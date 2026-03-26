import time
import base64
from ai_hr.core.config import get_settings
from ai_hr.services.speech.factory import create_asr_provider

settings = get_settings()
provider = create_asr_provider(settings)
audio = base64.b64encode(b"\x00" * 3200).decode()

def _instrumented_collect(self, *, ctx, wait_for_final, timeout_seconds):
    print(f"COLLECT START with timeout {timeout_seconds}")
    deadline = time.perf_counter() + max(0.01, timeout_seconds)
    texts = []
    reached_final = False
    while time.perf_counter() < deadline:
        rem = max(0.01, deadline - time.perf_counter())
        print(f"Calling recv with rem={rem:.3f}")
        start = time.perf_counter()
        try:
            msg = ctx.ws.recv(timeout=rem)
            print(f"Recv returned msg of type {type(msg)} in {time.perf_counter()-start:.3f}s")
            print(f"MSG: {msg}")
        except TimeoutError:
            print(f"TimeoutError caught in {time.perf_counter()-start:.3f}s")
            break
        except Exception as e:
            print(f"Exception {type(e)} caught in {time.perf_counter()-start:.3f}s: {e}")
            break
    print("COLLECT END")
    return texts, reached_final

import types
provider._collect_ws_messages = types.MethodType(_instrumented_collect, provider)

start = time.perf_counter()
try:
    res = provider._transcribe_stream_ws_duplex(
        session_id="test_perf_123", seq=1, text_hint="", audio_base64=audio,
        confidence=0.9, chunk_index=1, chunk_total=2, is_final=False
    )
    print(f"overall {time.perf_counter() - start:.3f}")
except Exception as e:
    print(f"ERR: {e}")

