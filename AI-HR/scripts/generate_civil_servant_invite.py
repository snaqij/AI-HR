"""Generate interview invitation link for civil servant position using resume_civil_servant.txt

Usage:
  python scripts/generate_civil_servant_invite.py
  python scripts/generate_civil_servant_invite.py --open
  python scripts/generate_civil_servant_invite.py --activate --open
  python scripts/generate_civil_servant_invite.py --no-send-email
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
import time
import webbrowser
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESUME_PATH = PROJECT_ROOT / "data" / "resume_civil_servant.txt"


def _api_post(
        client: httpx.Client,
        path: str,
        payload: dict[str, Any],
        *,
        timeout: float | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    print(f"[civil-servant] POST {path} ...")
    resp = client.post(path, json=payload, timeout=timeout)
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    print(f"[civil-servant] POST {path} done status={resp.status_code} cost_ms={elapsed_ms}")
    if resp.status_code >= 400:
        body_text = (resp.text or "").strip()
        raise RuntimeError(f"HTTP {resp.status_code} on POST {path}: {body_text}")
    body = resp.json()
    if not body.get("ok"):
        err = body.get("error") or {}
        raise RuntimeError(f"API error on {path}: {err.get('code')} {err.get('message')}")
    return body["data"]


def _api_get(
        client: httpx.Client,
        path: str,
        *,
        timeout: float | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    print(f"[civil-servant] GET {path} ...")
    resp = client.get(path, timeout=timeout)
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    print(f"[civil-servant] GET {path} done status={resp.status_code} cost_ms={elapsed_ms}")
    if resp.status_code >= 400:
        body_text = (resp.text or "").strip()
        raise RuntimeError(f"HTTP {resp.status_code} on GET {path}: {body_text}")
    body = resp.json()
    if not body.get("ok"):
        err = body.get("error") or {}
        raise RuntimeError(f"API error on {path}: {err.get('code')} {err.get('message')}")
    return body["data"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate civil servant interview invitation.")
    parser.add_argument("--api-base", default="http://127.0.0.1:8000/api/v1", help="Backend API base URL.")
    parser.add_argument("--frontend-base", default="http://localhost:5173", help="Frontend base URL.")
    parser.add_argument("--token", default="", help="Bearer token. Can also use AI_HR_TOKEN env var.")
    parser.add_argument("--open", action="store_true", help="Open invitation URL in browser.")
    parser.add_argument("--activate", action="store_true", help="Activate invitation and print session join URL.")
    parser.add_argument(
        "--send-email",
        dest="send_email",
        action="store_true",
        default=True,
        help="Send invitation via email. Enabled by default.",
    )
    parser.add_argument(
        "--no-send-email",
        dest="send_email",
        action="store_false",
        help="Disable email sending.",
    )
    parser.add_argument("--candidate-email", default="jiujingz@126.com", help="Candidate email.")
    parser.add_argument("--timeout", type=float, default=600.0, help="HTTP timeout seconds.")
    args = parser.parse_args()

    print("[civil-servant] Starting civil servant interview invitation generation")
    print(f"[civil-servant] api_base={args.api_base}")
    print(f"[civil-servant] frontend_base={args.frontend_base}")

    # Get bearer token
    bearer_token = (args.token or "").strip() or os.environ.get("AI_HR_TOKEN", "").strip()
    if not bearer_token:
        bearer_token = "v1.eyJ0eXAiOiJhY2Nlc3MiLCJzaWQiOiI0NTgwZWYzNC1mNGI4LTQyZjAtOWRjNS04YmRmODc5NDc1Y2QiLCJ1aWQiOiJjZGI0OTFhOS0wZjJlLTRkZTItOGI5My1kN2YzNjZhMTNiMDMiLCJleHAiOjE3NzY4NjY4MDMsIm4iOiJPV0lFb2owME1yRDloenE4UXIxWkFRIn0.yePq1OPGiJQeTZN-QMC0Lw-vN17gJqG4U13JxWaLgz8"
    if not bearer_token.startswith("Bearer "):
        bearer_token = f"Bearer {bearer_token}"

    # Read resume
    if not RESUME_PATH.exists():
        raise FileNotFoundError(f"Resume not found: {RESUME_PATH}")
    
    print(f"[civil-servant] resume_path={RESUME_PATH}")
    resume_text = RESUME_PATH.read_text(encoding="utf-8").strip()
    print(f"[civil-servant] resume_chars={len(resume_text)}")

    resume_hash = hashlib.sha256(resume_text.encode("utf-8")).hexdigest()
    candidate_external_id = f"civil-servant-{resume_hash[:16]}"

    # Job payload for civil servant position
    job_payload = {
        "title": "公务员",
        "department": "政府机关",
        "city": "北京",
        "salary_range": "面议",
        "requirements": (
            "1. 政治立场坚定，拥护党的领导，具备扎实的政治理论基础。\n"
            "2. 具备较强的综合分析能力，能够准确把握政策精神，分析复杂问题。\n"
            "3. 具备良好的组织协调能力，有丰富的活动策划和组织经验。\n"
            "4. 具备较强的应变能力和抗压能力，能够妥善处理突发事件。\n"
            "5. 具备良好的沟通能力和服务意识，热心为群众服务。\n"
            "6. 熟练掌握公文写作，文字功底扎实。\n"
            "7. 重点考察：政治素养、综合分析能力、组织协调能力、应变能力、服务意识。"
        ),
    }

    candidate_payload = {
        "candidates": [
            {
                "name": "赵公仆",
                "source_channel": "civil_servant_script",
                "external_candidate_id": candidate_external_id,
                "email": args.candidate_email,
                "resume_text": resume_text[:20000],
                "raw_profile": {
                    "from_script": "generate_civil_servant_invite",
                    "resume_file": "resume_civil_servant.txt",
                    "position": "公务员",
                    "email": args.candidate_email,
                },
            }
        ]
    }

    timeout = httpx.Timeout(timeout=args.timeout)
    headers = {"Authorization": bearer_token}
    
    with httpx.Client(base_url=args.api_base.rstrip("/"), timeout=timeout, headers=headers) as client:
        print("[civil-servant] step=create_job")
        job = _api_post(client, "/jobs", job_payload)
        
        print("[civil-servant] step=import_candidate")
        imported = _api_post(client, "/candidates/import", candidate_payload)
        candidate = (imported.get("candidates") or [None])[0]
        if not candidate:
            raise RuntimeError("Candidate import returned empty candidates.")

        invitation: dict[str, Any] | None = None
        token = ""
        invite_url = ""

        if args.send_email:
            print("[civil-servant] step=link_candidate_to_job")
            _api_post(
                client,
                f"/jobs/{job['id']}/candidates/{candidate['id']}/link",
                {},
            )

            print("[civil-servant] step=evaluate_candidate")
            evaluation_id: str | None = None
            try:
                eval_result = _api_post(
                    client,
                    f"/jobs/{job['id']}/candidates/{candidate['id']}/evaluate",
                    {"evaluation_version": "v1", "force_refresh": False},
                )
                evaluation_id = str((((eval_result or {}).get("evaluation") or {}).get("id") or "")).strip() or None
            except Exception as exc:
                print(f"[civil-servant][warn] evaluate failed: {exc}")

            print("[civil-servant] step=send_invite_email")
            email_result = _api_post(
                client,
                f"/jobs/{job['id']}/candidates/{candidate['id']}/invite-email",
                {
                    "evaluation_id": evaluation_id,
                    "note": "公务员岗位面试邀请",
                },
            )

            invite_url = str(email_result.get("invitation_link") or "").strip()
            if not invite_url:
                raise RuntimeError("invite-email succeeded but invitation_link is empty")
            
            path_parts = [p for p in urlparse(invite_url).path.split("/") if p]
            if path_parts and len(path_parts) >= 2 and path_parts[-2] == "invitation":
                token = path_parts[-1]
            
            print(f"[civil-servant] email_delivery_id={email_result.get('delivery_id')}")
            print(f"[civil-servant] invitation_id={email_result.get('invitation_id')}")
        else:
            print("[civil-servant] step=create_invitation")
            invitation = _api_post(
                client,
                "/ai-interviews/invitations",
                {
                    "candidate_id": candidate["id"],
                    "job_id": job["id"],
                    "note": "公务员岗位面试邀请",
                },
            )
            token = invitation["token"]
            invite_url = f"{args.frontend_base.rstrip('/')}/interview/invitation/{token}"

        print("\n=== 公务员面试邀请已生成 ===")
        print(f"简历文件: {RESUME_PATH}")
        print(f"岗位ID: {job['id']}")
        print(f"候选人ID: {candidate['id']}")
        if invitation:
            print(f"邀请ID: {invitation['id']}")
        print(f"邀请令牌: {token or '<未解析>'}")
        print(f"邀请链接: {invite_url}")

        if args.activate:
            if not token:
                raise RuntimeError("Cannot activate: token not parsed")
            print("[civil-servant] step=activate_invitation")
            activated = _api_post(client, f"/ai-interviews/invitations/token/{token}/activate", {})
            session_id = activated.get("id")
            join_url = activated.get("join_url")
            print(f"会话ID: {session_id}")
            if join_url:
                absolute_join_url = (
                    join_url if join_url.startswith("http") 
                    else f"{args.frontend_base.rstrip('/')}{join_url}"
                )
                print(f"会话链接: {absolute_join_url}")
                if args.open:
                    webbrowser.open(absolute_join_url)
            elif args.open:
                webbrowser.open(invite_url)
        elif args.open:
            webbrowser.open(invite_url)

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\n已中断。")
        raise SystemExit(130)
    except Exception as exc:
        print(f"失败: {exc}")
        raise SystemExit(1)
