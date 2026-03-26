-- Patch: enlarge ai_interview_sessions.join_token to fit LiveKit JWT.
-- Execute on existing ai_hr database.

USE `ai_hr`;

ALTER TABLE `ai_interview_sessions`
  MODIFY COLUMN `join_token` VARCHAR(512) NOT NULL;

