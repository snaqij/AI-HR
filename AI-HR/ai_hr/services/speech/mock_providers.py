"""Mock 语音 Provider。"""

from __future__ import annotations

from .base import ASRProvider, ASRStreamResult, TTSProvider, TTSStreamResult


class MockASRProvider(ASRProvider):
    provider_name = "mock"

    def transcribe_stream(
        self,
        *,
        session_id: str,
        seq: int,
        text_hint: str,
        audio_base64: str | None,
        confidence: float,
        latency_ms: int,
        chunk_index: int = 1,
        chunk_total: int = 1,
        is_final: bool = True,
        voice_format: str | None = None,
    ) -> ASRStreamResult:
        transcript = text_hint.strip() or f"ASR_TRANSCRIPT_SEQ_{seq}"
        return ASRStreamResult(
            transcript=transcript,
            confidence=confidence,
            latency_ms=latency_ms,
            provider=self.provider_name,
        )


class MockTTSProvider(TTSProvider):
    provider_name = "mock"

    def synthesize_stream(
        self,
        *,
        session_id: str,
        text: str,
        voice: str,
        chunk_size: int,
    ) -> TTSStreamResult:
        chunks = [text[idx : idx + chunk_size] for idx in range(0, len(text), chunk_size)]
        audio_uris = [f"mock://tts/{session_id}/{index + 1}.wav" for index in range(len(chunks))]
        return TTSStreamResult(chunks=chunks, audio_uris=audio_uris, provider=self.provider_name)
