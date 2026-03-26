import time
import base64
from ai_hr.core.config import get_settings
from ai_hr.services.speech.factory import create_asr_provider
import sys

settings = get_settings()
provider = create_asr_provider(settings)
audio = base64.b64encode(b"\x00" * 3200).decode()

orig = provider._transcribe_stream_ws_duplex
def _instrumented(*args, **kwargs):
    print("ENTRY")
    start = time.perf_counter()
    def trace(frame, event, arg):
        if event == "line" and "tencent_providers" in frame.f_code.co_filename:
            lineno = frame.f_lineno
            elapsed = time.perf_counter() - start
            if elapsed > 0.5:
                print(f"L{lineno} took {elapsed:.3f}s")
        return trace
    sys.settrace(trace)
    try:
        res = orig(*args, **kwargs)
    finally:
        sys.settrace(None)
    print("EXIT")
    return res

provider._transcribe_stream_ws_duplex = _instrumented

start = time.perf_counter()
try:
    res = provider._transcribe_stream_ws_duplex(
        session_id="test_perf_123", seq=1, text_hint="", audio_base64=audio,
        confidence=0.9, chunk_index=1, chunk_total=2, is_final=False
    )
    print(f"overall {time.perf_counter() - start:.3f}")
except Exception as e:
    print(f"ERR: {e}")
