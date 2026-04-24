-- =========================================================
-- AI-HR Business Data Cleanup (Keep System Data)
-- File: clear_business_data_keep_system_mysql8.sql
-- Usage:
--   1) USE <your_db>;
--   2) Review preserved tables below;
--   3) Execute in MySQL 8.0.
--
-- Preserved "system" tables:
--   - platform_users
--   - platform_user_sessions
--   - platform_email_verification_codes
--   - team_workspaces
--   - team_workspace_members
--   - channel_credentials
--   - ai_feature_flags
--   - ai_model_configs
--   - ai_prompt_versions
--   - decision_policy_versions
--   - email_templates
--
-- Everything else below is treated as business/runtime data and will be deleted.
-- =========================================================

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

START TRANSACTION;

-- ---------------------------------------------------------
-- 0) Optional preview
-- ---------------------------------------------------------
SELECT 'jobs' AS tbl, COUNT(*) AS cnt FROM jobs
UNION ALL SELECT 'job_publications', COUNT(*) FROM job_publications
UNION ALL SELECT 'job_candidates', COUNT(*) FROM job_candidates
UNION ALL SELECT 'candidate_job_pipeline', COUNT(*) FROM candidate_job_pipeline
UNION ALL SELECT 'candidate_job_evaluations', COUNT(*) FROM candidate_job_evaluations
UNION ALL SELECT 'candidates', COUNT(*) FROM candidates
UNION ALL SELECT 'candidate_identities', COUNT(*) FROM candidate_identities
UNION ALL SELECT 'candidate_resume_profiles', COUNT(*) FROM candidate_resume_profiles
UNION ALL SELECT 'candidate_resume_attachments', COUNT(*) FROM candidate_resume_attachments
UNION ALL SELECT 'candidate_resume_access_retries', COUNT(*) FROM candidate_resume_access_retries
UNION ALL SELECT 'candidate_resume_risks', COUNT(*) FROM candidate_resume_risks
UNION ALL SELECT 'candidate_email_deliveries', COUNT(*) FROM candidate_email_deliveries
UNION ALL SELECT 'interviews', COUNT(*) FROM interviews
UNION ALL SELECT 'conversations', COUNT(*) FROM conversations
UNION ALL SELECT 'job_sync_tasks', COUNT(*) FROM job_sync_tasks
UNION ALL SELECT 'job_sync_runs', COUNT(*) FROM job_sync_runs
UNION ALL SELECT 'events', COUNT(*) FROM events
UNION ALL SELECT 'agent_runs', COUNT(*) FROM agent_runs
UNION ALL SELECT 'agent_events', COUNT(*) FROM agent_events;

-- ---------------------------------------------------------
-- 1) Clear deep runtime / audit / async execution data
-- ---------------------------------------------------------
DELETE FROM ai_interview_answer_scores;
DELETE FROM ai_interview_answer_records;
DELETE FROM ai_interview_turns;
DELETE FROM ai_interview_handoffs;
DELETE FROM ai_interview_reports;
DELETE FROM ai_interview_question_attempts;
DELETE FROM ai_interview_question_sets;
DELETE FROM ai_interview_assessments;
DELETE FROM ai_interview_invitations;
DELETE FROM ai_interview_sessions;

DELETE FROM ai_eval_runs;
DELETE FROM ai_request_traces;
DELETE FROM ai_decision_logs;
DELETE FROM decision_events;
DELETE FROM review_queue_tasks;
DELETE FROM approvals;
DELETE FROM automation_task_logs;
DELETE FROM agent_events;
DELETE FROM agent_runs;
DELETE FROM events;

-- ---------------------------------------------------------
-- 2) Clear candidate/job derived business data
-- ---------------------------------------------------------
DELETE FROM candidate_composite_assessments;
DELETE FROM candidate_job_scores;
DELETE FROM candidate_job_evaluations;
DELETE FROM candidate_job_pipeline;
DELETE FROM candidate_email_deliveries;

DELETE FROM candidate_resume_risks;
DELETE FROM candidate_resume_access_retries;
DELETE FROM candidate_resume_attachments;
DELETE FROM candidate_resume_profiles;

DELETE FROM candidate_identities;
DELETE FROM conversations;
DELETE FROM interviews;
DELETE FROM job_shortlists;
DELETE FROM job_candidates;

-- ---------------------------------------------------------
-- 3) Clear job sync / publishing business data
-- ---------------------------------------------------------
DELETE FROM job_sync_runs;
DELETE FROM job_sync_tasks;
DELETE FROM job_publications;
DELETE FROM job_market_snapshots;

-- ---------------------------------------------------------
-- 4) Clear master business entities last
-- ---------------------------------------------------------
DELETE FROM candidates;
DELETE FROM jobs;

COMMIT;

SET FOREIGN_KEY_CHECKS = 1;

-- ---------------------------------------------------------
-- 5) Post-check
-- ---------------------------------------------------------
SELECT 'jobs' AS tbl, COUNT(*) AS cnt FROM jobs
UNION ALL SELECT 'job_publications', COUNT(*) FROM job_publications
UNION ALL SELECT 'job_candidates', COUNT(*) FROM job_candidates
UNION ALL SELECT 'candidate_job_pipeline', COUNT(*) FROM candidate_job_pipeline
UNION ALL SELECT 'candidate_job_evaluations', COUNT(*) FROM candidate_job_evaluations
UNION ALL SELECT 'candidates', COUNT(*) FROM candidates
UNION ALL SELECT 'candidate_identities', COUNT(*) FROM candidate_identities
UNION ALL SELECT 'candidate_resume_profiles', COUNT(*) FROM candidate_resume_profiles
UNION ALL SELECT 'candidate_resume_attachments', COUNT(*) FROM candidate_resume_attachments
UNION ALL SELECT 'candidate_resume_access_retries', COUNT(*) FROM candidate_resume_access_retries
UNION ALL SELECT 'candidate_resume_risks', COUNT(*) FROM candidate_resume_risks
UNION ALL SELECT 'candidate_email_deliveries', COUNT(*) FROM candidate_email_deliveries
UNION ALL SELECT 'interviews', COUNT(*) FROM interviews
UNION ALL SELECT 'conversations', COUNT(*) FROM conversations
UNION ALL SELECT 'job_sync_tasks', COUNT(*) FROM job_sync_tasks
UNION ALL SELECT 'job_sync_runs', COUNT(*) FROM job_sync_runs
UNION ALL SELECT 'events', COUNT(*) FROM events
UNION ALL SELECT 'agent_runs', COUNT(*) FROM agent_runs
UNION ALL SELECT 'agent_events', COUNT(*) FROM agent_events;
