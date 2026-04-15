# -*- coding: utf-8 -*-
import os
import sys

sys.path.insert(0, os.path.abspath('.'))
os.environ["PYTHONUTF8"] = "1"

from ai_hr.core.config import get_settings
settings = get_settings()
print('LLM_ENABLED=', settings.ai_interview_llm_enabled)
print('LLM_API_KEY=', bool(settings.llm_api_key))
print('LLM_PROVIDER=', settings.llm_provider)

from ai_hr.db.session import SessionLocal
from ai_hr.services.ai_interviews import AIInterviewService
from ai_hr.repositories.ai_interviews import AIInterviewSessionRepository, AIInterviewInvitationRepository
from ai_hr.repositories.ai_runtime import AIRuntimeRepository
from ai_hr.repositories.candidates import CandidateRepository
from ai_hr.repositories.jobs import JobRepository
from ai_hr.repositories.events import EventRepository
from ai_hr.repositories.interviews import InterviewRepository
from ai_hr.services.rtc.base import RTCGateway
class MockASRProvider: pass
class MockTTSProvider: pass
from ai_hr.services.llm.client import LLMClient
from ai_hr.services.interview_runtime.store import InterviewRuntimeStore

class DummyRTCGateway(RTCGateway):
    def create_room(self, *a, **kw): pass
    def close_room(self, *a, **kw): pass
class DummyOrch:
    pass

session = SessionLocal()
service = AIInterviewService(
    session_repository=AIInterviewSessionRepository(session),
    invitation_repository=AIInterviewInvitationRepository(session),
    runtime_repository=AIRuntimeRepository(session),
    candidate_repository=CandidateRepository(session),
    job_repository=JobRepository(session),
    interview_repository=InterviewRepository(session),
    event_repository=EventRepository(session),
    rtc_gateway=DummyRTCGateway(),
    asr_provider=MockASRProvider(),
    tts_provider=MockTTSProvider(),
    llm_client=LLMClient(),
    orchestrator=DummyOrch(),
    runtime_store=InterviewRuntimeStore(),
    ten_runtime_manager=None,
)

try:
    q, mode = service._generate_questions_with_fallback(
        session_id='test-session',
        job_title='Python Engineer',
        resume_text='Experience in Python and FastAPI',
        job_requirements='Know python',
        skills=['python'],
        question_count=5,
    )
    print('Generated:', len(q), 'Mode:', mode)
    if mode != 'llm':
        print(q)
except Exception as e:
    import traceback
    traceback.print_exc()
