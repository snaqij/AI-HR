import time
import socket

orig = socket.getaddrinfo
def ipv4_getaddrinfo(host, port, family=0, *args, **kwargs):
    return orig(host, port, socket.AF_INET, *args, **kwargs)
socket.getaddrinfo = ipv4_getaddrinfo

try:
    ws_url = "wss://asr.cloud.tencent.com/asr/v2"
    import websockets.sync.client
    start = time.perf_counter()
    try:
        ws = websockets.sync.client.connect(ws_url, open_timeout=0.8, close_timeout=1, max_size=8*1024*1024)
        print(f"Time taken: {time.perf_counter()-start:.3f}s. Success")
    except Exception as e:
        print(f"Time taken: {time.perf_counter()-start:.3f}s. Error: {type(e)} - {e}")
finally:
    socket.getaddrinfo = orig
