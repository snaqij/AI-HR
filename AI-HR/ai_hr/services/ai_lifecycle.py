"""AI 面试生命周期清理服务。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..repositories.ai_lifecycle import AIInterviewLifecycleRepository


class AIInterviewLifecycleService:
    """执行转写/音频/事件生命周期清理任务。"""

    def __init__(self, session: Session):
        self._settings = get_settings()
        self._repo = AIInterviewLifecycleRepository(session)

    def run_cleanup(self, *, dry_run: bool = True, batch_size: int | None = None) -> dict[str, int | bool | str]:
        now = datetime.now(UTC).replace(tzinfo=None)
        batch = int(batch_size or self._settings.ai_interview_cleanup_batch_size)

        transcript_cutoff = now - timedelta(days=max(1, self._settings.ai_interview_transcript_retention_days))
        audio_cutoff = now - timedelta(days=max(1, self._settings.ai_interview_audio_retention_days))
        event_cutoff = now - timedelta(days=max(1, self._settings.ai_interview_event_retention_days))

        transcript_ids = self._repo.list_expired_transcript_turn_ids(cutoff=transcript_cutoff, limit=batch)
        transcript_cleared = self._repo.clear_transcripts(turn_ids=transcript_ids, cleaned_at=now, dry_run=dry_run)

        audio_ids = self._repo.list_expired_audio_turn_ids(cutoff=audio_cutoff, limit=batch)
        audio_cleared = self._repo.clear_audio_uris(turn_ids=audio_ids, cleaned_at=now, dry_run=dry_run)

        event_ids = self._repo.list_expired_ai_event_ids(cutoff=event_cutoff, limit=batch)
        event_deleted = self._repo.delete_events(event_ids=event_ids, dry_run=dry_run)

        summary = {
            "dry_run": dry_run,
            "batch_size": batch,
            "transcript_candidates": len(transcript_ids),
            "transcript_cleared": transcript_cleared,
            "audio_candidates": len(audio_ids),
            "audio_cleared": audio_cleared,
            "event_candidates": len(event_ids),
            "event_deleted": event_deleted,
        }
        audit_id = self._repo.create_cleanup_audit_event(payload=summary)
        summary["audit_event_id"] = audit_id
        return summary
