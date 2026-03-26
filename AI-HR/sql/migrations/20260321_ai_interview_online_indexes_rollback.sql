-- DB-002A rollback: AI 面试模块在线索引回滚（MySQL 8.0+）
-- 说明：
-- 1) 使用 INFORMATION_SCHEMA 做幂等检查；
-- 2) 使用 ALGORITHM=INPLACE, LOCK=NONE 减少锁影响；
-- 3) 仅在确认需要回滚索引时执行。
SET @db := DATABASE();

-- ai_interview_turns.transcript_expires_at
SET @idx_exists := (
  SELECT COUNT(1)
  FROM information_schema.statistics
  WHERE table_schema = @db
    AND table_name = 'ai_interview_turns'
    AND index_name = 'ix_ai_interview_turns_transcript_expires_at'
);
SET @ddl := IF(
  @idx_exists > 0,
  'ALTER TABLE ai_interview_turns DROP INDEX ix_ai_interview_turns_transcript_expires_at, ALGORITHM=INPLACE, LOCK=NONE',
  'SELECT "skip drop ix_ai_interview_turns_transcript_expires_at"'
);
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- ai_interview_turns.audio_expires_at
SET @idx_exists := (
  SELECT COUNT(1)
  FROM information_schema.statistics
  WHERE table_schema = @db
    AND table_name = 'ai_interview_turns'
    AND index_name = 'ix_ai_interview_turns_audio_expires_at'
);
SET @ddl := IF(
  @idx_exists > 0,
  'ALTER TABLE ai_interview_turns DROP INDEX ix_ai_interview_turns_audio_expires_at, ALGORITHM=INPLACE, LOCK=NONE',
  'SELECT "skip drop ix_ai_interview_turns_audio_expires_at"'
);
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- events.occurred_at
SET @idx_exists := (
  SELECT COUNT(1)
  FROM information_schema.statistics
  WHERE table_schema = @db
    AND table_name = 'events'
    AND index_name = 'ix_events_occurred_at'
);
SET @ddl := IF(
  @idx_exists > 0,
  'ALTER TABLE events DROP INDEX ix_events_occurred_at, ALGORITHM=INPLACE, LOCK=NONE',
  'SELECT "skip drop ix_events_occurred_at"'
);
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- events.event_type + occurred_at
SET @idx_exists := (
  SELECT COUNT(1)
  FROM information_schema.statistics
  WHERE table_schema = @db
    AND table_name = 'events'
    AND index_name = 'ix_events_event_type_occurred_at'
);
SET @ddl := IF(
  @idx_exists > 0,
  'ALTER TABLE events DROP INDEX ix_events_event_type_occurred_at, ALGORITHM=INPLACE, LOCK=NONE',
  'SELECT "skip drop ix_events_event_type_occurred_at"'
);
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
