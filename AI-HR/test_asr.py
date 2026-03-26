import time
import base64
from ai_hr.core.config import get_settings
from ai_hr.services.speech.factory import create_asr_provider

settings = get_settings()
provider = create_asr_provider(settings)

# Send 2 seconds of silent audio (64,000 bytes)
audio = base64.b64encode(b"\x00" * 64000).decode()

print("Starting WS ASR with 2s audio buffer (testing pacing)...")
start = time.perf_counter()
try:
    res = provider._transcribe_stream_ws_duplex(
        session_id="test_perf_123", seq=1, text_hint="", audio_base64=audio,
        confidence=0.9, chunk_index=1, chunk_total=1, is_final=True
    )
    print(f"WS final took {time.perf_counter() - start:.3f}s. latency_ms={res.latency_ms}", flush=True)
    print(f"Transcript: {res.transcript}", flush=True)
except Exception as e:
    print(f"WS error: {e}", flush=True)

time.sleep(2)
print("Test finished.", flush=True)
