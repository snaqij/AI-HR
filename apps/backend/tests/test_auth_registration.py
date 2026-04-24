from __future__ import annotations

import os

os.environ["AI_HR_ENV_FILE"] = ""

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from ai_hr.db.base import Base
from ai_hr.db.models import PlatformEmailVerificationCode, PlatformUser
from ai_hr.db.session import get_db_session
from ai_hr.main import app
from ai_hr.services.auth import AuthService


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


@pytest.fixture(autouse=True)
def reset_db(monkeypatch: pytest.MonkeyPatch):
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    app.dependency_overrides[get_db_session] = override_get_db_session
    monkeypatch.setattr(AuthService, "_generate_email_verification_code", staticmethod(lambda: "123456"))
    monkeypatch.setattr(AuthService, "_send_email_verification_code", lambda self, email, code, purpose: None)
    yield
    app.dependency_overrides[get_db_session] = override_get_db_session


def test_send_register_email_code_rejects_registered_email() -> None:
    with TestingSessionLocal() as session:
        session.add(
            PlatformUser(
                email="registered@example.com",
                email_normalized="registered@example.com",
                display_name="Existing User",
                password_hash="hash",
                password_algo="pbkdf2_sha256",
                status="active",
                email_verified=True,
                mobile_verified=False,
                profile_json={},
            )
        )
        session.commit()

    response = client.post(
        "/api/v1/auth/register/email-code",
        json={"email": "registered@example.com"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert payload["error"]["message"] == "该邮箱已注册"


def test_register_requires_email_code_and_marks_email_verified() -> None:
    send_code_response = client.post(
        "/api/v1/auth/register/email-code",
        json={"email": "newuser@example.com"},
    )
    assert send_code_response.status_code == 200
    assert send_code_response.json()["ok"] is True

    register_response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "newuser@example.com",
            "verification_code": "123456",
            "password": "password123",
            "display_name": "New User",
            "workspace_name": "My Team",
        },
    )

    assert register_response.status_code == 201
    payload = register_response.json()
    assert payload["ok"] is True
    assert payload["data"]["email"] == "newuser@example.com"

    with TestingSessionLocal() as session:
        user = session.execute(
            select(PlatformUser).where(PlatformUser.email_normalized == "newuser@example.com")
        ).scalars().one()
        code = session.execute(
            select(PlatformEmailVerificationCode).where(
                PlatformEmailVerificationCode.email_normalized == "newuser@example.com"
            )
        ).scalars().one()

    assert user.email_verified is True
    assert code.status == "consumed"


def test_register_rejects_invalid_email_code() -> None:
    client.post(
        "/api/v1/auth/register/email-code",
        json={"email": "another@example.com"},
    )

    register_response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "another@example.com",
            "verification_code": "654321",
            "password": "password123",
            "display_name": "Another User",
            "workspace_name": "My Team",
        },
    )

    assert register_response.status_code == 201
    payload = register_response.json()
    assert payload["ok"] is False
    assert payload["error"]["message"] == "验证码错误或已失效"
