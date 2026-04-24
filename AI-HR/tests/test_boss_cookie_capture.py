from __future__ import annotations

import json

import httpx

from ai_hr.boss_cookie_capture import (
    AIHRAuthSession,
    build_auth_headers,
    build_cookie_header,
    build_cookie_snapshot,
    filter_boss_cookies,
    login_ai_hr,
    update_boss_cookie,
    validate_boss_cookie,
)


def test_filter_boss_cookies_should_keep_zhipin_domains_and_deduplicate_by_name() -> None:
    cookies = [
        {"name": "bst", "value": "old-token", "domain": ".zhipin.com"},
        {"name": "session", "value": "abc", "domain": "www.zhipin.com"},
        {"name": "bst", "value": "new-token", "domain": "www.zhipin.com"},
        {"name": "other", "value": "123", "domain": ".example.com"},
        {"name": "", "value": "x", "domain": ".zhipin.com"},
    ]

    result = filter_boss_cookies(cookies)

    assert result == [
        {"name": "bst", "value": "new-token"},
        {"name": "session", "value": "abc"},
    ]
    assert build_cookie_header(result) == "bst=new-token; session=abc"
    assert build_cookie_snapshot(result) == {
        "cookies": {
            "bst": "new-token",
            "session": "abc",
        }
    }


def test_build_auth_headers_should_include_bearer_and_workspace() -> None:
    headers = build_auth_headers(AIHRAuthSession(access_token="plain-token", workspace_id="ws-001"))

    assert headers == {
        "Authorization": "Bearer plain-token",
        "X-Workspace-Id": "ws-001",
    }


def test_ai_hr_cookie_sync_helpers_should_login_update_and_validate() -> None:
    seen_requests: list[tuple[str, dict[str, str], str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = request.content.decode("utf-8") if request.content else ""
        seen_requests.append((request.url.path, dict(request.headers), body))

        if request.url.path == "/auth/login":
            payload = json.loads(body)
            assert payload == {"email": "owner@example.com", "password": "password123"}
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "data": {
                        "session": {
                            "access_token": "issued-token",
                            "workspace_id": "ws-123",
                        }
                    },
                },
            )

        if request.url.path == "/credentials/boss":
            payload = json.loads(body)
            assert payload["cookie_header"] == "bst=token-1; wt2=token-2"
            assert payload["account_name"] == "Main BOSS"
            assert request.headers["Authorization"] == "Bearer issued-token"
            assert request.headers["X-Workspace-Id"] == "ws-123"
            return httpx.Response(
                200,
                json={"ok": True, "data": {"status": "success", "message": "updated"}},
            )

        if request.url.path == "/credentials/boss/validate":
            assert request.headers["Authorization"] == "Bearer issued-token"
            assert request.headers["X-Workspace-Id"] == "ws-123"
            return httpx.Response(
                200,
                json={"ok": True, "data": {"id": "cred-1", "status": "normal"}},
            )

        raise AssertionError(f"Unexpected request path: {request.url.path}")

    client = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="http://ai-hr.local",
    )
    auth_session = login_ai_hr(client, email="owner@example.com", password="password123")
    update_result = update_boss_cookie(
        client,
        cookie_header="bst=token-1; wt2=token-2",
        account_name="Main BOSS",
        auth_session=auth_session,
    )
    validate_result = validate_boss_cookie(client, auth_session=auth_session)

    assert auth_session == AIHRAuthSession(access_token="issued-token", workspace_id="ws-123")
    assert update_result == {"status": "success", "message": "updated"}
    assert validate_result == {"id": "cred-1", "status": "normal"}
    assert [path for path, _, _ in seen_requests] == [
        "/auth/login",
        "/credentials/boss",
        "/credentials/boss/validate",
    ]
