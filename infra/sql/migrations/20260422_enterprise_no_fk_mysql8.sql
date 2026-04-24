-- =========================================================
-- AI-HR Enterprise Upgrade (No Foreign Keys, MySQL 8.0)
-- File: 20260422_enterprise_no_fk_mysql8.sql
-- Notes:
-- 1) Run after selecting target schema: USE <your_db>;
-- 2) This script is idempotent for CREATE/ALTER operations.
-- 3) No FK constraints are created by design.
-- =========================================================

SET NAMES utf8mb4;

-- ---------------------------------------------------------
-- 0) Idempotent helpers (column/index existence checks)
-- ---------------------------------------------------------
DELIMITER $$

DROP PROCEDURE IF EXISTS `sp_exec_if`$$
CREATE PROCEDURE `sp_exec_if`(
    IN p_cond TINYINT,
    IN p_sql LONGTEXT
)
BEGIN
    IF p_cond = 1 THEN
        SET @dyn_sql := p_sql;
        PREPARE stmt FROM @dyn_sql;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;
    END IF;
END$$

DROP PROCEDURE IF EXISTS `sp_add_column_if_missing`$$
CREATE PROCEDURE `sp_add_column_if_missing`(
    IN p_schema VARCHAR(64),
    IN p_table  VARCHAR(64),
    IN p_column VARCHAR(64),
    IN p_ddl    LONGTEXT
)
BEGIN
    DECLARE v_exists INT DEFAULT 0;
    SELECT COUNT(1)
      INTO v_exists
      FROM information_schema.columns
     WHERE table_schema = p_schema
       AND table_name = p_table
       AND column_name = p_column;

    CALL sp_exec_if(v_exists = 0, p_ddl);
END$$

DROP PROCEDURE IF EXISTS `sp_add_index_if_missing`$$
CREATE PROCEDURE `sp_add_index_if_missing`(
    IN p_schema VARCHAR(64),
    IN p_table  VARCHAR(64),
    IN p_index  VARCHAR(64),
    IN p_ddl    LONGTEXT
)
BEGIN
    DECLARE v_exists INT DEFAULT 0;
    SELECT COUNT(1)
      INTO v_exists
      FROM information_schema.statistics
     WHERE table_schema = p_schema
       AND table_name = p_table
       AND index_name = p_index;

    CALL sp_exec_if(v_exists = 0, p_ddl);
END$$

DELIMITER ;

-- ---------------------------------------------------------
-- 1) Enterprise auth & workspace tables (no-FK)
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS `platform_users` (
  `id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
  `email` varchar(320) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
  `email_normalized` varchar(320) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
  `mobile_e164` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL,
  `display_name` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
  `avatar_url` varchar(1024) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL,
  `password_hash` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
  `password_algo` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT 'argon2id',
  `status` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT 'active',
  `email_verified` tinyint(1) NOT NULL DEFAULT 0,
  `mobile_verified` tinyint(1) NOT NULL DEFAULT 0,
  `password_updated_at` datetime NULL DEFAULT NULL,
  `last_login_at` datetime NULL DEFAULT NULL,
  `last_login_ip` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL,
  `profile_json` json NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uk_platform_users_email_normalized`(`email_normalized` ASC) USING BTREE,
  INDEX `idx_platform_users_status`(`status` ASC) USING BTREE,
  INDEX `idx_platform_users_last_login_at`(`last_login_at` ASC) USING BTREE
) ENGINE=InnoDB CHARACTER SET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `platform_user_sessions` (
  `id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
  `user_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
  `session_token_hash` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
  `refresh_token_hash` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
  `device_id` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL,
  `user_agent` varchar(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL,
  `ip` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL,
  `status` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT 'active',
  `expires_at` datetime NOT NULL,
  `rotated_at` datetime NULL DEFAULT NULL,
  `revoked_at` datetime NULL DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uk_platform_user_sessions_session_token_hash`(`session_token_hash` ASC) USING BTREE,
  UNIQUE INDEX `uk_platform_user_sessions_refresh_token_hash`(`refresh_token_hash` ASC) USING BTREE,
  INDEX `idx_platform_user_sessions_user_status`(`user_id` ASC, `status` ASC) USING BTREE,
  INDEX `idx_platform_user_sessions_expires_at`(`expires_at` ASC) USING BTREE
) ENGINE=InnoDB CHARACTER SET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `platform_email_verification_codes` (
  `id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
  `email` varchar(320) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
  `email_normalized` varchar(320) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
  `purpose` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
  `code_hash` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
  `status` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT 'active',
  `expires_at` datetime NOT NULL,
  `sent_at` datetime NULL DEFAULT NULL,
  `consumed_at` datetime NULL DEFAULT NULL,
  `last_attempt_at` datetime NULL DEFAULT NULL,
  `attempt_count` int NOT NULL DEFAULT 0,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_platform_email_verification_email_purpose`(`email_normalized` ASC, `purpose` ASC) USING BTREE,
  INDEX `idx_platform_email_verification_status_expires`(`status` ASC, `expires_at` ASC) USING BTREE
) ENGINE=InnoDB CHARACTER SET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `platform_user_mfa_methods` (
  `id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
  `user_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
  `method_type` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
  `secret_ciphertext` text CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL,
  `phone_masked` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL,
  `email_masked` varchar(320) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL,
  `is_primary` tinyint(1) NOT NULL DEFAULT 0,
  `status` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT 'active',
  `last_verified_at` datetime NULL DEFAULT NULL,
  `payload` json NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uk_platform_user_mfa_user_method`(`user_id` ASC, `method_type` ASC) USING BTREE,
  INDEX `idx_platform_user_mfa_status`(`status` ASC) USING BTREE
) ENGINE=InnoDB CHARACTER SET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `team_workspaces` (
  `id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `workspace_code` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `name` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `owner_user_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `plan_code` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pro',
  `status` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'active',
  `settings_json` json NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uk_team_workspaces_workspace_code`(`workspace_code` ASC) USING BTREE,
  INDEX `idx_team_workspaces_owner_user`(`owner_user_id` ASC) USING BTREE,
  INDEX `idx_team_workspaces_status`(`status` ASC) USING BTREE
) ENGINE=InnoDB CHARACTER SET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `team_workspace_members` (
  `id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `workspace_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `user_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `role` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'recruiter',
  `status` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'active',
  `invited_by_user_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL,
  `joined_at` datetime NULL DEFAULT NULL,
  `last_active_at` datetime NULL DEFAULT NULL,
  `permissions_json` json NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uk_team_workspace_members_workspace_user`(`workspace_id` ASC, `user_id` ASC) USING BTREE,
  INDEX `idx_team_workspace_members_user_status`(`user_id` ASC, `status` ASC) USING BTREE,
  INDEX `idx_team_workspace_members_workspace_role`(`workspace_id` ASC, `role` ASC) USING BTREE
) ENGINE=InnoDB CHARACTER SET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `team_workspace_invitations` (
  `id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `workspace_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `email_normalized` varchar(320) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `role` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'recruiter',
  `token_hash` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `status` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending',
  `invited_by_user_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `accepted_by_user_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL,
  `expires_at` datetime NOT NULL,
  `accepted_at` datetime NULL DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uk_team_workspace_invitations_token_hash`(`token_hash` ASC) USING BTREE,
  INDEX `idx_team_workspace_invitations_workspace_status`(`workspace_id` ASC, `status` ASC) USING BTREE,
  INDEX `idx_team_workspace_invitations_email_status`(`email_normalized` ASC, `status` ASC) USING BTREE,
  INDEX `idx_team_workspace_invitations_expires_at`(`expires_at` ASC) USING BTREE
) ENGINE=InnoDB CHARACTER SET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `team_workspace_audit_logs` (
  `id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `workspace_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `actor_user_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `action` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `resource_type` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `resource_id` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL,
  `trace_id` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL,
  `payload` json NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_team_workspace_audit_workspace_created`(`workspace_id` ASC, `created_at` ASC) USING BTREE,
  INDEX `idx_team_workspace_audit_actor_created`(`actor_user_id` ASC, `created_at` ASC) USING BTREE,
  INDEX `idx_team_workspace_audit_trace_id`(`trace_id` ASC) USING BTREE
) ENGINE=InnoDB CHARACTER SET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------
-- 2) Interview/composite assessment tables (no-FK)
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS `decision_policy_versions` (
  `id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `policy_code` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `version` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `status` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'draft',
  `description` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL,
  `resume_weight` decimal(8,4) NOT NULL DEFAULT 0.3500,
  `interview_weight` decimal(8,4) NOT NULL DEFAULT 0.4500,
  `market_weight` decimal(8,4) NOT NULL DEFAULT 0.1500,
  `stability_weight` decimal(8,4) NOT NULL DEFAULT 0.0500,
  `risk_penalty_weight` decimal(8,4) NOT NULL DEFAULT 0.2000,
  `hard_rules_json` json NULL,
  `threshold_rules_json` json NULL,
  `override_rules_json` json NULL,
  `formula_text` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL,
  `is_default` tinyint(1) NOT NULL DEFAULT 0,
  `effective_from` datetime NULL DEFAULT NULL,
  `effective_to` datetime NULL DEFAULT NULL,
  `created_by` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL,
  `updated_by` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uk_decision_policy_versions_policy_ver`(`policy_code` ASC, `version` ASC) USING BTREE,
  INDEX `idx_decision_policy_versions_policy_status`(`policy_code` ASC, `status` ASC) USING BTREE,
  INDEX `idx_decision_policy_versions_default`(`is_default` ASC) USING BTREE
) ENGINE=InnoDB CHARACTER SET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `ai_interview_question_attempts` (
  `id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
  `session_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
  `candidate_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
  `job_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
  `question_id` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
  `question_seq` int NOT NULL,
  `stage_code` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
  `prompt_text` text CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL,
  `asked_at` datetime NULL DEFAULT NULL,
  `answer_started_at` datetime NULL DEFAULT NULL,
  `answer_ended_at` datetime NULL DEFAULT NULL,
  `answer_turn_count` int NOT NULL DEFAULT 0,
  `answer_text` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL,
  `asr_confidence` decimal(6,4) NULL DEFAULT NULL,
  `model_confidence` decimal(6,4) NULL DEFAULT NULL,
  `evidence_density` decimal(6,4) NULL DEFAULT NULL,
  `status` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT 'pending',
  `followup_count` int NOT NULL DEFAULT 0,
  `insufficient_evidence` tinyint(1) NOT NULL DEFAULT 0,
  `invalid_reason` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL,
  `payload` json NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uk_ai_interview_question_attempts_session_seq`(`session_id` ASC, `question_seq` ASC) USING BTREE,
  INDEX `idx_ai_interview_question_attempts_question_id`(`question_id` ASC) USING BTREE,
  INDEX `idx_ai_interview_question_attempts_status`(`status` ASC) USING BTREE,
  INDEX `idx_ai_interview_question_attempts_candidate_job`(`candidate_id` ASC, `job_id` ASC) USING BTREE
) ENGINE=InnoDB CHARACTER SET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `ai_interview_assessments` (
  `id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `session_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `candidate_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `job_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `run_no` int NOT NULL DEFAULT 1,
  `status` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'draft',
  `policy_code` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'candidate_progression',
  `policy_version` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'v1.0.0',
  `interview_score` decimal(5,2) NULL DEFAULT NULL,
  `interview_confidence` decimal(6,4) NULL DEFAULT NULL,
  `coverage_rate` decimal(6,4) NULL DEFAULT NULL,
  `answered_required_questions` int NOT NULL DEFAULT 0,
  `total_required_questions` int NOT NULL DEFAULT 0,
  `dimension_scores_json` json NULL,
  `risk_tags_json` json NULL,
  `evidence_refs_json` json NULL,
  `recommendation` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL,
  `decision` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending',
  `reason_codes_json` json NULL,
  `computed_at` datetime NULL DEFAULT NULL,
  `decided_at` datetime NULL DEFAULT NULL,
  `published_at` datetime NULL DEFAULT NULL,
  `superseded_at` datetime NULL DEFAULT NULL,
  `trace_id` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL,
  `payload` json NULL,
  `created_by` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL,
  `updated_by` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uk_ai_interview_assessments_session_run`(`session_id` ASC, `run_no` ASC) USING BTREE,
  INDEX `idx_ai_interview_assessments_status`(`status` ASC) USING BTREE,
  INDEX `idx_ai_interview_assessments_candidate_job`(`candidate_id` ASC, `job_id` ASC) USING BTREE,
  INDEX `idx_ai_interview_assessments_decision`(`decision` ASC) USING BTREE,
  INDEX `idx_ai_interview_assessments_computed_at`(`computed_at` ASC) USING BTREE
) ENGINE=InnoDB CHARACTER SET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `ai_interview_assessment_questions` (
  `id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `assessment_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `question_attempt_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `session_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `question_id` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `question_seq` int NOT NULL,
  `stage_code` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `is_required` tinyint(1) NOT NULL DEFAULT 1,
  `is_critical` tinyint(1) NOT NULL DEFAULT 0,
  `completeness_score` decimal(5,2) NULL DEFAULT NULL,
  `depth_score` decimal(5,2) NULL DEFAULT NULL,
  `evidence_score` decimal(5,2) NULL DEFAULT NULL,
  `logic_score` decimal(5,2) NULL DEFAULT NULL,
  `communication_score` decimal(5,2) NULL DEFAULT NULL,
  `domain_fit_score` decimal(5,2) NULL DEFAULT NULL,
  `risk_penalty_score` decimal(5,2) NULL DEFAULT NULL,
  `question_score` decimal(5,2) NULL DEFAULT NULL,
  `reliability_score` decimal(6,4) NULL DEFAULT NULL,
  `question_weight` decimal(8,4) NULL DEFAULT NULL,
  `risk_tags_json` json NULL,
  `evidence_refs_json` json NULL,
  `notes` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uk_ai_interview_assessment_questions_assess_attempt`(`assessment_id` ASC, `question_attempt_id` ASC) USING BTREE,
  INDEX `idx_ai_interview_assessment_questions_assessment_seq`(`assessment_id` ASC, `question_seq` ASC) USING BTREE,
  INDEX `idx_ai_interview_assessment_questions_question_id`(`question_id` ASC) USING BTREE
) ENGINE=InnoDB CHARACTER SET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `ai_market_snapshots` (
  `id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `region` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `industry` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `job_family` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL,
  `level_code` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL,
  `salary_band` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL,
  `salary_fit` decimal(5,2) NULL DEFAULT NULL,
  `skill_scarcity_fit` decimal(5,2) NULL DEFAULT NULL,
  `peer_percentile` decimal(5,2) NULL DEFAULT NULL,
  `data_recency_factor` decimal(6,4) NULL DEFAULT NULL,
  `sample_size_factor` decimal(6,4) NULL DEFAULT NULL,
  `source_quality_factor` decimal(6,4) NULL DEFAULT NULL,
  `market_score` decimal(5,2) NULL DEFAULT NULL,
  `market_confidence` decimal(6,4) NULL DEFAULT NULL,
  `source_name` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL,
  `snapshot_at` datetime NOT NULL,
  `payload` json NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_ai_market_snapshots_dim_time`(`region` ASC, `industry` ASC, `level_code` ASC, `snapshot_at` ASC) USING BTREE,
  INDEX `idx_ai_market_snapshots_snapshot_at`(`snapshot_at` ASC) USING BTREE
) ENGINE=InnoDB CHARACTER SET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `ai_composite_assessments` (
  `id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `candidate_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `job_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `session_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL,
  `run_no` int NOT NULL DEFAULT 1,
  `resume_evaluation_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL,
  `interview_assessment_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL,
  `market_snapshot_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL,
  `status` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'draft',
  `policy_code` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'candidate_progression',
  `policy_version` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'v1.0.0',
  `resume_score` decimal(5,2) NULL DEFAULT NULL,
  `resume_confidence` decimal(6,4) NULL DEFAULT NULL,
  `interview_score` decimal(5,2) NULL DEFAULT NULL,
  `interview_confidence` decimal(6,4) NULL DEFAULT NULL,
  `market_score` decimal(5,2) NULL DEFAULT NULL,
  `market_confidence` decimal(6,4) NULL DEFAULT NULL,
  `raw_score` decimal(5,2) NULL DEFAULT NULL,
  `global_risk_penalty` decimal(5,2) NOT NULL DEFAULT 0.00,
  `bonus` decimal(5,2) NOT NULL DEFAULT 0.00,
  `composite_score` decimal(5,2) NULL DEFAULT NULL,
  `composite_confidence` decimal(6,4) NULL DEFAULT NULL,
  `hard_gate_result` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL,
  `hard_gate_codes_json` json NULL,
  `recommendation` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL,
  `decision` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending',
  `reason_codes_json` json NULL,
  `risk_tags_json` json NULL,
  `evidence_refs_json` json NULL,
  `formula_breakdown_json` json NULL,
  `computed_at` datetime NULL DEFAULT NULL,
  `decided_at` datetime NULL DEFAULT NULL,
  `published_at` datetime NULL DEFAULT NULL,
  `superseded_at` datetime NULL DEFAULT NULL,
  `trace_id` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL,
  `payload` json NULL,
  `created_by` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL,
  `updated_by` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uk_ai_composite_assessments_candidate_job_session_run`(`candidate_id` ASC, `job_id` ASC, `session_id` ASC, `run_no` ASC) USING BTREE,
  INDEX `idx_ai_composite_assessments_status`(`status` ASC) USING BTREE,
  INDEX `idx_ai_composite_assessments_decision`(`decision` ASC) USING BTREE,
  INDEX `idx_ai_composite_assessments_computed_at`(`computed_at` ASC) USING BTREE,
  INDEX `idx_ai_composite_assessments_policy`(`policy_code` ASC, `policy_version` ASC) USING BTREE
) ENGINE=InnoDB CHARACTER SET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `ai_decisions` (
  `id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `composite_assessment_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `pipeline_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL,
  `candidate_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `job_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `session_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL,
  `decision` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `source` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'system',
  `reason_codes_json` json NULL,
  `confidence` decimal(6,4) NULL DEFAULT NULL,
  `policy_code` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL,
  `policy_version` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL,
  `dry_run` tinyint(1) NOT NULL DEFAULT 0,
  `operator_id` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL,
  `note` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL,
  `trace_id` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL,
  `decided_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_ai_decisions_composite_assessment`(`composite_assessment_id` ASC) USING BTREE,
  INDEX `idx_ai_decisions_pipeline`(`pipeline_id` ASC) USING BTREE,
  INDEX `idx_ai_decisions_candidate_job_time`(`candidate_id` ASC, `job_id` ASC, `decided_at` ASC) USING BTREE,
  INDEX `idx_ai_decisions_decision_time`(`decision` ASC, `decided_at` ASC) USING BTREE,
  INDEX `idx_ai_decisions_trace_id`(`trace_id` ASC) USING BTREE
) ENGINE=InnoDB CHARACTER SET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `ai_decision_overrides` (
  `id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `decision_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `composite_assessment_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `pipeline_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL,
  `operator_id` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `from_decision` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `to_decision` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason_code` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `note` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL,
  `payload` json NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_ai_decision_overrides_pipeline_created`(`pipeline_id` ASC, `created_at` ASC) USING BTREE,
  INDEX `idx_ai_decision_overrides_operator_created`(`operator_id` ASC, `created_at` ASC) USING BTREE,
  INDEX `idx_ai_decision_overrides_composite`(`composite_assessment_id` ASC) USING BTREE
) ENGINE=InnoDB CHARACTER SET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `review_queue_tasks` (
  `id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `task_type` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_type` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `workspace_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL,
  `candidate_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL,
  `job_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL,
  `pipeline_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL,
  `priority` int NOT NULL DEFAULT 50,
  `status` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'open',
  `assignee_user_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL,
  `reason_codes_json` json NULL,
  `sla_due_at` datetime NULL DEFAULT NULL,
  `started_at` datetime NULL DEFAULT NULL,
  `resolved_at` datetime NULL DEFAULT NULL,
  `trace_id` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL,
  `payload` json NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_review_queue_tasks_status_priority_created`(`status` ASC, `priority` ASC, `created_at` ASC) USING BTREE,
  INDEX `idx_review_queue_tasks_assignee_status`(`assignee_user_id` ASC, `status` ASC) USING BTREE,
  INDEX `idx_review_queue_tasks_job_status`(`job_id` ASC, `status` ASC) USING BTREE,
  INDEX `idx_review_queue_tasks_sla_due_at`(`sla_due_at` ASC) USING BTREE
) ENGINE=InnoDB CHARACTER SET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `ai_event_outbox` (
  `id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `event_type` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `aggregate_type` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `aggregate_id` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `idempotency_key` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `schema_version` varchar(16) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'v1',
  `trace_id` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL,
  `occurred_at` datetime NOT NULL,
  `payload` json NOT NULL,
  `publish_status` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending',
  `attempt_count` int NOT NULL DEFAULT 0,
  `next_retry_at` datetime NULL DEFAULT NULL,
  `last_error` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uk_ai_event_outbox_idempotency_key`(`idempotency_key` ASC) USING BTREE,
  INDEX `idx_ai_event_outbox_publish_status_retry`(`publish_status` ASC, `next_retry_at` ASC) USING BTREE,
  INDEX `idx_ai_event_outbox_event_type_occurred`(`event_type` ASC, `occurred_at` ASC) USING BTREE,
  INDEX `idx_ai_event_outbox_trace_id`(`trace_id` ASC) USING BTREE
) ENGINE=InnoDB CHARACTER SET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------
-- 3) Extend existing business tables (no-FK)
-- ---------------------------------------------------------
CALL sp_add_index_if_missing(DATABASE(), 'decision_policy_versions', 'uk_decision_policy_versions_policy_ver',
  'ALTER TABLE `decision_policy_versions` ADD UNIQUE INDEX `uk_decision_policy_versions_policy_ver` (`policy_code`, `version`) USING BTREE');

CALL sp_add_column_if_missing(DATABASE(), 'candidates', 'workspace_id',
  'ALTER TABLE `candidates` ADD COLUMN `workspace_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL AFTER `id`');
CALL sp_add_index_if_missing(DATABASE(), 'candidates', 'idx_candidates_workspace_id',
  'ALTER TABLE `candidates` ADD INDEX `idx_candidates_workspace_id` (`workspace_id`) USING BTREE');

CALL sp_add_column_if_missing(DATABASE(), 'jobs', 'workspace_id',
  'ALTER TABLE `jobs` ADD COLUMN `workspace_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL AFTER `id`');
CALL sp_add_index_if_missing(DATABASE(), 'jobs', 'idx_jobs_workspace_id',
  'ALTER TABLE `jobs` ADD INDEX `idx_jobs_workspace_id` (`workspace_id`) USING BTREE');

CALL sp_add_column_if_missing(DATABASE(), 'candidate_job_evaluations', 'workspace_id',
  'ALTER TABLE `candidate_job_evaluations` ADD COLUMN `workspace_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL AFTER `job_id`');
CALL sp_add_index_if_missing(DATABASE(), 'candidate_job_evaluations', 'idx_candidate_job_eval_workspace_id',
  'ALTER TABLE `candidate_job_evaluations` ADD INDEX `idx_candidate_job_eval_workspace_id` (`workspace_id`) USING BTREE');

CALL sp_add_column_if_missing(DATABASE(), 'ai_interview_sessions', 'workspace_id',
  'ALTER TABLE `ai_interview_sessions` ADD COLUMN `workspace_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL AFTER `id`');
CALL sp_add_index_if_missing(DATABASE(), 'ai_interview_sessions', 'ix_ai_interview_sessions_workspace_id',
  'ALTER TABLE `ai_interview_sessions` ADD INDEX `ix_ai_interview_sessions_workspace_id` (`workspace_id`) USING BTREE');

CALL sp_add_column_if_missing(DATABASE(), 'candidate_job_pipeline', 'workspace_id',
  'ALTER TABLE `candidate_job_pipeline` ADD COLUMN `workspace_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL AFTER `id`');
CALL sp_add_index_if_missing(DATABASE(), 'candidate_job_pipeline', 'idx_candidate_job_pipeline_workspace_id',
  'ALTER TABLE `candidate_job_pipeline` ADD INDEX `idx_candidate_job_pipeline_workspace_id` (`workspace_id`) USING BTREE');

-- 3.1) Extend ai_interview_turns
CALL sp_add_column_if_missing(DATABASE(), 'ai_interview_turns', 'question_attempt_id',
  'ALTER TABLE `ai_interview_turns` ADD COLUMN `question_attempt_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL AFTER `turn_no`');
CALL sp_add_column_if_missing(DATABASE(), 'ai_interview_turns', 'question_id',
  'ALTER TABLE `ai_interview_turns` ADD COLUMN `question_id` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL AFTER `question_attempt_id`');
CALL sp_add_column_if_missing(DATABASE(), 'ai_interview_turns', 'question_seq',
  'ALTER TABLE `ai_interview_turns` ADD COLUMN `question_seq` int NULL DEFAULT NULL AFTER `question_id`');
CALL sp_add_column_if_missing(DATABASE(), 'ai_interview_turns', 'ingest_trace_id',
  'ALTER TABLE `ai_interview_turns` ADD COLUMN `ingest_trace_id` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL AFTER `latency_ms`');

CALL sp_add_index_if_missing(DATABASE(), 'ai_interview_turns', 'ix_ai_interview_turns_question_attempt_id',
  'ALTER TABLE `ai_interview_turns` ADD INDEX `ix_ai_interview_turns_question_attempt_id` (`question_attempt_id`) USING BTREE');
CALL sp_add_index_if_missing(DATABASE(), 'ai_interview_turns', 'ix_ai_interview_turns_session_question_seq',
  'ALTER TABLE `ai_interview_turns` ADD INDEX `ix_ai_interview_turns_session_question_seq` (`session_id`, `question_seq`) USING BTREE');
CALL sp_add_index_if_missing(DATABASE(), 'ai_interview_turns', 'ix_ai_interview_turns_ingest_trace_id',
  'ALTER TABLE `ai_interview_turns` ADD INDEX `ix_ai_interview_turns_ingest_trace_id` (`ingest_trace_id`) USING BTREE');

-- 3.2) Extend ai_interview_reports (compatibility link)
CALL sp_add_column_if_missing(DATABASE(), 'ai_interview_reports', 'assessment_id',
  'ALTER TABLE `ai_interview_reports` ADD COLUMN `assessment_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL AFTER `session_id`');
CALL sp_add_column_if_missing(DATABASE(), 'ai_interview_reports', 'report_type',
  'ALTER TABLE `ai_interview_reports` ADD COLUMN `report_type` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT ''legacy'' AFTER `recommendation`');
CALL sp_add_index_if_missing(DATABASE(), 'ai_interview_reports', 'ix_ai_interview_reports_assessment_id',
  'ALTER TABLE `ai_interview_reports` ADD INDEX `ix_ai_interview_reports_assessment_id` (`assessment_id`) USING BTREE');

-- 3.3) Extend candidate_job_pipeline
CALL sp_add_column_if_missing(DATABASE(), 'candidate_job_pipeline', 'interview_status',
  'ALTER TABLE `candidate_job_pipeline` ADD COLUMN `interview_status` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT ''not_started'' AFTER `invitation_status`');
CALL sp_add_column_if_missing(DATABASE(), 'candidate_job_pipeline', 'composite_assessment_status',
  'ALTER TABLE `candidate_job_pipeline` ADD COLUMN `composite_assessment_status` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT ''pending'' AFTER `interview_status`');
CALL sp_add_column_if_missing(DATABASE(), 'candidate_job_pipeline', 'next_step_status',
  'ALTER TABLE `candidate_job_pipeline` ADD COLUMN `next_step_status` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT ''pending_decision'' AFTER `composite_assessment_status`');
CALL sp_add_column_if_missing(DATABASE(), 'candidate_job_pipeline', 'latest_interview_assessment_id',
  'ALTER TABLE `candidate_job_pipeline` ADD COLUMN `latest_interview_assessment_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL AFTER `latest_evaluation_id`');
CALL sp_add_column_if_missing(DATABASE(), 'candidate_job_pipeline', 'latest_composite_assessment_id',
  'ALTER TABLE `candidate_job_pipeline` ADD COLUMN `latest_composite_assessment_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL AFTER `latest_interview_assessment_id`');
CALL sp_add_column_if_missing(DATABASE(), 'candidate_job_pipeline', 'latest_policy_version_id',
  'ALTER TABLE `candidate_job_pipeline` ADD COLUMN `latest_policy_version_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL AFTER `latest_composite_assessment_id`');
CALL sp_add_column_if_missing(DATABASE(), 'candidate_job_pipeline', 'last_interview_evaluated_at',
  'ALTER TABLE `candidate_job_pipeline` ADD COLUMN `last_interview_evaluated_at` datetime NULL DEFAULT NULL AFTER `last_evaluated_at`');
CALL sp_add_column_if_missing(DATABASE(), 'candidate_job_pipeline', 'latest_decision_at',
  'ALTER TABLE `candidate_job_pipeline` ADD COLUMN `latest_decision_at` datetime NULL DEFAULT NULL AFTER `last_interview_evaluated_at`');

CALL sp_add_index_if_missing(DATABASE(), 'candidate_job_pipeline', 'idx_candidate_job_pipeline_interview_status',
  'ALTER TABLE `candidate_job_pipeline` ADD INDEX `idx_candidate_job_pipeline_interview_status` (`interview_status`) USING BTREE');
CALL sp_add_index_if_missing(DATABASE(), 'candidate_job_pipeline', 'idx_candidate_job_pipeline_composite_status',
  'ALTER TABLE `candidate_job_pipeline` ADD INDEX `idx_candidate_job_pipeline_composite_status` (`composite_assessment_status`) USING BTREE');
CALL sp_add_index_if_missing(DATABASE(), 'candidate_job_pipeline', 'idx_candidate_job_pipeline_next_step_status',
  'ALTER TABLE `candidate_job_pipeline` ADD INDEX `idx_candidate_job_pipeline_next_step_status` (`next_step_status`) USING BTREE');
CALL sp_add_index_if_missing(DATABASE(), 'candidate_job_pipeline', 'idx_candidate_job_pipeline_latest_decision_at',
  'ALTER TABLE `candidate_job_pipeline` ADD INDEX `idx_candidate_job_pipeline_latest_decision_at` (`latest_decision_at`) USING BTREE');
CALL sp_add_index_if_missing(DATABASE(), 'candidate_job_pipeline', 'idx_candidate_job_pipeline_latest_interview_assessment',
  'ALTER TABLE `candidate_job_pipeline` ADD INDEX `idx_candidate_job_pipeline_latest_interview_assessment` (`latest_interview_assessment_id`) USING BTREE');
CALL sp_add_index_if_missing(DATABASE(), 'candidate_job_pipeline', 'idx_candidate_job_pipeline_latest_composite_assessment',
  'ALTER TABLE `candidate_job_pipeline` ADD INDEX `idx_candidate_job_pipeline_latest_composite_assessment` (`latest_composite_assessment_id`) USING BTREE');
CALL sp_add_index_if_missing(DATABASE(), 'candidate_job_pipeline', 'idx_candidate_job_pipeline_latest_policy_version',
  'ALTER TABLE `candidate_job_pipeline` ADD INDEX `idx_candidate_job_pipeline_latest_policy_version` (`latest_policy_version_id`) USING BTREE');

-- ---------------------------------------------------------
-- 4) Scope email invitation deliveries by workspace/user
-- ---------------------------------------------------------
CALL sp_add_column_if_missing(DATABASE(), 'candidate_email_deliveries', 'workspace_id',
  'ALTER TABLE `candidate_email_deliveries` ADD COLUMN `workspace_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL AFTER `id`');
CALL sp_add_index_if_missing(DATABASE(), 'candidate_email_deliveries', 'idx_candidate_email_delivery_workspace',
  'ALTER TABLE `candidate_email_deliveries` ADD INDEX `idx_candidate_email_delivery_workspace` (`workspace_id`) USING BTREE');

CALL sp_add_column_if_missing(DATABASE(), 'candidate_email_deliveries', 'created_by_user_id',
  'ALTER TABLE `candidate_email_deliveries` ADD COLUMN `created_by_user_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL AFTER `workspace_id`');
CALL sp_add_index_if_missing(DATABASE(), 'candidate_email_deliveries', 'idx_candidate_email_delivery_created_by',
  'ALTER TABLE `candidate_email_deliveries` ADD INDEX `idx_candidate_email_delivery_created_by` (`created_by_user_id`) USING BTREE');

CALL sp_add_column_if_missing(DATABASE(), 'channel_credentials', 'owner_user_id',
  'ALTER TABLE `channel_credentials` ADD COLUMN `owner_user_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL AFTER `provider`');
CALL sp_add_index_if_missing(DATABASE(), 'channel_credentials', 'idx_channel_credentials_owner_user_channel',
  'ALTER TABLE `channel_credentials` ADD INDEX `idx_channel_credentials_owner_user_channel` (`owner_user_id`, `channel`) USING BTREE');

UPDATE `candidate_email_deliveries` ced
JOIN `jobs` j ON j.`id` = ced.`job_id`
   SET ced.`workspace_id` = j.`workspace_id`
 WHERE ced.`workspace_id` IS NULL
   AND j.`workspace_id` IS NOT NULL;

-- ---------------------------------------------------------
-- 5) Seed default decision policy
-- ---------------------------------------------------------
UPDATE `decision_policy_versions`
   SET `is_default` = 0
 WHERE `policy_code` = 'candidate_progression';

INSERT INTO `decision_policy_versions` (
  `id`,
  `policy_code`,
  `version`,
  `status`,
  `description`,
  `resume_weight`,
  `interview_weight`,
  `market_weight`,
  `stability_weight`,
  `risk_penalty_weight`,
  `hard_rules_json`,
  `threshold_rules_json`,
  `override_rules_json`,
  `formula_text`,
  `is_default`,
  `effective_from`,
  `created_by`,
  `updated_by`
) VALUES (
  UUID(),
  'candidate_progression',
  'v1.0.0',
  'active',
  'Enterprise default policy for next-step progression',
  0.3500,
  0.4500,
  0.1500,
  0.0500,
  0.2000,
  JSON_OBJECT(
    'hard_reject_tags', JSON_ARRAY('identity_fraud', 'compliance_block'),
    'must_review_tags', JSON_ARRAY('conflicting_answers', 'fabrication_risk')
  ),
  JSON_OBJECT(
    'advance_min_score', 82,
    'review_min_score', 70,
    'max_risk_penalty', 30,
    'must_review_confidence_below', 0.72
  ),
  JSON_OBJECT(
    'manual_override_roles', JSON_ARRAY('workspace_owner', 'recruiter_manager', 'hrbp'),
    'allow_force_advance', TRUE
  ),
  'composite_score = clip(0,100,0.40*resume + 0.45*interview + 0.15*market - global_risk_penalty + bonus)',
  1,
  NOW(),
  'system',
  'system'
)
ON DUPLICATE KEY UPDATE
  `status` = VALUES(`status`),
  `description` = VALUES(`description`),
  `resume_weight` = VALUES(`resume_weight`),
  `interview_weight` = VALUES(`interview_weight`),
  `market_weight` = VALUES(`market_weight`),
  `stability_weight` = VALUES(`stability_weight`),
  `risk_penalty_weight` = VALUES(`risk_penalty_weight`),
  `hard_rules_json` = VALUES(`hard_rules_json`),
  `threshold_rules_json` = VALUES(`threshold_rules_json`),
  `override_rules_json` = VALUES(`override_rules_json`),
  `formula_text` = VALUES(`formula_text`),
  `is_default` = VALUES(`is_default`),
  `effective_from` = VALUES(`effective_from`),
  `updated_by` = VALUES(`updated_by`),
  `updated_at` = CURRENT_TIMESTAMP;

-- ---------------------------------------------------------
-- 6) Cleanup helper routines
-- ---------------------------------------------------------
DROP PROCEDURE IF EXISTS `sp_add_index_if_missing`;
DROP PROCEDURE IF EXISTS `sp_add_column_if_missing`;
DROP PROCEDURE IF EXISTS `sp_exec_if`;
