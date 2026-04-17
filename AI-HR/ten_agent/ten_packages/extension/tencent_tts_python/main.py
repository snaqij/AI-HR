import os
import sys
import uuid
import json
import time
import asyncio

from ten_runtime import (
    AudioFrame,
    AudioFrameDataFmt,
    Cmd,
    Data,
    AsyncExtension,
    AsyncTenEnv,
    CmdResult,
    StatusCode,
)

current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, "../../../"))
if project_root not in sys.path:
    sys.path.append(project_root)

from ai_hr.services.speech.tencent_providers import TencentTTSProvider


class TencentTTSExtension(AsyncExtension):
    def __init__(self, name: str):
        super().__init__(name)
        self.session_id = str(uuid.uuid4())
        self.interrupted = False
        self.provider = None
        self.text_queue = asyncio.Queue()
        self.pipeline_queue = asyncio.Queue()
        self.active_tasks = set()
        self.synthesis_worker_task = None
        self.playback_worker_task = None
        self.turn_start_time = 0.0
        self.last_text_time = 0.0

    async def on_init(self, ten_env: AsyncTenEnv) -> None:
        print("[tencent_tts] on_init starting...", flush=True)
        self.interrupted = False
        config_json, _ = await ten_env.get_property_to_json("")
        config = json.loads(config_json) if config_json else {}

        secret_id = config.get("secret_id", "")
        secret_key = config.get("secret_key", "")
        region = config.get("region", "ap-guangzhou")
        app_id = config.get("app_id", "")
        voice_type = config.get("voice_type", 101001) # Default to Zhiqi (Female)

        self.provider = TencentTTSProvider(
            secret_id=secret_id,
            secret_key=secret_key,
            region=region,
            app_id=app_id,
            voice_type=voice_type,
            timeout_ms=5000,
            ws_streaming_enabled=True,
        )
        
        # 1. Start Synthesis Dispatcher
        self.synthesis_worker_task = asyncio.create_task(self._synthesis_dispatch_loop(ten_env))
        # 2. Start Streaming Player
        self.playback_worker_task = asyncio.create_task(self._playback_loop(ten_env))
        
        print("[tencent_tts] on_init done. Pooled Pipeline system active.", flush=True)

    async def _synthesis_dispatch_loop(self, ten_env: AsyncTenEnv):
        """Core: Concurrent Fetching. Distributes sentences to workers immediately."""
        while True:
            item = await self.text_queue.get()
            if self.interrupted:
                self.text_queue.task_done()
                continue
            
            text = item.get("text")
            meta = item.get("meta", {})
                
            sentence_q = asyncio.Queue()
            await self.pipeline_queue.put(sentence_q)
            
            task = asyncio.create_task(self._fetch_sentence(text, sentence_q, time.perf_counter(), meta))
            self.active_tasks.add(task)
            task.add_done_callback(self.active_tasks.discard)
            self.text_queue.task_done()

    async def _fetch_sentence(self, text: str, sentence_q: asyncio.Queue, receive_ts: float, meta: dict = None):
        try:
            loop = asyncio.get_running_loop()

            def get_iter():
                return self.provider.synthesize_stream_iter(
                    session_id=self.session_id,
                    text=text,
                    voice="default",
                    chunk_size=50,
                )
                
            def consume():
                try:
                    for packet in get_iter():
                        if self.interrupted: break
                        audio_bytes = packet.get("audio_bytes") or b""
                        if audio_bytes:
                            if not hasattr(consume, "_first_packet_sent"):
                                consume._first_packet_sent = True
                                tts_latency = (time.perf_counter() - receive_ts) * 1000
                                print(f"[LATENCY_TTS] First Packet Latency: {tts_latency:.2f}ms for text: {text[:20]}...", flush=True)
                                
                                # 核心：计算闭环真终点时延（从用户开口结束到听到声音）
                                if meta and meta.get("asr_physical_stop_ts"):
                                    true_e2e = (time.perf_counter() - meta["asr_physical_stop_ts"]) * 1000
                                    print(f"  >>> [FINAL_E2E_LATENCY] Physical Stop -> Ear: {true_e2e:.2f}ms | Trace: {meta.get('trace_id')}\n", flush=True)
                            
                            loop.call_soon_threadsafe(sentence_q.put_nowait, audio_bytes)
                except Exception as exc:
                    print(f"[tencent_tts] provider failure: {exc}", flush=True)
                finally:
                    loop.call_soon_threadsafe(sentence_q.put_nowait, b"EOF")
            
            await asyncio.to_thread(consume)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"[tencent_tts] synthesis failure: {e}", flush=True)
            await sentence_q.put(b"EOF")

    async def _playback_loop(self, ten_env: AsyncTenEnv):
        """Consumes sentence queues in order with precise clock gating for fluid transitions."""
        next_frame_time = time.perf_counter()
        while True:
            sentence_q = await self.pipeline_queue.get()
            print(f"[tencent_tts] playback: starting new sentence queue.", flush=True)
            self.turn_start_time = time.time() # Reset shield for EACH sentence
            if self.interrupted:
                self.pipeline_queue.task_done()
                continue
            
            while True:
                if self.interrupted: break
                chunk = await sentence_q.get()
                if chunk == b"EOF":
                    sentence_q.task_done()
                    break
                
                try:
                    frame = AudioFrame.create("pcm_frame")
                    frame.set_bytes_per_sample(2)
                    frame.set_sample_rate(16000)
                    frame.set_number_of_channels(1)
                    frame.set_data_fmt(AudioFrameDataFmt.INTERLEAVE)
                    frame.set_samples_per_channel(len(chunk) // 2)
                    frame.alloc_buf(len(chunk))
                    buf = frame.lock_buf()
                    buf[:] = chunk
                    frame.unlock_buf(buf)
                    
                    duration_sec = len(chunk) / 32000.0
                    now = time.perf_counter()
                    if next_frame_time < now:
                        next_frame_time = now
                        self.turn_start_time = time.time()
                        
                    await ten_env.send_audio_frame(frame)
                    
                    next_frame_time += duration_sec
                    sleep_time = next_frame_time - time.perf_counter()
                    if sleep_time > 0.05:
                        if self.interrupted: break
                        await asyncio.sleep(sleep_time - 0.05)
                except Exception as e:
                    print(f"[tencent_tts] playback error: {e}", flush=True)
                finally:
                    sentence_q.task_done()
            self.pipeline_queue.task_done()

    async def on_start(self, ten_env: AsyncTenEnv) -> None:
        pass

    async def on_stop(self, ten_env: AsyncTenEnv) -> None:
        self.interrupted = True
        for task in self.active_tasks:
            if not task.done(): task.cancel()
        if self.synthesis_worker_task: self.synthesis_worker_task.cancel()
        if self.playback_worker_task: self.playback_worker_task.cancel()

    async def on_cmd(self, ten_env: AsyncTenEnv, cmd: Cmd) -> None:
        cmd_name = cmd.get_name()
        if cmd_name in {"interrupt", "start_of_sentence"}:
            # 将保护期减少到 0.1s，确保用户可以几乎随时打断
            if time.time() - self.last_text_time < 0.1:
                print(f"[tencent_tts] on_cmd: {cmd_name} IGNORED (Initial 0.1s Protection Active!)", flush=True)
                await ten_env.return_result(CmdResult.create(StatusCode.OK, cmd))
                return

            # 将护盾减少到 0.05s，最高程度提高打断灵敏度
            if cmd_name == "start_of_sentence" and time.time() - getattr(self, "turn_start_time", 0) < 0.05:
                print(f"[tencent_tts] on_cmd: {cmd_name} IGNORED (Acoustic Echo Shield Active!)", flush=True)
                await ten_env.return_result(CmdResult.create(StatusCode.OK, cmd))
                return

            print(f"[tencent_tts] on_cmd: {cmd_name} !! FLUSHING !!", flush=True)
            self.interrupted = True
            
            for task in list(self.active_tasks):
                if not task.done(): task.cancel()
            self.active_tasks.clear()
            
            while not self.text_queue.empty():
                try: self.text_queue.get_nowait(); self.text_queue.task_done()
                except asyncio.QueueEmpty: break
            
            while not self.pipeline_queue.empty():
                try: self.pipeline_queue.get_nowait(); self.pipeline_queue.task_done()
                except asyncio.QueueEmpty: break

        await ten_env.return_result(CmdResult.create(StatusCode.OK, cmd))

    async def on_data(self, ten_env: AsyncTenEnv, data: Data) -> None:
        text, _ = data.get_property_string("text")
        text = (text or "").strip()
        if text:
            self.interrupted = False
            self.last_text_time = time.time()
            
            # 提取元数据
            asr_physical_stop_ts, _ = data.get_property_float("asr_physical_stop_ts")
            trace_id, _ = data.get_property_string("trace_id")
            
            item = {
                "text": text,
                "meta": {
                    "asr_physical_stop_ts": asr_physical_stop_ts,
                    "trace_id": trace_id
                }
            }
            await self.text_queue.put(item)
            
    async def on_pcm_frame(self, ten_env: AsyncTenEnv, audio_frame: AudioFrame) -> None:
        pass

    async def on_pcm_frame(self, ten_env: AsyncTenEnv, audio_frame: AudioFrame) -> None:
        pass


if __name__ == "__main__":
    from ten_runtime import Main
    Main(TencentTTSExtension).run()
