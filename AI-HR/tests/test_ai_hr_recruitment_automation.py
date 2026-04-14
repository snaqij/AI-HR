from __future__ import annotations

import os
from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from ai_hr.core.config import get_settings
from ai_hr.db.base import Base
from ai_hr.db.models import CandidateEmailDelivery, CandidateJobPipeline, JobCandidate
from ai_hr.db.session import get_db_session
from ai_hr.main import app
from ai_hr.services.recruitment_automation import RecruitmentAutomationService
import ai_hr.services.interview_invitation_email as invitation_email_module


class DummySMTP:
    def __init__(self, *args, **kwargs):
        self.sent = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def starttls(self):
        return None

    def login(self, *args, **kwargs):
        return None

    def send_message(self, message):
        self.sent.append(message)


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)
Base.metadata.create_all(bind=engine)


def override_get_db_session():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


app.dependency_overrides[get_db_session] = override_get_db_session
client = TestClient(app)


def _configure_env() -> None:
    os.environ["AI_HR_LLM_PROVIDER"] = "mock"
    os.environ["AI_HR_RTC_PROVIDER"] = "mock"
    os.environ["AI_HR_ASR_PROVIDER"] = "mock"
    os.environ["AI_HR_TTS_PROVIDER"] = "mock"
    os.environ["AI_HR_AI_INTERVIEW_LLM_ENABLED"] = "false"
    os.environ["AI_HR_AI_CANDIDATE_EVALUATION_LLM_ENABLED"] = "false"
    os.environ["AI_HR_AI_AUTO_INVITATION_ENABLED"] = "true"
    os.environ["AI_HR_EMAIL_SMTP_HOST"] = "smtp.example.com"
    os.environ["AI_HR_EMAIL_FROM_ADDRESS"] = "hr@example.com"
    os.environ["AI_HR_INTERVIEW_INVITATION_BASE_URL"] = "http://localhost:5173/interview/invitation/{token}"
    get_settings.cache_clear()


def _create_job_and_candidate() -> tuple[str, str]:
    job_id = client.post(
        "/api/v1/jobs",
        json={
            "title": "Java Backend Engineer",
            "department": "Engineering",
            "city": "Shanghai",
            "salary_range": "25k-35k",
            "requirements": "Java SpringBoot MySQL Redis 本科 3年以上",
        },
    ).json()["data"]["id"]
    candidate_id = client.post(
        "/api/v1/candidates/import",
        json={
            "candidates": [
                {
                    "name": "Guo Xiangqian",
                    "source_channel": "boss",
                    "external_candidate_id": "boss-automation-001",
                    "resume_text": "3年Java后端开发经验，本科，熟悉SpringBoot、MySQL、Redis，参与电商交易系统与库存系统开发。",
                    "raw_profile": {
                        "skills": ["Java", "SpringBoot", "MySQL", "Redis"],
                        "job_hops": 1,
                        "email": "candidate@example.com",
                        "projects": [{"name": "交易系统"}],
                    },
                }
            ]
        },
    ).json()["data"]["candidates"][0]["id"]
    return job_id, candidate_id


def test_recruitment_automation_should_evaluate_and_send_invitation() -> None:
    _configure_env()
    invitation_email_module.smtplib.SMTP = DummySMTP
    job_id, candidate_id = _create_job_and_candidate()

    with TestingSessionLocal() as session:
        session.add(
            JobCandidate(
                job_id=job_id,
                publication_id=None,
                candidate_id=candidate_id,
                channel="boss",
                external_job_id="boss-job-automation-001",
                external_candidate_id="boss-automation-001",
                stage="new",
                source_status="active",
                first_synced_at=datetime(2026, 4, 13, 0, 0, 0),
                last_synced_at=datetime(2026, 4, 13, 0, 0, 0),
                source_payload={},
            )
        )
        from ai_hr.repositories.candidate_job_pipeline import CandidateJobPipelineRepository

        pipeline_repo = CandidateJobPipelineRepository(session)
        pipeline = pipeline_repo.ensure(
            candidate_id=candidate_id,
            job_id=job_id,
            source_channel="boss",
            external_candidate_id="boss-automation-001",
        )
        pipeline_repo.mark_resume_downloaded(pipeline.id, resume_attachment_id="resume-attachment-demo")
        session.commit()

    with TestingSessionLocal() as session:
        automation = RecruitmentAutomationService(session)
        eval_results = automation.execute_due_candidate_evaluations(limit=10)
        invite_results = automation.execute_due_invitation_emails(limit=10)
        assert eval_results[0]["status"] == "completed"
        assert invite_results[0]["status"] == "sent"

        pipeline = session.execute(
            select(CandidateJobPipeline).where(CandidateJobPipeline.candidate_id == candidate_id)
        ).scalar_one()
        delivery = session.execute(
            select(CandidateEmailDelivery).where(CandidateEmailDelivery.candidate_id == candidate_id)
        ).scalar_one()
        assert pipeline.evaluation_status == "completed"
        assert pipeline.invitation_status == "invited"
        assert delivery.status == "sent"
