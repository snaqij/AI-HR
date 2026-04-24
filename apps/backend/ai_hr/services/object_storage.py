"""Object storage client abstractions."""

from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlsplit

try:
    from minio import Minio
    from minio.error import S3Error
except Exception:  # pragma: no cover - optional dependency for object storage runtime
    Minio = None  # type: ignore[assignment]
    S3Error = Exception  # type: ignore[assignment]

from ..core.config import Settings
from ..core.exceptions import InvalidStateError, ObjectStorageError


@dataclass(frozen=True, slots=True)
class StoredObject:
    provider: str
    bucket: str
    object_key: str
    object_url: str
    etag: str | None


class MinioResumeStorage:
    """MinIO-backed resume object storage."""

    def __init__(self, settings: Settings):
        if Minio is None:
            raise InvalidStateError(
                "Object storage requires optional dependency 'minio'. "
                "Install it with: pip install 'minio>=7.2.9'"
            )
        self._settings = settings
        endpoint = (settings.object_storage_endpoint or "").strip()
        access_key = (settings.object_storage_access_key or "").strip()
        secret_key = (settings.object_storage_secret_key or "").strip()
        if not endpoint or not access_key or not secret_key:
            raise InvalidStateError(
                "Object storage is enabled but endpoint/access key/secret key is missing. "
                "Please set AI_HR_OBJECT_STORAGE_ENDPOINT/ACCESS_KEY/SECRET_KEY."
            )
        self._bucket = settings.object_storage_bucket.strip()
        if not self._bucket:
            raise InvalidStateError("AI_HR_OBJECT_STORAGE_BUCKET cannot be empty when object storage is enabled.")

        self._client = Minio(
            endpoint=endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=bool(settings.object_storage_secure),
            region=(settings.object_storage_region or None),
        )
        self._bucket_ensured = False

    def upload_resume(
        self,
        *,
        object_key: str,
        content: bytes,
        content_type: str | None,
        metadata: dict[str, str] | None = None,
    ) -> StoredObject:
        self._ensure_bucket()
        stream = io.BytesIO(content)
        try:
            result = self._client.put_object(
                bucket_name=self._bucket,
                object_name=object_key,
                data=stream,
                length=len(content),
                content_type=(content_type or "application/octet-stream"),
                metadata=(metadata or {}),
            )
        except S3Error as exc:
            raise ObjectStorageError(f"MinIO put_object failed for '{object_key}': {exc}") from exc
        return StoredObject(
            provider="minio",
            bucket=self._bucket,
            object_key=object_key,
            object_url=self._build_object_url(object_key),
            etag=getattr(result, "etag", None),
        )

    def _ensure_bucket(self) -> None:
        if self._bucket_ensured:
            return
        try:
            exists = self._client.bucket_exists(self._bucket)
            if not exists:
                if not self._settings.object_storage_auto_create_bucket:
                    raise ObjectStorageError(
                        f"MinIO bucket '{self._bucket}' does not exist and auto-create is disabled."
                    )
                self._client.make_bucket(self._bucket)
        except S3Error as exc:
            raise ObjectStorageError(f"MinIO bucket check/create failed for '{self._bucket}': {exc}") from exc
        self._bucket_ensured = True

    def _build_object_url(self, object_key: str) -> str:
        public_base = (self._settings.object_storage_public_base_url or "").strip()
        if public_base:
            return f"{public_base.rstrip('/')}/{self._bucket}/{object_key}"

        endpoint = (self._settings.object_storage_endpoint or "").strip()
        if "://" not in endpoint:
            scheme = "https" if self._settings.object_storage_secure else "http"
            endpoint = f"{scheme}://{endpoint}"
        parsed = urlsplit(endpoint)
        scheme = parsed.scheme or ("https" if self._settings.object_storage_secure else "http")
        netloc = parsed.netloc or parsed.path
        return f"{scheme}://{netloc}/{self._bucket}/{object_key}"


def build_resume_storage_key(
    *,
    prefix: str,
    source_channel: str,
    candidate_id: str,
    file_sha256: str,
    file_name: str,
) -> str:
    safe_name = "".join(ch if ch.isalnum() or ch in {".", "_", "-"} else "_" for ch in (file_name or "resume.bin")).strip("._")
    if not safe_name:
        safe_name = "resume.bin"
    date_prefix = datetime.now(UTC).strftime("%Y/%m/%d")
    base_prefix = (prefix or "resume-attachments").strip().strip("/")
    return f"{base_prefix}/{source_channel}/{date_prefix}/{candidate_id}/{file_sha256[:16]}-{safe_name}"
