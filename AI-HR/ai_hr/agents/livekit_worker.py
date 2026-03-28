import asyncio
import logging
import base64
import uuid
import threading
from livekit import agents, rtc
from livekit.agents import stt, tts, pipeline

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
        # BE-013: Use generator directly in executor to enable true streaming
        loop = asyncio.get_running_loop()
        
        def _stream_to_chan():
            try:
                for p in self._provider.synthesize_stream_iter(
                    session_id=str(uuid.uuid4()),
                    text=self._text,
                    voice="default",
                    chunk_size=50,
                ):
                    audio_bytes = p.get("audio_bytes")
                    if audio_bytes:
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

        try:
            await loop.run_in_executor(None, _stream_to_chan)
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
    logger.info(f"Connected to room {ctx.room.name}. Waiting for backend commands.")

    # BE-013: Redundant VoicePipelineAgent removed.
    # The backend (AIInterviewService) now handles the interview logic, VAD, and playback triggers.
    # This worker can be used for session maintenance or specific RTC tasks.

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    agents.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))
