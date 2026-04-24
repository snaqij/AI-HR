"""Capture a user-authorized BOSS login cookie and sync it into AI-HR.

This script launches an isolated browser session for manual BOSS login.
After login succeeds, it collects the active `zhipin.com` cookies from that
session and submits them to AI-HR through the existing credentials API.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any, Sequence

import httpx

from ai_hr.boss_cookie_capture import (
    AIHRAuthSession,
    build_cookie_header,
    build_cookie_snapshot,
    extract_cookie_names,
    filter_boss_cookies,
    has_required_cookie_names,
    login_ai_hr,
    update_boss_cookie,
    validate_boss_cookie,
)

try:
    from playwright.sync_api import BrowserContext, sync_playwright
except Exception:  # noqa: BLE001
    BrowserContext = Any  # type: ignore[assignment]
    sync_playwright = None


DEFAULT_API_BASE = "http://127.0.0.1:8000"
DEFAULT_API_PREFIX = "/api/v1"
DEFAULT_BOSS_URL = "https://www.zhipin.com/web/geek/job"
DEFAULT_LOGIN_TIMEOUT_SECONDS = 300.0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="采集当前人工登录的 BOSS 直聘 Cookie，并写入 AI-HR 系统。")
    parser.add_argument("--api-base", default=DEFAULT_API_BASE, help="AI-HR 服务地址，例如 http://127.0.0.1:8000")
    parser.add_argument("--api-prefix", default=DEFAULT_API_PREFIX, help="AI-HR API 前缀，默认 /api/v1")
    parser.add_argument("--email", default=os.getenv("AI_HR_EMAIL", "").strip(), help="AI-HR 登录邮箱，可用 AI_HR_EMAIL")
    parser.add_argument("--password", default=os.getenv("AI_HR_PASSWORD", "").strip(), help="AI-HR 登录密码，可用 AI_HR_PASSWORD")
    parser.add_argument("--access-token", default=os.getenv("AI_HR_TOKEN", "").strip(), help="AI-HR access token，可用 AI_HR_TOKEN")
    parser.add_argument(
        "--workspace-id",
        default=os.getenv("AI_HR_WORKSPACE_ID", "").strip(),
        help="AI-HR workspace id，可用 AI_HR_WORKSPACE_ID",
    )
    parser.add_argument("--account-name", default="Primary Account", help="系统内展示的账号名称")
    parser.add_argument("--boss-url", default=DEFAULT_BOSS_URL, help="打开的 BOSS 登录页或业务页")
    parser.add_argument("--browser-channel", default="", help="可选浏览器通道，例如 chrome 或 msedge")
    parser.add_argument("--headless", action="store_true", help="无头模式运行，一般不建议开启")
    parser.add_argument("--login-timeout", type=float, default=DEFAULT_LOGIN_TIMEOUT_SECONDS, help="等待登录完成的超时时间（秒）")
    parser.add_argument(
        "--required-cookie",
        action="append",
        dest="required_cookies",
        default=[],
        help="用于判断登录完成的必需 Cookie 名称，可重复传入；默认 bst",
    )
    parser.add_argument("--cookie-file", default="", help="可选，将采集到的 Cookie 额外写入本地 JSON 文件")
    parser.add_argument(
        "--validate",
        dest="validate",
        action="store_true",
        default=True,
        help="写入后调用后端校验接口，默认开启",
    )
    parser.add_argument(
        "--no-validate",
        dest="validate",
        action="store_false",
        help="写入后不调用后端校验接口",
    )
    return parser.parse_args()


def _normalized_api_base(api_base: str, api_prefix: str) -> str:
    return f"{api_base.rstrip('/')}/{api_prefix.strip('/')}"


def _resolve_auth_session(client: httpx.Client, args: argparse.Namespace) -> AIHRAuthSession | None:
    access_token = str(args.access_token or "").strip()
    workspace_id = str(args.workspace_id or "").strip() or None
    email = str(args.email or "").strip()
    password = str(args.password or "").strip()

    if access_token:
        print("[boss-cookie] 使用传入的 AI-HR access token 写入系统")
        return AIHRAuthSession(access_token=access_token, workspace_id=workspace_id)

    if email and password:
        print(f"[boss-cookie] 正在登录 AI-HR: {email}")
        session = login_ai_hr(client, email=email, password=password)
        if workspace_id and workspace_id != session.workspace_id:
            session = AIHRAuthSession(access_token=session.access_token, workspace_id=workspace_id)
        print("[boss-cookie] AI-HR 登录成功")
        return session

    print("[boss-cookie] 未提供 AI-HR 认证信息，将直接请求后端；若后端开启鉴权，接口会返回 401")
    return None


def _wait_for_boss_cookies(
    context: BrowserContext,
    *,
    boss_url: str,
    required_cookie_names: Sequence[str],
    timeout_seconds: float,
) -> list[dict[str, str]]:
    deadline = time.monotonic() + max(5.0, timeout_seconds)
    last_reported_names: tuple[str, ...] | None = None

    while time.monotonic() < deadline:
        raw_cookies = context.cookies([boss_url])
        boss_cookies = filter_boss_cookies(raw_cookies)
        if boss_cookies and has_required_cookie_names(boss_cookies, required_names=required_cookie_names):
            return boss_cookies

        current_names = tuple(extract_cookie_names(boss_cookies))
        if current_names != last_reported_names:
            reported = ", ".join(current_names) if current_names else "<empty>"
            print(f"[boss-cookie] 等待登录完成，当前已捕获 Cookie: {reported}")
            last_reported_names = current_names
        time.sleep(1.0)

    raw_cookies = context.cookies([boss_url])
    boss_cookies = filter_boss_cookies(raw_cookies)
    names = ", ".join(extract_cookie_names(boss_cookies)) or "<empty>"
    required = ", ".join(required_cookie_names) or "<none>"
    raise TimeoutError(
        f"等待 BOSS 登录超时，仍未拿到必需 Cookie。required=[{required}] captured=[{names}]"
    )


def _write_cookie_file(cookie_file: str, cookies: Sequence[dict[str, str]]) -> None:
    if not cookie_file:
        return
    target = Path(cookie_file).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = build_cookie_snapshot(cookies)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[boss-cookie] 已写入本地 Cookie 文件: {target}")


def main() -> int:
    try:
        args = _parse_args()
        if sync_playwright is None:
            print("[boss-cookie] 缺少 playwright 依赖，请先安装 `playwright` 并执行 `python -m playwright install chromium`。")
            return 1

        required_cookie_names = tuple(
            str(name).strip()
            for name in (args.required_cookies or ["bst"])
            if str(name).strip()
        )
        api_base = _normalized_api_base(args.api_base, args.api_prefix)

        print(f"[boss-cookie] AI-HR API: {api_base}")
        print(f"[boss-cookie] BOSS 页面: {args.boss_url}")
        print(f"[boss-cookie] 登录超时: {args.login_timeout}s")

        with httpx.Client(base_url=api_base, timeout=httpx.Timeout(30.0)) as api_client:
            auth_session = _resolve_auth_session(api_client, args)

            with sync_playwright() as playwright:
                launch_kwargs: dict[str, Any] = {"headless": bool(args.headless)}
                if str(args.browser_channel or "").strip():
                    launch_kwargs["channel"] = str(args.browser_channel).strip()
                browser = playwright.chromium.launch(**launch_kwargs)
                context = browser.new_context()
                page = context.new_page()

                print("[boss-cookie] 已打开独立浏览器，请在该窗口中手动完成 BOSS 登录")
                page.goto(args.boss_url, wait_until="domcontentloaded")

                try:
                    boss_cookies = _wait_for_boss_cookies(
                        context,
                        boss_url=args.boss_url,
                        required_cookie_names=required_cookie_names,
                        timeout_seconds=float(args.login_timeout),
                    )
                finally:
                    browser.close()

            cookie_header = build_cookie_header(boss_cookies)
            if not cookie_header:
                print("[boss-cookie] 未捕获到有效 Cookie，任务终止")
                return 1

            print(
                "[boss-cookie] 已捕获 Cookie，名称包括: "
                + ", ".join(extract_cookie_names(boss_cookies))
            )
            _write_cookie_file(args.cookie_file, boss_cookies)

            update_result = update_boss_cookie(
                api_client,
                cookie_header=cookie_header,
                account_name=str(args.account_name or "Primary Account"),
                auth_session=auth_session,
            )
            print(f"[boss-cookie] 写入系统成功: {update_result}")

            if args.validate:
                validation_result = validate_boss_cookie(api_client, auth_session=auth_session)
                print(f"[boss-cookie] 后端校验结果: {validation_result}")
    except Exception as exc:  # noqa: BLE001
        print(f"[boss-cookie] 执行失败: {exc}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
