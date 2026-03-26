"""PCM chunk helpers for realtime ASR streaming uploads."""

from __future__ import annotations

import base64
import io
import wave


def split_pcm16le_chunks(
    *,
    pcm_bytes: bytes,
    sample_rate: int,
    channels: int,
    sample_width: int = 2,
    chunk_ms: int = 400,
) -> list[bytes]:
    """Split PCM bytes by time window and keep frame boundaries."""
    safe_chunk_ms = max(100, chunk_ms)
    frame_bytes = max(1, channels * sample_width)
    chunk_bytes = int(sample_rate * frame_bytes * (safe_chunk_ms / 1000.0))
    chunk_bytes = max(frame_bytes, chunk_bytes - (chunk_bytes % frame_bytes))
    chunks: list[bytes] = []
    for offset in range(0, len(pcm_bytes), chunk_bytes):
        piece = pcm_bytes[offset : offset + chunk_bytes]
        if piece:
            chunks.append(piece)
    return chunks or [b""]


def pcm16le_to_wav_bytes(
    *,
    pcm_bytes: bytes,
    sample_rate: int,
    channels: int,
    sample_width: int = 2,
) -> bytes:
    """Pack one PCM chunk as wav for ASR provider compatibility."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)
    return buf.getvalue()


def build_asr_stream_payloads(
    *,
    seq: int,
    pcm_bytes: bytes,
    sample_rate: int,
    channels: int,
    chunk_ms: int,
    text_hint: str = "",
    confidence: float = 0.9,
    input_format: str = "wav",
    target_latency_ms: int = 700,
) -> list[dict]:
    """Build payloads for POST /ai/interviews/sessions/{id}/rtc/asr/stream."""
    chunks = split_pcm16le_chunks(
        pcm_bytes=pcm_bytes,
        sample_rate=sample_rate,
        channels=channels,
        sample_width=2,
        chunk_ms=chunk_ms,
    )
    total = len(chunks)
    payloads: list[dict] = []
    for idx, chunk in enumerate(chunks, start=1):
        wav_bytes = pcm16le_to_wav_bytes(
            pcm_bytes=chunk,
            sample_rate=sample_rate,
            channels=channels,
            sample_width=2,
        )
        payloads.append(
            {
                "seq": seq,
                "text_hint": text_hint,
                "audio_base64": base64.b64encode(wav_bytes).decode("utf-8"),
                "confidence": confidence,
                "latency_ms": 500,
                "chunk_index": idx,
                "chunk_total": total,
                "is_final": idx == total,
                "input_format": input_format,
                "target_latency_ms": target_latency_ms,
            }
        )
    return payloads

