import base64
import time
import os
import sys

from ten_runtime import (
    AudioFrame,
    Cmd,
    Data,
    AsyncExtension,
    AsyncTenEnv,
    CmdResult,
    StatusCode,
)

current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, "../../../../../apps/backend"))
if project_root not in sys.path:
    sys.path.append(project_root)

from ai_hr.services.speech.aliyun_providers import AliyunNlsASRProvider


def _get_string(ten_env: AsyncTenEnv, path: str, default: str = "") -> str:
    # This is a placeholder for async property getting if needed, 
    # but for now we use the sync ones from init if available.
    return default


class AliyunNlsASRExtension(AsyncExtension):
    def __init__(self, name: str):
        super().__init__(name)
        self.session_id = ""
        self.provider: AliyunNlsASRProvider | None = None
        self.logged_first_audio_frame = False
        self.last_partial = ""

    async def _emit_transcript(self, ten_env: AsyncTenEnv, transcript: str, is_final: bool, metadata: dict = None) -> None:
        transcript = (transcript or "").strip()
        if not transcript:
            return

        # 记录流控：如果是 Partial，且与上次相比无显著变化，则为了减轻总线压力略过
        if not is_final and transcript == self.last_partial:
            return

        output_data = Data.create("text_data")
        output_data.set_property_string("text", transcript)
        output_data.set_property_bool("is_final", is_final)
        
        # 记录 ASR 产生的绝对时间戳透传给 Orchestrator
        metadata = metadata or {}
        if is_final:
            output_data.set_property_float("asr_final_ts", metadata.get("asr_final_ts") or time.perf_counter())
            output_data.set_property_float("asr_sentence_start_ts", metadata.get("asr_sentence_start_ts") or 0.0)
            output_data.set_property_float("asr_physical_stop_ts", metadata.get("asr_physical_stop_ts") or 0.0)
        
        await ten_env.send_data(output_data)

        if is_final:
            print(f"[aliyun_nls_asr] final transcript: {transcript}", flush=True)
            self.provider.flush(session_id=self.session_id)
            self.last_partial = ""
        else:
            self.last_partial = transcript

    async def on_init(self, ten_env: AsyncTenEnv) -> None:
        print("[aliyun_nls_asr] on_init starting...", flush=True)
        # In AsyncExtension, we extract properties from the initial json
        config_json, _ = await ten_env.get_property_to_json("")
        import json
        config = json.loads(config_json) if config_json else {}
        
        appkey = config.get("appkey", "")
        access_key_id = config.get("access_key_id", "")
        access_key_secret = config.get("access_key_secret", "")
        vocabulary_id = config.get("vocabulary_id")
        customization_id = config.get("customization_id")

        self.provider = AliyunNlsASRProvider(
            appkey=appkey,
            access_key_id=access_key_id,
            access_key_secret=access_key_secret,
            streaming_enabled=True,
            vocabulary_id=vocabulary_id,
            customization_id=customization_id,
        )
        self.session_id = "ten_session_" + base64.b64encode(os.urandom(6)).decode("ascii")
        print(f"[aliyun_nls_asr] on_init done. Session: {self.session_id}", flush=True)

    async def on_start(self, ten_env: AsyncTenEnv) -> None:
        print("[aliyun_nls_asr] on_start", flush=True)
        if self.provider is not None:
            self.provider.warmup(session_id=self.session_id)
        print("[aliyun_nls_asr] warmup finished", flush=True)

    async def on_stop(self, ten_env: AsyncTenEnv) -> None:
        print("[aliyun_nls_asr] on_stop", flush=True)
        if self.provider is not None:
            self.provider.flush(session_id=self.session_id)

    async def on_cmd(self, ten_env: AsyncTenEnv, cmd: Cmd) -> None:
        cmd_name = cmd.get_name()
        print(f"[aliyun_nls_asr] on_cmd: {cmd_name}", flush=True)

        if self.provider is not None:
            if cmd_name == "start_of_sentence":
                self.provider.flush(session_id=self.session_id)
                self.last_partial = ""
            elif cmd_name == "end_of_sentence":
                try:
                    vad_stop_ts = time.perf_counter()  # Capture VAD-confirmed silence time NOW
                    result = self.provider.transcribe_stream(
                        session_id=self.session_id,
                        seq=0,
                        text_hint="",
                        audio_bytes=b"",
                        confidence=1.0,
                        latency_ms=0,
                        is_final=True,
                    )
                    metadata = result.metadata or {}
                    # CRITICAL: If NLS hasn't fired on_sentence_end yet (mid-sentence VAD pause),
                    # asr_physical_stop_ts will be 0.0 or stale, causing silence_ms to be astronomically
                    # large in the orchestrator finalize loop → immediate force_finalize → user interrupted.
                    # Fix: always use the VAD-confirmed stop time as the physical stop anchor.
                    if not metadata.get("asr_physical_stop_ts"):
                        metadata["asr_physical_stop_ts"] = vad_stop_ts
                    await self._emit_transcript(ten_env, result.transcript or "", True, metadata)
                except Exception as exc:
                    print(f"[aliyun_nls_asr] finalize error: {exc}", flush=True)

        # CRITICAL: Always return a result for commands
        await ten_env.return_result(CmdResult.create(StatusCode.OK, cmd))

    async def on_pcm_frame(self, ten_env: AsyncTenEnv, audio_frame: AudioFrame) -> None:
        # Standard callback for named port "pcm_frame"
        await self.on_audio_frame(ten_env, audio_frame)

    async def on_audio_frame(self, ten_env: AsyncTenEnv, audio_frame: AudioFrame) -> None:
        if not self.logged_first_audio_frame:
            self.logged_first_audio_frame = True
            print("[aliyun_nls_asr] !!! ABSOLUTELY FIRST AUDIO FRAME REACHED !!!", flush=True)

        if self.provider is None:
            return

        audio_data = audio_frame.get_buf()
        if not audio_data:
            return

        try:
            result = self.provider.transcribe_stream(
                session_id=self.session_id,
                seq=0,
                text_hint="",
                audio_bytes=bytes(audio_data),
                confidence=1.0,
                latency_ms=0,
                is_final=False,
            )
            
            metadata = result.metadata or {}
            is_final = bool(metadata.get("sentence_completed"))
            await self._emit_transcript(ten_env, result.transcript or "", is_final, metadata)
        except Exception as exc:
            # Avoid flooding logs but show errors
            pass


if __name__ == "__main__":
    from ten_runtime import Main
    Main(AliyunNlsASRExtension).run()
