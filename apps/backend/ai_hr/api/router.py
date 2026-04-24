"""Root API router."""

from fastapi import APIRouter

from .routes import (
    ai,
    ai_assessments,
    agent_ops,
    auth,
    ai_interview_invitations,
    ai_interviews,
    ai_runtime,
    analytics,
    candidates,
    conversations,
    governance,
    interviews,
    jobs,
    credentials,
    workspaces,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(workspaces.router)
api_router.include_router(jobs.router)
api_router.include_router(candidates.router)
api_router.include_router(conversations.router)
api_router.include_router(ai.router)
api_router.include_router(ai_assessments.router)
api_router.include_router(agent_ops.router)
api_router.include_router(ai_interviews.router)
api_router.include_router(ai_interview_invitations.router)
api_router.include_router(ai_runtime.router)
api_router.include_router(analytics.router)
api_router.include_router(interviews.router)
api_router.include_router(governance.router)
api_router.include_router(credentials.router)
