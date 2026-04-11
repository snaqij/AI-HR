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
    assert "CREATE INDEX ix_ai_interview_turns_transcript_expires_at ON ai_interview_turns (transcript_expires_at);" in init_sql
    assert "CREATE INDEX ix_ai_interview_turns_audio_expires_at ON ai_interview_turns (audio_expires_at);" in init_sql
    assert "CREATE INDEX ix_events_occurred_at ON events (occurred_at);" in init_sql
    assert "CREATE INDEX ix_events_event_type_occurred_at ON events (event_type, occurred_at);" in init_sql


def test_db_004a_question_set_invitation_migration_should_cover_forward_and_rollback() -> None:
    forward_sql = (
        PROJECT_ROOT / "sql" / "migrations" / "20260411_ai_interview_question_sets_invitation_id.sql"
    ).read_text(encoding="utf-8")
    rollback_sql = (
        PROJECT_ROOT / "sql" / "migrations" / "20260411_ai_interview_question_sets_invitation_id_rollback.sql"
    ).read_text(encoding="utf-8")

    assert "MODIFY COLUMN session_id VARCHAR(36) NULL" in forward_sql
    assert "ADD COLUMN invitation_id VARCHAR(36) NULL AFTER session_id" in forward_sql
    assert "fk_ai_interview_question_sets_invitation_id" in forward_sql
    assert "ix_ai_interview_question_sets_invitation_id" in forward_sql
    assert "ALGORITHM=INPLACE, LOCK=NONE" in forward_sql

    assert "DROP FOREIGN KEY fk_ai_interview_question_sets_invitation_id" in rollback_sql
    assert "DROP INDEX ix_ai_interview_question_sets_invitation_id" in rollback_sql
    assert "DROP COLUMN invitation_id" in rollback_sql
    assert "MODIFY COLUMN session_id VARCHAR(36) NOT NULL" in rollback_sql
    assert "ALGORITHM=INPLACE, LOCK=NONE" in rollback_sql


def test_db_004a_question_set_invitation_columns_should_exist_in_init_mysql() -> None:
    init_sql = (PROJECT_ROOT / "sql" / "init_mysql.sql").read_text(encoding="utf-8")
    assert "session_id VARCHAR(36)," in init_sql
    assert "invitation_id VARCHAR(36)," in init_sql
    assert "FOREIGN KEY(invitation_id) REFERENCES ai_interview_invitations (id) ON DELETE CASCADE" in init_sql
    assert "CREATE INDEX ix_ai_interview_question_sets_invitation_id ON ai_interview_question_sets (invitation_id);" in init_sql
