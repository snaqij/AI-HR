"""OpenAI speech providers."""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request

from ...core.exceptions import ConnectorOperationError, InvalidConnectorConfigError
from .base import ASRProvider, ASRStreamResult, TTSProvider, TTSStreamResult


class OpenAIASRProvider(ASRProvider):
    provider_name = "openai"

    def __init__(self, *, api_key: str, base_url: str | None, timeout_ms: int):
        if not api_key:
            raise InvalidConnectorConfigError("OpenAI ASR provider requires api_key")
        self._api_key = api_key
        self._base_url = (base_url or "https://api.openai.com").rstrip("/")
        self._timeout = max(1.0, timeout_ms / 1000.0)

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
        if not audio_base64:
            # Compatible with no-audio-input scenarios; fallback to hint.
            transcript = text_hint.strip() or f"ASR_TRANSCRIPT_SEQ_{seq}"
            return ASRStreamResult(transcript=transcript, confidence=confidence, latency_ms=latency_ms, provider=self.provider_name)

        audio_bytes = base64.b64decode(audio_base64.encode("utf-8"))
        boundary = "----AIHRFormBoundary"
        body = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="model"\r\n\r\n'
            "gpt-4o-mini-transcribe\r\n"
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="file"; filename="audio.wav"\r\n'
            "Content-Type: audio/wav\r\n\r\n"
        ).encode("utf-8") + audio_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")

        request = urllib.request.Request(
            url=f"{self._base_url}/v1/audio/transcriptions",
            method="POST",
            data=body,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise ConnectorOperationError(f"OpenAI ASR HTTP error: {exc.code}") from exc
        except Exception as exc:  # pragma: no cover
            raise ConnectorOperationError(f"OpenAI ASR error: {exc}") from exc

        transcript = str(payload.get("text") or text_hint or f"ASR_TRANSCRIPT_SEQ_{seq}")
        return ASRStreamResult(
            transcript=transcript,
            confidence=confidence,
            latency_ms=latency_ms,
            provider=self.provider_name,
        )


class OpenAITTSProvider(TTSProvider):
    provider_name = "openai"

    def __init__(self, *, api_key: str, base_url: str | None, timeout_ms: int):
        if not api_key:
            raise InvalidConnectorConfigError("OpenAI TTS provider requires api_key")
        self._api_key = api_key
        self._base_url = (base_url or "https://api.openai.com").rstrip("/")
        self._timeout = max(1.0, timeout_ms / 1000.0)

    def synthesize_stream(
        self,
        *,
        session_id: str,
        text: str,
        voice: str,
        chunk_size: int,
    ) -> TTSStreamResult:
        chunks = [text[idx : idx + chunk_size] for idx in range(0, len(text), chunk_size)]
        audio_uris: list[str] = []
        for index, chunk in enumerate(chunks, start=1):
            body = json.dumps(
                {
                    "model": "gpt-4o-mini-tts",
                    "voice": voice if voice != "default" else "alloy",
                    "input": chunk,
                }
            ).encode("utf-8")
            request = urllib.request.Request(
                url=f"{self._base_url}/v1/audio/speech",
                method="POST",
                data=body,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
            )
            try:
                with urllib.request.urlopen(request, timeout=self._timeout) as response:
                    audio_bytes = response.read()
            except urllib.error.HTTPError as exc:
                raise ConnectorOperationError(f"OpenAI TTS HTTP error: {exc.code}") from exc
            except Exception as exc:  # pragma: no cover
                raise ConnectorOperationError(f"OpenAI TTS error: {exc}") from exc
            audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")
            audio_uris.append(f"data:audio/mpeg;base64,{audio_base64}")
        return TTSStreamResult(chunks=chunks, audio_uris=audio_uris, provider=self.provider_name)
