"""Bug condition exploration test for job request quota fix.

**Validates: Requirements 1.1, 1.2, 1.3, 1.4**

This test demonstrates the bug where count_requests_today() incorrectly includes
records where last_resume_requested_at was set by mark_resume_visible() instead
of mark_resume_requested().

CRITICAL: This test MUST FAIL on unfixed code - failure confirms the bug exists.
"""

from __future__ import annotations

import os
from datetime import datetime, UTC

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from ai_hr.core.config import get_settings
from ai_hr.db.base import Base
from ai_hr.db.models import CandidateJobPipeline
from ai_hr.repositories.candidate_job_pipeline import CandidateJobPipelineRepository


# Configure test environment
os.environ.setdefault("AI_HR_RTC_PROVIDER", "mock")
os.environ.setdefault("AI_HR_ASR_PROVIDER", "mock")
os.environ.setdefault("AI_HR_TTS_PROVIDER", "mock")
os.environ.setdefault("AI_HR_LLM_PROVIDER", "mock")
os.environ.setdefault("AI_HR_AI_INTERVIEW_LLM_ENABLED", "false")
get_settings.cache_clear()


# Setup test database
engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)
Base.metadata.create_all(bind=engine)


def test_bug_condition_quota_count_includes_non_request_records():
    """
    **Property 1: Bug Condition** - Quota Count Includes Non-Request Records
    
    **Validates: Requirements 1.1, 1.2, 1.3, 1.4**
    
    This test demonstrates the bug: when mark_resume_visible() is called on a pipeline
    where last_resume_requested_at is None, it sets last_resume_requested_at to now,
    causing count_requests_today() to incorrectly include this record even though
    resume_request_count = 0 (no actual request was made).
    
    EXPECTED OUTCOME: Test FAILS on unfixed code because count_requests_today()
    incorrectly returns 1 instead of 0.
    """
    session = TestingSessionLocal()
    try:
        repo = CandidateJobPipelineRepository(session)
        datetime.now(UTC).replace(tzinfo=None)
        
        # Create a pipeline record with last_resume_requested_at = None
        pipeline = CandidateJobPipeline(
            candidate_id="candidate-001",
            job_id="job-001",
            source_channel="boss",
            external_candidate_id="ext-001",
            resume_request_status="pending",
            resume_request_count=0,  # No actual request made
            last_resume_requested_at=None,  # This is the key: it's None
        )
        session.add(pipeline)
        session.flush()
        
        # Verify initial state: count should be 0
        initial_count = repo.count_requests_today("job-001")
        assert initial_count == 0, f"Initial count should be 0, got {initial_count}"
        
        # Call mark_resume_visible() - this triggers the bug
        # It will set last_resume_requested_at to now even though no request was made
        repo.mark_resume_visible(
            pipeline.id,
            next_retry_at=None,
        )
        session.flush()
        
        # Verify the bug: last_resume_requested_at is now set
        session.refresh(pipeline)
        assert pipeline.last_resume_requested_at is not None, "Bug trigger failed: last_resume_requested_at should be set"
        assert pipeline.resume_request_count == 0, "resume_request_count should still be 0"
        
        # BUG CONDITION: count_requests_today() now incorrectly includes this record
        # Expected behavior: count should be 0 (because resume_request_count = 0)
        # Actual buggy behavior: count will be 1 (because last_resume_requested_at >= start_of_day)
        count_after_visible = repo.count_requests_today("job-001")
        
        # This assertion SHOULD PASS (expected behavior) but WILL FAIL on unfixed code (bug)
        assert count_after_visible == 0, (
            f"BUG DETECTED: count_requests_today() incorrectly counted {count_after_visible} "
            f"instead of 0. The record has resume_request_count=0 but was included because "
            f"last_resume_requested_at was set by mark_resume_visible()."
        )
        
    finally:
        session.close()


def test_bug_condition_with_actual_request():
    """
    Contrast test: Verify that actual requests ARE correctly counted.
    
    This test should PASS even on unfixed code, demonstrating that the bug
    only affects records where mark_resume_visible() set last_resume_requested_at.
    """
    session = TestingSessionLocal()
    try:
        repo = CandidateJobPipelineRepository(session)
        
        # Create a pipeline and make an actual request
        pipeline = CandidateJobPipeline(
            candidate_id="candidate-002",
            job_id="job-002",
            source_channel="boss",
            external_candidate_id="ext-002",
            resume_request_status="pending",
            resume_request_count=0,
            last_resume_requested_at=None,
        )
        session.add(pipeline)
        session.flush()
        
        # Make an actual request using mark_resume_requested()
        repo.mark_resume_requested(
            pipeline.id,
            next_retry_at=None,
        )
        session.flush()
        
        # Verify: count should be 1 (this is correct behavior)
        count = repo.count_requests_today("job-002")
        assert count == 1, f"Count should be 1 for actual request, got {count}"
        
        # Verify the fields are set correctly
        session.refresh(pipeline)
        assert pipeline.resume_request_count == 1, "resume_request_count should be 1"
        assert pipeline.last_resume_requested_at is not None, "last_resume_requested_at should be set"
        
    finally:
        session.close()


def test_count_requests_today_sums_actual_request_count_for_same_day() -> None:
    session = TestingSessionLocal()
    try:
        repo = CandidateJobPipelineRepository(session)

        pipeline = CandidateJobPipeline(
            candidate_id="candidate-003",
            job_id="job-003",
            source_channel="boss",
            external_candidate_id="ext-003",
            resume_request_status="pending",
            resume_request_count=0,
            last_resume_requested_at=None,
        )
        session.add(pipeline)
        session.flush()

        repo.mark_resume_requested(
            pipeline.id,
            next_retry_at=None,
        )
        repo.mark_resume_requested(
            pipeline.id,
            next_retry_at=None,
        )
        session.flush()

        count = repo.count_requests_today("job-003")
        assert count == 2, f"Count should sum actual requests for the day, got {count}"

        session.refresh(pipeline)
        assert pipeline.resume_request_count == 2
        assert pipeline.last_resume_requested_at is not None
    finally:
        session.close()
