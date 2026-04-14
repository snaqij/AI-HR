"""Root API router."""

from fastapi import APIRouter

from .routes import (
    ai,
    ai_interview_invitations,
    ai_interview_webhooks,
    ai_interviews,
    ai_runtime,
    analytics,
    candidates,
    conversations,
    governance,
    interviews,
    jobs,
    credentials,
)

api_router = APIRouter()
api_router.include_router(jobs.router)
api_router.include_router(candidates.router)
api_router.include_router(conversations.router)
api_router.include_router(ai.router)
api_router.include_router(ai_interviews.router)
api_router.include_router(ai_interview_invitations.router)
api_router.include_router(ai_interview_webhooks.router)
api_router.include_router(ai_runtime.router)
api_router.include_router(analytics.router)
api_router.include_router(interviews.router)
api_router.include_router(governance.router)
api_router.include_router(credentials.router)
