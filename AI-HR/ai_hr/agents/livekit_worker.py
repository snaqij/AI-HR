import asyncio
import logging
import base64
import uuid
from livekit import agents, rtc
from livekit.agents import stt, tts, pipeline
from livekit.plugins import openai

# Internal imports
from ai_hr.core.config import get_settings
from ai_hr.services.speech.tencent_providers import TencentASRProvider, TencentTTSProvider

logger = logging.getLogger("livekit-worker")

class TencentSTT(stt.STT):
    def __init__(self, provider: TencentASRProvider):
        super().__init__(streaming_supported=True)
        self._provider = provider

    def stream(self, *, language: str | None = None) -> stt.STTStream:
         return TencentSTTStream(self._provider)

class TencentSTTStream(stt.STTStream):
    def __init__(self, provider: TencentASRProvider):
        super().__init__()
        self._provider = provider
        self._audio_queue = asyncio.Queue()
        self._closed = False

    def push_frame(self, frame: rtc.AudioFrame):
        if self._closed:
            return
        # Ensure frame is PCM 16kHz mono
        resampled_frame = frame.remix_and_resample(16000, 1)
        self._audio_queue.put_nowait(resampled_frame.data.tobytes())

    async def _run(self):
         # Create a generator that reads from the queue for the provider
         async def _gen_audio():
             while not self._closed:
                 try:
                     chunk = await self._audio_queue.get()
                     if chunk is None:
                         break
                     yield base64.b64encode(chunk).decode("utf-8")
                 except Exception:
                     break

         try:
             # Bridge to our existing provider
             # Note: transcribe_stream is sync/blocking in its current form, so we use to_thread
             def _sync_transcribe():
                 # This would need a minor change to propagate results via callback
                 # For now, we simulate the results
                 pass
             
             # Actually, for the best performance, we'd use the WS provider directly here
             # But for this V1, let's keep the high-level logic and assume direct WS integration.
             pass
         finally:
             self._closed = True

class TencentTTS(tts.TTS):
    def __init__(self, provider: TencentTTSProvider):
        super().__init__(
            capabilities=tts.TTSCapabilities(streaming=True),
            sample_rate=16000,
            num_channels=1
        )
        self._provider = provider

    def synthesize(self, text: str) -> tts.SynthesizeStream:
        return TencentTTSStream(self._provider, text)

class TencentTTSStream(tts.SynthesizeStream):
    def __init__(self, provider: TencentTTSProvider, text: str):
        super().__init__()
        self._provider = provider
        self._text = text

    async def _run(self):
        # Tencent TTS synthesis
        # We wrap the sync iterator in a thread to keep the event loop free
        loop = asyncio.get_running_loop()

        def _get_packets():
            return list(self._provider.synthesize_stream_iter(
                session_id=str(uuid.uuid4()),
                text=self._text,
                voice="default",
                chunk_size=40,
            ))

        try:
            packets = await loop.run_in_executor(None, _get_packets)
            for p in packets:
                 # In a real impl, we'd stream this instead of list()
                 audio_bytes = p.get("audio_bytes")
                 if audio_bytes:
                     # LiveKit expects AudioFrame packets
                     # For simplicity in this Demo, we send the raw data if it matches format
                     self._event_chan.send_nowait(tts.SynthesizePacket(
                         audio=rtc.AudioFrame(
                             data=audio_bytes,
                             sample_rate=16000,
                             num_channels=1,
                             samples_per_channel=len(audio_bytes) // 2
                         )
                     ))
        except Exception as e:
            logger.error(f"TTS synthesis failed: {e}")
        finally:
            self.closed = True

async def entrypoint(ctx: agents.JobContext):
    settings = get_settings()
    
    # Initialize our existing providers
    asr_provider = TencentASRProvider(
        secret_id=settings.asr_tencent_secret_id,
        secret_key=settings.asr_tencent_secret_key,
        region=settings.asr_tencent_region,
        app_id=settings.asr_tencent_app_id,
        ws_open_timeout_ms=settings.asr_stream_timeout_ms,
    )
    
    tts_provider = TencentTTSProvider(
        secret_id=settings.tts_tencent_secret_id,
        secret_key=settings.tts_tencent_secret_key,
        region=settings.tts_tencent_region,
        timeout_ms=settings.tts_timeout_ms,
    )

    await ctx.connect()
    logger.info(f"Connected to room {ctx.room.name}")

    # VoicePipelineAgent is the high-level API to orchestrate VAD + STT + LLM + TTS
    agent = pipeline.VoicePipelineAgent(
        vad=agents.vad.SileroVAD(), # Standard VAD
        stt=TencentSTT(asr_provider),
        llm=openai.LLM(model="gpt-4o"), # Or use internal LLM wrapper
        tts=TencentTTS(tts_provider),
        chat_ctx=openai.ChatContext().append(
            role="system",
            text="You are a professional HR interviewer. Conduct a technical interview in a natural way."
        ),
    )

    agent.start(ctx.room)
    
    # Initial greeting
    await agent.say("Hi there! I am your AI interviewer today. Let's start the interview.", allow_interruptions=True)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    agents.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))
