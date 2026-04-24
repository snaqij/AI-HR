from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from ai_hr.db.base import Base
from ai_hr.db.session import get_db_session
from ai_hr.main import app


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


def test_ai_reply_classify_intent_endpoint() -> None:
    response = client.post(
        "/api/v1/ai/reply/classify-intent",
        json={"conversation_id": "conv-001", "message": "薪资范围是多少？"},
    )
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["conversation_id"] == "conv-001"
    assert payload["intent"] in {"salary", "general", "greeting"}
    assert "explanation" in payload
    assert payload["provider"] == "mock"
    assert payload["model_name"] == "intent_classify-mock"


def test_ai_reply_generate_endpoint_with_explanation() -> None:
    response = client.post(
        "/api/v1/ai/reply/generate",
        json={"conversation_id": "conv-002", "message": "你好，我对这个岗位感兴趣"},
    )
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["conversation_id"] == "conv-002"
    assert isinstance(payload["reply_text"], str)
    assert payload["confidence"] >= 0
    assert payload["action"] in {"auto_send", "handoff", "blocked"}
    assert "explanation" in payload
    assert payload["provider"] == "mock"
    assert payload["model_name"] == "reply_generate-mock"

