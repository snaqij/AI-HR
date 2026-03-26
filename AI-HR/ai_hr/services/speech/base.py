"""语音 Provider 抽象。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ASRStreamResult:
    transcript: str
    confidence: float
    latency_ms: int
    provider: str
    metadata: dict[str, Any] | None = None
    is_active_pushed: bool = False


@dataclass(frozen=True, slots=True)
class TTSStreamResult:
    chunks: list[str]
    audio_uris: list[str]
    provider: str


class ASRProvider:
    provider_name: str = "unknown"

    def warmup(self, *, session_id: str) -> None:
        """Optional provider-side warmup hook."""
        return None

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
        raise NotImplementedError

    def flush(self, *, session_id: str) -> None:
        """Optional hook to clear accumulated state for a session."""
        return None


class TTSProvider:
    provider_name: str = "unknown"

    def warmup(self, *, session_id: str, voice: str) -> None:
        """Optional provider-side warmup hook."""
        return None

    def synthesize_stream(
        self,
        *,
        session_id: str,
        text: str,
        voice: str,
        chunk_size: int,
    ) -> TTSStreamResult:
        raise NotImplementedError

    def synthesize_stream_iter(
        self,
        *,
        session_id: str,
        text: str,
        voice: str,
        chunk_size: int,
    ):
        result = self.synthesize_stream(
            session_id=session_id,
            text=text,
            voice=voice,
            chunk_size=chunk_size,
        )
        total = len(result.audio_uris)
        for idx, uri in enumerate(result.audio_uris, start=1):
            yield {
                "index": idx,
                "audio_uri": uri,
                "text": result.chunks[idx - 1] if idx - 1 < len(result.chunks) else text,
                "is_final_packet": idx == total,
            }
