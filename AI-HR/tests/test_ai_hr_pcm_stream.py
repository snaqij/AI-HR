from __future__ import annotations

import base64

from ai_hr.services.rtc.pcm_stream import build_asr_stream_payloads, split_pcm16le_chunks


def test_split_pcm16le_chunks_should_keep_frame_boundary() -> None:
    # 16kHz, mono, 16-bit => 32000 bytes / sec
    pcm = b"\x00\x00" * 16000
    chunks = split_pcm16le_chunks(
        pcm_bytes=pcm,
        sample_rate=16000,
        channels=1,
        sample_width=2,
        chunk_ms=250,
    )
    assert len(chunks) == 4
    assert sum(len(item) for item in chunks) == len(pcm)
    assert all(len(item) % 2 == 0 for item in chunks)


def test_build_asr_stream_payloads_should_mark_final_chunk() -> None:
    pcm = b"\x01\x02" * 8000
    payloads = build_asr_stream_payloads(
        seq=5,
        pcm_bytes=pcm,
        sample_rate=16000,
        channels=1,
        chunk_ms=200,
        text_hint="hello",
    )
    assert len(payloads) >= 1
    assert payloads[0]["chunk_index"] == 1
    assert payloads[-1]["is_final"] is True
    assert all(item["chunk_total"] == len(payloads) for item in payloads)
    raw = base64.b64decode(payloads[0]["audio_base64"].encode("utf-8"))
    assert raw.startswith(b"RIFF")

