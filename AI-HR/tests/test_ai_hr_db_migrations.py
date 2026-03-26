from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_db_002a_online_index_migration_should_cover_forward_and_rollback() -> None:
    forward_sql = (
        PROJECT_ROOT / "sql" / "migrations" / "20260321_ai_interview_online_indexes.sql"
    ).read_text(encoding="utf-8")
    rollback_sql = (
        PROJECT_ROOT / "sql" / "migrations" / "20260321_ai_interview_online_indexes_rollback.sql"
    ).read_text(encoding="utf-8")

    assert "ix_ai_interview_turns_transcript_expires_at" in forward_sql
    assert "ix_ai_interview_turns_audio_expires_at" in forward_sql
    assert "ix_events_occurred_at" in forward_sql
    assert "ix_events_event_type_occurred_at" in forward_sql
    assert "ALGORITHM=INPLACE, LOCK=NONE" in forward_sql

    assert "DROP INDEX ix_ai_interview_turns_transcript_expires_at" in rollback_sql
    assert "DROP INDEX ix_ai_interview_turns_audio_expires_at" in rollback_sql
    assert "DROP INDEX ix_events_occurred_at" in rollback_sql
    assert "DROP INDEX ix_events_event_type_occurred_at" in rollback_sql
    assert "ALGORITHM=INPLACE, LOCK=NONE" in rollback_sql


def test_db_002a_indexes_should_exist_in_init_mysql() -> None:
    init_sql = (PROJECT_ROOT / "sql" / "init_mysql.sql").read_text(encoding="utf-8")
    assert "KEY `ix_ai_interview_turns_transcript_expires_at` (`transcript_expires_at`)" in init_sql
    assert "KEY `ix_ai_interview_turns_audio_expires_at` (`audio_expires_at`)" in init_sql
    assert "KEY `ix_events_occurred_at` (`occurred_at`)" in init_sql
    assert "KEY `ix_events_event_type_occurred_at` (`event_type`, `occurred_at`)" in init_sql
