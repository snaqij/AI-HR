-- AI-HR MySQL initialization script (aligned with current ORM models)
-- Recommended MySQL version: 8.0+

CREATE DATABASE IF NOT EXISTS `ai_hr`
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_0900_ai_ci;

USE `ai_hr`;

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

DROP TABLE IF EXISTS `ai_interview_turns`;
DROP TABLE IF EXISTS `ai_interview_reports`;
DROP TABLE IF EXISTS `ai_interview_question_sets`;
DROP TABLE IF EXISTS `ai_interview_handoffs`;
DROP TABLE IF EXISTS `job_shortlists`;
DROP TABLE IF EXISTS `job_publications`;
DROP TABLE IF EXISTS `interviews`;
DROP TABLE IF EXISTS `conversations`;
DROP TABLE IF EXISTS `candidate_resume_risks`;
DROP TABLE IF EXISTS `candidate_resume_profiles`;
DROP TABLE IF EXISTS `candidate_job_scores`;
DROP TABLE IF EXISTS `candidate_identities`;
DROP TABLE IF EXISTS `ai_interview_sessions`;
DROP TABLE IF EXISTS `jobs`;
DROP TABLE IF EXISTS `events`;
DROP TABLE IF EXISTS `candidates`;
DROP TABLE IF EXISTS `approvals`;
DROP TABLE IF EXISTS `ai_request_traces`;
DROP TABLE IF EXISTS `ai_prompt_versions`;
DROP TABLE IF EXISTS `ai_model_configs`;
DROP TABLE IF EXISTS `ai_feature_flags`;
DROP TABLE IF EXISTS `ai_eval_runs`;
DROP TABLE IF EXISTS `ai_decision_logs`;


CREATE TABLE ai_decision_logs (
	id VARCHAR(36) NOT NULL, 
	trace_id VARCHAR(64) NOT NULL, 
	module_key VARCHAR(64) NOT NULL, 
	entity_type VARCHAR(32) NOT NULL, 
	entity_id VARCHAR(36) NOT NULL, 
	confidence FLOAT, 
	risk_tags JSON NOT NULL, 
	policy_flags JSON NOT NULL, 
	action VARCHAR(32) NOT NULL, 
	input_summary TEXT, 
	output_summary TEXT, 
	provider VARCHAR(32), 
	model_name VARCHAR(128), 
	prompt_version VARCHAR(32), 
	extra_payload JSON NOT NULL, 
	created_at DATETIME NOT NULL DEFAULT now(), 
	updated_at DATETIME NOT NULL DEFAULT now(), 
	PRIMARY KEY (id)
);


CREATE TABLE ai_eval_runs (
	id VARCHAR(36) NOT NULL, 
	eval_type VARCHAR(64) NOT NULL, 
	dataset_version VARCHAR(64) NOT NULL, 
	model_version VARCHAR(128) NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	metrics JSON NOT NULL, 
	summary TEXT, 
	started_at DATETIME NOT NULL, 
	finished_at DATETIME NOT NULL, 
	created_at DATETIME NOT NULL DEFAULT now(), 
	updated_at DATETIME NOT NULL DEFAULT now(), 
	PRIMARY KEY (id)
);


CREATE TABLE ai_feature_flags (
	id VARCHAR(36) NOT NULL, 
	feature_key VARCHAR(64) NOT NULL, 
	tenant_id VARCHAR(64), 
	job_id VARCHAR(64), 
	rollout_percent INTEGER NOT NULL, 
	enabled BOOL NOT NULL, 
	fallback_mode VARCHAR(32) NOT NULL, 
	created_at DATETIME NOT NULL DEFAULT now(), 
	updated_at DATETIME NOT NULL DEFAULT now(), 
	PRIMARY KEY (id), 
	CONSTRAINT uq_ai_feature_tenant_job UNIQUE (feature_key, tenant_id, job_id)
);


CREATE TABLE ai_model_configs (
	id VARCHAR(36) NOT NULL, 
	task_key VARCHAR(64) NOT NULL, 
	provider VARCHAR(32) NOT NULL, 
	model_name VARCHAR(128) NOT NULL, 
	temperature_milli INTEGER NOT NULL, 
	timeout_seconds INTEGER NOT NULL, 
	max_retries INTEGER NOT NULL, 
	is_active BOOL NOT NULL, 
	weight INTEGER NOT NULL, 
	created_at DATETIME NOT NULL DEFAULT now(), 
	updated_at DATETIME NOT NULL DEFAULT now(), 
	PRIMARY KEY (id)
);


CREATE TABLE ai_prompt_versions (
	id VARCHAR(36) NOT NULL, 
	task_key VARCHAR(64) NOT NULL, 
	version VARCHAR(32) NOT NULL, 
	system_prompt TEXT NOT NULL, 
	user_template TEXT NOT NULL, 
	output_schema JSON NOT NULL, 
	is_active BOOL NOT NULL, 
	created_by VARCHAR(64), 
	created_at DATETIME NOT NULL DEFAULT now(), 
	updated_at DATETIME NOT NULL DEFAULT now(), 
	PRIMARY KEY (id), 
	CONSTRAINT uq_ai_prompt_task_version UNIQUE (task_key, version)
);


CREATE TABLE ai_request_traces (
	id VARCHAR(36) NOT NULL, 
	trace_id VARCHAR(64) NOT NULL, 
	task_key VARCHAR(64) NOT NULL, 
	provider VARCHAR(32) NOT NULL, 
	model_name VARCHAR(128) NOT NULL, 
	prompt_version VARCHAR(32) NOT NULL, 
	request_hash VARCHAR(64) NOT NULL, 
	response_status VARCHAR(32) NOT NULL, 
	latency_ms INTEGER NOT NULL, 
	input_tokens INTEGER, 
	output_tokens INTEGER, 
	cost_usd FLOAT, 
	retry_count INTEGER NOT NULL, 
	fallback_used INTEGER NOT NULL, 
	finished_at DATETIME NOT NULL, 
	created_at DATETIME NOT NULL DEFAULT now(), 
	updated_at DATETIME NOT NULL DEFAULT now(), 
	PRIMARY KEY (id)
);


CREATE TABLE approvals (
	id VARCHAR(36) NOT NULL, 
	action_type VARCHAR(64) NOT NULL, 
	entity_type VARCHAR(64) NOT NULL, 
	entity_id VARCHAR(36) NOT NULL, 
	requested_by VARCHAR(64) NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	reason TEXT, 
	payload JSON NOT NULL, 
	decided_by VARCHAR(64), 
	decided_at DATETIME, 
	created_at DATETIME NOT NULL DEFAULT now(), 
	updated_at DATETIME NOT NULL DEFAULT now(), 
	PRIMARY KEY (id)
);


CREATE TABLE candidates (
	id VARCHAR(36) NOT NULL, 
	name VARCHAR(255) NOT NULL, 
	source_channel VARCHAR(64) NOT NULL, 
	external_candidate_id VARCHAR(128) NOT NULL, 
	phone_hash VARCHAR(255), 
	email_hash VARCHAR(255), 
	resume_url TEXT, 
	resume_text TEXT, 
	current_stage VARCHAR(32) NOT NULL, 
	raw_profile JSON NOT NULL, 
	score_total FLOAT, 
	score_dimensions JSON NOT NULL, 
	score_explanation TEXT, 
	scored_at DATETIME, 
	created_at DATETIME NOT NULL DEFAULT now(), 
	updated_at DATETIME NOT NULL DEFAULT now(), 
	PRIMARY KEY (id)
);


CREATE TABLE events (
	id VARCHAR(36) NOT NULL, 
	event_type VARCHAR(64) NOT NULL, 
	entity_type VARCHAR(64) NOT NULL, 
	entity_id VARCHAR(36) NOT NULL, 
	channel VARCHAR(64), 
	operator VARCHAR(64), 
	session_id VARCHAR(36), 
	job_id VARCHAR(36), 
	status VARCHAR(32) NOT NULL, 
	occurred_at DATETIME NOT NULL DEFAULT now(), 
	payload JSON NOT NULL, 
	created_at DATETIME NOT NULL DEFAULT now(), 
	updated_at DATETIME NOT NULL DEFAULT now(), 
	PRIMARY KEY (id)
);


CREATE TABLE jobs (
	id VARCHAR(36) NOT NULL, 
	title VARCHAR(255) NOT NULL, 
	department VARCHAR(255), 
	city VARCHAR(128) NOT NULL, 
	salary_range VARCHAR(128), 
	requirements TEXT NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	published_at DATETIME, 
	created_at DATETIME NOT NULL DEFAULT now(), 
	updated_at DATETIME NOT NULL DEFAULT now(), 
	PRIMARY KEY (id)
);


CREATE TABLE ai_interview_sessions (
	id VARCHAR(36) NOT NULL, 
	candidate_id VARCHAR(36) NOT NULL, 
	job_id VARCHAR(36) NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	channel VARCHAR(64) NOT NULL, 
	language VARCHAR(16) NOT NULL, 
	rtc_room_id VARCHAR(128) NOT NULL, 
	join_token VARCHAR(512) NOT NULL, 
	started_at DATETIME, 
	ended_at DATETIME, 
	payload JSON NOT NULL, 
	note TEXT, 
	created_at DATETIME NOT NULL DEFAULT now(), 
	updated_at DATETIME NOT NULL DEFAULT now(), 
	PRIMARY KEY (id), 
	FOREIGN KEY(candidate_id) REFERENCES candidates (id) ON DELETE CASCADE, 
	FOREIGN KEY(job_id) REFERENCES jobs (id) ON DELETE CASCADE, 
	UNIQUE (rtc_room_id), 
	UNIQUE (join_token)
);


CREATE TABLE candidate_identities (
	id VARCHAR(36) NOT NULL, 
	candidate_id VARCHAR(36) NOT NULL, 
	source_channel VARCHAR(64) NOT NULL, 
	external_candidate_id VARCHAR(128) NOT NULL, 
	created_at DATETIME NOT NULL DEFAULT now(), 
	updated_at DATETIME NOT NULL DEFAULT now(), 
	PRIMARY KEY (id), 
	CONSTRAINT uq_identity_source_external_id UNIQUE (source_channel, external_candidate_id), 
	FOREIGN KEY(candidate_id) REFERENCES candidates (id) ON DELETE CASCADE
);


CREATE TABLE candidate_job_scores (
	id VARCHAR(36) NOT NULL, 
	candidate_id VARCHAR(36) NOT NULL, 
	job_id VARCHAR(36) NOT NULL, 
	total_score FLOAT NOT NULL, 
	dimension_scores JSON NOT NULL, 
	explanation TEXT NOT NULL, 
	risk_tags JSON NOT NULL, 
	score_version VARCHAR(64) NOT NULL, 
	scored_at DATETIME NOT NULL, 
	created_at DATETIME NOT NULL DEFAULT now(), 
	updated_at DATETIME NOT NULL DEFAULT now(), 
	PRIMARY KEY (id), 
	CONSTRAINT uq_candidate_job_score UNIQUE (candidate_id, job_id), 
	FOREIGN KEY(candidate_id) REFERENCES candidates (id) ON DELETE CASCADE, 
	FOREIGN KEY(job_id) REFERENCES jobs (id) ON DELETE CASCADE
);


CREATE TABLE candidate_resume_profiles (
	id VARCHAR(36) NOT NULL, 
	candidate_id VARCHAR(36) NOT NULL, 
	raw_text TEXT NOT NULL, 
	parsed_json JSON NOT NULL, 
	normalized_json JSON NOT NULL, 
	parse_status VARCHAR(32) NOT NULL, 
	parser_version VARCHAR(64) NOT NULL, 
	confidence FLOAT NOT NULL, 
	created_at DATETIME NOT NULL DEFAULT now(), 
	updated_at DATETIME NOT NULL DEFAULT now(), 
	PRIMARY KEY (id), 
	CONSTRAINT uq_resume_profile_candidate_id UNIQUE (candidate_id), 
	FOREIGN KEY(candidate_id) REFERENCES candidates (id) ON DELETE CASCADE
);


CREATE TABLE candidate_resume_risks (
	id VARCHAR(36) NOT NULL, 
	candidate_id VARCHAR(36) NOT NULL, 
	risk_code VARCHAR(64) NOT NULL, 
	risk_level VARCHAR(16) NOT NULL, 
	detail TEXT NOT NULL, 
	created_at DATETIME NOT NULL DEFAULT now(), 
	updated_at DATETIME NOT NULL DEFAULT now(), 
	PRIMARY KEY (id), 
	FOREIGN KEY(candidate_id) REFERENCES candidates (id) ON DELETE CASCADE
);


CREATE TABLE conversations (
	id VARCHAR(36) NOT NULL, 
	candidate_id VARCHAR(36) NOT NULL, 
	channel VARCHAR(64) NOT NULL, 
	external_conversation_id VARCHAR(128) NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	last_message_at DATETIME, 
	context_payload JSON NOT NULL, 
	created_at DATETIME NOT NULL DEFAULT now(), 
	updated_at DATETIME NOT NULL DEFAULT now(), 
	PRIMARY KEY (id), 
	CONSTRAINT uq_conversation_channel_external_id UNIQUE (channel, external_conversation_id), 
	FOREIGN KEY(candidate_id) REFERENCES candidates (id) ON DELETE CASCADE
);


CREATE TABLE interviews (
	id VARCHAR(36) NOT NULL, 
	candidate_id VARCHAR(36) NOT NULL, 
	job_id VARCHAR(36) NOT NULL, 
	channel VARCHAR(64) NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	scheduled_at DATETIME, 
	meeting_link TEXT, 
	external_interview_id VARCHAR(128), 
	target_headcount INTEGER, 
	payload JSON NOT NULL, 
	created_at DATETIME NOT NULL DEFAULT now(), 
	updated_at DATETIME NOT NULL DEFAULT now(), 
	PRIMARY KEY (id), 
	FOREIGN KEY(candidate_id) REFERENCES candidates (id) ON DELETE CASCADE, 
	FOREIGN KEY(job_id) REFERENCES jobs (id) ON DELETE CASCADE
);


CREATE TABLE job_publications (
	id VARCHAR(36) NOT NULL, 
	job_id VARCHAR(36) NOT NULL, 
	channel VARCHAR(64) NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	external_job_id VARCHAR(128), 
	error_message TEXT, 
	request_payload JSON NOT NULL, 
	response_payload JSON NOT NULL, 
	published_at DATETIME, 
	last_synced_at DATETIME, 
	applicant_sync_cursor VARCHAR(255), 
	created_at DATETIME NOT NULL DEFAULT now(), 
	updated_at DATETIME NOT NULL DEFAULT now(), 
	PRIMARY KEY (id), 
	FOREIGN KEY(job_id) REFERENCES jobs (id) ON DELETE CASCADE
);


CREATE TABLE job_shortlists (
	id VARCHAR(36) NOT NULL, 
	job_id VARCHAR(36) NOT NULL, 
	candidate_id VARCHAR(36) NOT NULL, 
	`rank` INTEGER NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	created_at DATETIME NOT NULL DEFAULT now(), 
	updated_at DATETIME NOT NULL DEFAULT now(), 
	PRIMARY KEY (id), 
	CONSTRAINT uq_job_shortlist_candidate UNIQUE (job_id, candidate_id), 
	FOREIGN KEY(job_id) REFERENCES jobs (id) ON DELETE CASCADE, 
	FOREIGN KEY(candidate_id) REFERENCES candidates (id) ON DELETE CASCADE
);


CREATE TABLE ai_interview_handoffs (
	id VARCHAR(36) NOT NULL, 
	session_id VARCHAR(36) NOT NULL, 
	reason VARCHAR(128) NOT NULL, 
	trigger_flags JSON NOT NULL, 
	operator VARCHAR(64) NOT NULL, 
	note TEXT, 
	payload JSON NOT NULL, 
	created_at DATETIME NOT NULL DEFAULT now(), 
	updated_at DATETIME NOT NULL DEFAULT now(), 
	PRIMARY KEY (id), 
	FOREIGN KEY(session_id) REFERENCES ai_interview_sessions (id) ON DELETE CASCADE
);


CREATE TABLE ai_interview_question_sets (
	id VARCHAR(36) NOT NULL, 
	session_id VARCHAR(36), 
	invitation_id VARCHAR(36), 
	version INTEGER NOT NULL, 
	source VARCHAR(64) NOT NULL, 
	questions_json JSON NOT NULL, 
	created_at DATETIME NOT NULL DEFAULT now(), 
	updated_at DATETIME NOT NULL DEFAULT now(), 
	PRIMARY KEY (id), 
	FOREIGN KEY(session_id) REFERENCES ai_interview_sessions (id) ON DELETE CASCADE,
	FOREIGN KEY(invitation_id) REFERENCES ai_interview_invitations (id) ON DELETE CASCADE
);


CREATE TABLE ai_interview_reports (
	id VARCHAR(36) NOT NULL, 
	session_id VARCHAR(36) NOT NULL, 
	report_version INTEGER NOT NULL, 
	summary TEXT NOT NULL, 
	dimension_scores_json JSON NOT NULL, 
	risk_tags_json JSON NOT NULL, 
	recommendation VARCHAR(32) NOT NULL, 
	payload JSON NOT NULL, 
	created_at DATETIME NOT NULL DEFAULT now(), 
	updated_at DATETIME NOT NULL DEFAULT now(), 
	PRIMARY KEY (id), 
	FOREIGN KEY(session_id) REFERENCES ai_interview_sessions (id) ON DELETE CASCADE
);


CREATE TABLE ai_interview_turns (
	id VARCHAR(36) NOT NULL, 
	session_id VARCHAR(36) NOT NULL, 
	turn_no INTEGER NOT NULL, 
	speaker VARCHAR(32) NOT NULL, 
	transcript TEXT, 
	audio_uri TEXT, 
	transcript_expires_at DATETIME, 
	audio_expires_at DATETIME, 
	confidence FLOAT, 
	latency_ms INTEGER, 
	policy_flags JSON NOT NULL, 
	payload JSON NOT NULL, 
	created_at DATETIME NOT NULL DEFAULT now(), 
	updated_at DATETIME NOT NULL DEFAULT now(), 
	PRIMARY KEY (id), 
	FOREIGN KEY(session_id) REFERENCES ai_interview_sessions (id) ON DELETE CASCADE
);

CREATE INDEX ix_ai_decision_logs_trace_id ON ai_decision_logs (trace_id);
CREATE INDEX ix_ai_decision_logs_entity_id ON ai_decision_logs (entity_id);
CREATE INDEX ix_ai_decision_logs_entity_type ON ai_decision_logs (entity_type);
CREATE INDEX ix_ai_decision_logs_module_key ON ai_decision_logs (module_key);

CREATE INDEX ix_ai_eval_runs_eval_type ON ai_eval_runs (eval_type);

CREATE INDEX ix_ai_feature_flags_feature_key ON ai_feature_flags (feature_key);
CREATE INDEX ix_ai_feature_flags_job_id ON ai_feature_flags (job_id);

CREATE INDEX ix_ai_model_configs_is_active ON ai_model_configs (is_active);
CREATE INDEX ix_ai_model_configs_task_key ON ai_model_configs (task_key);

CREATE INDEX ix_ai_prompt_versions_is_active ON ai_prompt_versions (is_active);
CREATE INDEX ix_ai_prompt_versions_task_key ON ai_prompt_versions (task_key);

CREATE INDEX ix_ai_request_traces_task_key ON ai_request_traces (task_key);
CREATE INDEX ix_ai_request_traces_trace_id ON ai_request_traces (trace_id);

CREATE INDEX ix_approvals_entity_type ON approvals (entity_type);
CREATE INDEX ix_approvals_action_type ON approvals (action_type);
CREATE INDEX ix_approvals_entity_id ON approvals (entity_id);

CREATE INDEX ix_events_entity_type ON events (entity_type);
CREATE INDEX ix_events_operator ON events (operator);
CREATE INDEX ix_events_job_id ON events (job_id);
CREATE INDEX ix_events_entity_id ON events (entity_id);
CREATE INDEX ix_events_event_type ON events (event_type);
CREATE INDEX ix_events_session_id ON events (session_id);

CREATE INDEX ix_ai_interview_sessions_candidate_created ON ai_interview_sessions (candidate_id, created_at);
CREATE INDEX ix_ai_interview_sessions_candidate_id ON ai_interview_sessions (candidate_id);
CREATE INDEX ix_ai_interview_sessions_job_created ON ai_interview_sessions (job_id, created_at);
CREATE INDEX ix_ai_interview_sessions_job_id ON ai_interview_sessions (job_id);

CREATE INDEX ix_candidate_identities_candidate_id ON candidate_identities (candidate_id);

CREATE INDEX ix_candidate_job_scores_candidate_id ON candidate_job_scores (candidate_id);
CREATE INDEX ix_candidate_job_scores_job_id ON candidate_job_scores (job_id);

CREATE INDEX ix_candidate_resume_profiles_candidate_id ON candidate_resume_profiles (candidate_id);

CREATE INDEX ix_candidate_resume_risks_candidate_id ON candidate_resume_risks (candidate_id);

CREATE INDEX ix_conversations_candidate_id ON conversations (candidate_id);

CREATE INDEX ix_interviews_candidate_id ON interviews (candidate_id);
CREATE INDEX ix_interviews_job_id ON interviews (job_id);

CREATE INDEX ix_job_publications_job_id ON job_publications (job_id);

CREATE INDEX ix_job_shortlists_candidate_id ON job_shortlists (candidate_id);
CREATE INDEX ix_job_shortlists_job_id ON job_shortlists (job_id);

CREATE INDEX ix_ai_interview_handoffs_session_id ON ai_interview_handoffs (session_id);

CREATE INDEX ix_ai_interview_question_sets_session_id ON ai_interview_question_sets (session_id);
CREATE INDEX ix_ai_interview_question_sets_invitation_id ON ai_interview_question_sets (invitation_id);

CREATE INDEX ix_ai_interview_reports_session_id ON ai_interview_reports (session_id);

CREATE INDEX ix_ai_interview_turns_session_id ON ai_interview_turns (session_id);
CREATE INDEX ix_ai_interview_turns_session_turn ON ai_interview_turns (session_id, turn_no);
CREATE INDEX ix_ai_interview_turns_session_created ON ai_interview_turns (session_id, created_at);
CREATE INDEX ix_ai_interview_turns_transcript_expires_at ON ai_interview_turns (transcript_expires_at);
CREATE INDEX ix_ai_interview_turns_audio_expires_at ON ai_interview_turns (audio_expires_at);

CREATE INDEX ix_events_occurred_at ON events (occurred_at);
CREATE INDEX ix_events_event_type_occurred_at ON events (event_type, occurred_at);

SET FOREIGN_KEY_CHECKS = 1;
