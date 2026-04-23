"""Create a real interview invitation link from a resume in data/ and optionally open it.

Usage:
  python scripts/generate_interview_invite.py --token YOUR_TOKEN
  python scripts/generate_interview_invite.py --token YOUR_TOKEN --no-send-email
  python scripts/generate_interview_invite.py --token YOUR_TOKEN --open --activate
  python scripts/generate_interview_invite.py --resume data/sample.pdf --token YOUR_TOKEN
  
  # Or use environment variable:
  export AI_HR_TOKEN="v1.eyJ0eXAiOiJhY2Nlc3MiLCJzaWQiOi..."
  python scripts/generate_interview_invite.py
"""

from __future__ import annotations

import argparse
import hashlib
import os
import traceback
import sys
import time
import webbrowser
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

try:
    import pypdf
except Exception:  # noqa: BLE001
    pypdf = None


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_TEST_RESUME = DEFAULT_DATA_DIR / "resume_civil_servant"


def _extract_text_from_pdf(pdf_path: Path) -> str:
    if pypdf is None:
        raise RuntimeError("pypdf is required to parse PDF resumes. Please install dependencies first.")
    text_parts: list[str] = []
    with pdf_path.open("rb") as f:
        reader = pypdf.PdfReader(f)
        for page in reader.pages:
            text_parts.append(page.extract_text() or "")
    return "\n".join(text_parts).strip()


def _read_resume_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _extract_text_from_pdf(path)
    return path.read_text(encoding="utf-8", errors="ignore").strip()


def _pick_resume_file(data_dir: Path) -> Path:
    if not data_dir.exists():
        raise FileNotFoundError(f"data dir not found: {data_dir}")

    preferred: list[Path] = []
    for item in data_dir.iterdir():
        if not item.is_file():
            continue
        name = item.name.lower()
        if item.suffix.lower() in {".txt", ".pdf"}:
            preferred.append(item)
            continue
        # Allow files like "测试文本简历" without extension.
        if ("简历" in item.name) and item.suffix == "":
            preferred.append(item)

    if not preferred:
        raise FileNotFoundError(f"No resume file found in {data_dir}. Put .txt/.pdf resume under data/.")

    # Prefer txt first for deterministic local scripts.
    preferred.sort(key=lambda p: (0 if p.suffix.lower() == ".txt" else 1, p.name))
    return preferred[0]


def _api_post(
        client: httpx.Client,
        path: str,
        payload: dict[str, Any],
        *,
        timeout: float | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    print(f"[invite] POST {path} ...")
    resp = client.post(path, json=payload, timeout=timeout)
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    print(f"[invite] POST {path} done status={resp.status_code} cost_ms={elapsed_ms}")
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
    print(f"[invite] GET {path} ...")
    resp = client.get(path, timeout=timeout)
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    print(f"[invite] GET {path} done status={resp.status_code} cost_ms={elapsed_ms}")
    if resp.status_code >= 400:
        body_text = (resp.text or "").strip()
        raise RuntimeError(f"HTTP {resp.status_code} on GET {path}: {body_text}")
    body = resp.json()
    if not body.get("ok"):
        err = body.get("error") or {}
        raise RuntimeError(f"API error on {path}: {err.get('code')} {err.get('message')}")
    return body["data"]


def _build_candidate_name(resume_path: Path, resume_text: str) -> str:
    first_line = (resume_text.splitlines()[0].strip() if resume_text else "").strip()
    if 1 <= len(first_line) <= 20 and " " not in first_line:
        return first_line
    stem = resume_path.stem.strip() or "candidate"
    return f"Candidate-{stem[:24]}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate interview invitation link from local resume data.")
    parser.add_argument("--api-base", default="http://127.0.0.1:8000/api/v1", help="Backend API base URL.")
    parser.add_argument("--frontend-base", default="http://localhost:5173", help="Frontend base URL.")
    parser.add_argument("--resume", default="", help="Optional resume path. Default: auto-pick from data/.")
    parser.add_argument("--token", default="", help="Bearer token for API authentication. Can also use AI_HR_TOKEN env var.")
    parser.add_argument("--open", action="store_true", help="Open invitation URL in browser.")
    parser.add_argument("--activate", action="store_true", help="Activate invitation and print session join URL.")
    parser.add_argument(
        "--send-email",
        dest="send_email",
        action="store_true",
        default=True,
        help="Send invitation via email (evaluate candidate first). Enabled by default.",
    )
    parser.add_argument(
        "--no-send-email",
        dest="send_email",
        action="store_false",
        help="Disable email sending and only create invitation link.",
    )
    parser.add_argument("--candidate-email", default="jiujingz@126.com", help="Candidate email used for invitation delivery.")
    parser.add_argument("--template-code", default="", help="Optional email template code for invitation.")
    parser.add_argument("--timeout", type=float, default=600.0, help="Default HTTP timeout seconds.")
    parser.add_argument(
        "--invitation-timeout",
        type=float,
        default=600.0,
        help="Timeout for creating invitation (often slower due to question prebuild).",
    )
    parser.add_argument("--debug", action="store_true", help="Print detailed debug logs and stack trace on failure.")
    args = parser.parse_args()

    print("[invite] start generate_interview_invite")
    print(f"[invite] api_base={args.api_base}")
    print(f"[invite] frontend_base={args.frontend_base}")
    print(
        f"[invite] timeout={args.timeout}s invitation_timeout={args.invitation_timeout}s "
        f"activate={args.activate} open={args.open} send_email={args.send_email}"
    )

    # Get bearer token from args or environment variable or use hardcoded default
    bearer_token = (args.token or "").strip() or os.environ.get("AI_HR_TOKEN", "").strip()
    
    # Hardcoded default token
    if not bearer_token:
        bearer_token = "v1.eyJ0eXAiOiJhY2Nlc3MiLCJzaWQiOiI0NTgwZWYzNC1mNGI4LTQyZjAtOWRjNS04YmRmODc5NDc1Y2QiLCJ1aWQiOiJjZGI0OTFhOS0wZjJlLTRkZTItOGI5My1kN2YzNjZhMTNiMDMiLCJleHAiOjE3NzY4NjU4NzgsIm4iOiJpYWpHeHB1S0dnZmktb2c2OWIyT3lBIn0.I6asek8CbGF5A0ZzsCsqnC4bMe8XDcIn2SNgNXINnjk"

    # Ensure token has Bearer prefix
    if not bearer_token.startswith("Bearer "):
        bearer_token = f"Bearer {bearer_token}"
    
    print(f"[invite] auth_token={'*' * 20}...{bearer_token[-8:]}")  # Mask token for security

    if args.resume:
        resume_path = Path(args.resume).resolve()
    elif DEFAULT_TEST_RESUME.exists():
        resume_path = DEFAULT_TEST_RESUME.resolve()
    else:
        resume_path = _pick_resume_file(DEFAULT_DATA_DIR)
    print(f"[invite] picked_resume={resume_path}")
    resume_text = _read_resume_text(resume_path)
    if not resume_text:
        raise RuntimeError(f"Resume text is empty: {resume_path}")
    print(f"[invite] resume_chars={len(resume_text)}")

    resume_hash = hashlib.sha256(resume_text.encode("utf-8", errors="ignore")).hexdigest()
    candidate_external_id = f"local-resume-{resume_hash[:16]}"
    candidate_name = _build_candidate_name(resume_path, resume_text)

    job_title = "Java开发实习生"
    job_payload = {
        "title": job_title,
        "department": "研发团队",
        "city": "上海",
        "salary_range": "150-200/天",
        "requirements": (
            "1. 计算机或相关专业本科及以上学历在读生。\n"
            "2. 热爱编程，具备扎实的Java语言基础，了解JVM、多线程及集合框架。\n"
            "3. 熟悉Spring、Spring Boot、MyBatis等主流应用开发框架优先。\n"
            "4. 熟悉关系型数据库（MySQL）的基本使用，了解常用SQL优化。\n"
            "5. 有较强的逻辑分析能力和系统除错能力，能快速适应新领域和学习新技术。\n"
            "6. 重点考察：基础技术功底、项目实践的真实度、以及遇到 Bug 时真实的解决思路。"
        ),
    }

    candidate_payload = {
        "candidates": [
            {
                "name": candidate_name,
                "source_channel": "local_script",
                "external_candidate_id": candidate_external_id,
                "email": (args.candidate_email or "").strip() or None,
                "resume_text": resume_text[:20000],
                "raw_profile": {
                    "from_script": "generate_interview_invite",
                    "resume_file": resume_path.name,
                    "email": (args.candidate_email or "").strip() or None,
                },
            }
        ]
    }

    timeout = httpx.Timeout(timeout=args.timeout)
    headers = {"Authorization": bearer_token}
    with httpx.Client(base_url=args.api_base.rstrip("/"), timeout=timeout, headers=headers) as client:
        health_url = args.api_base.rstrip("/") + "/jobs"
        print(f"[invite] probing_api={health_url}")
        probe_start = time.perf_counter()
        try:
            resp = client.get("/jobs")
            probe_ms = int((time.perf_counter() - probe_start) * 1000)
            print(f"[invite] probe_done status={resp.status_code} cost_ms={probe_ms}")
        except Exception as exc:  # noqa: BLE001
            probe_ms = int((time.perf_counter() - probe_start) * 1000)
            print(f"[invite] probe_failed cost_ms={probe_ms} err={exc}")
            raise

        print("[invite] step=create_job")
        job = _api_post(client, "/jobs", job_payload)
        print("[invite] step=import_candidate")
        imported = _api_post(client, "/candidates/import", candidate_payload)
        candidate = (imported.get("candidates") or [None])[0]
        if not candidate:
            raise RuntimeError("Candidate import returned empty candidates.")

        invitation: dict[str, Any] | None = None
        token = ""
        invite_url = ""

        if args.send_email:
            candidate_email = (args.candidate_email or "").strip()
            if not candidate_email:
                raise RuntimeError("--send-email requires --candidate-email")

            print("[invite] step=link_candidate_to_job")
            _api_post(
                client,
                f"/jobs/{job['id']}/candidates/{candidate['id']}/link",
                {},
                timeout=args.invitation_timeout,
            )

            evaluation_id: str | None = None
            print("[invite] step=evaluate_candidate")
            try:
                eval_result = _api_post(
                    client,
                    f"/jobs/{job['id']}/candidates/{candidate['id']}/evaluate",
                    {
                        "evaluation_version": "v1",
                        "force_refresh": False,
                    },
                    timeout=args.invitation_timeout,
                )
                evaluation_id = str((((eval_result or {}).get("evaluation") or {}).get("id") or "")).strip() or None
            except Exception as exc:  # noqa: BLE001
                print(f"[invite][warn] evaluate failed, will try latest evaluation fallback: {exc}")
                try:
                    latest_eval = _api_get(
                        client,
                        f"/jobs/{job['id']}/candidates/{candidate['id']}/evaluation-latest",
                        timeout=args.invitation_timeout,
                    )
                    evaluation_id = str((((latest_eval or {}).get("evaluation") or {}).get("id") or "")).strip() or None
                    if evaluation_id:
                        print(f"[invite] fallback latest evaluation_id={evaluation_id}")
                except Exception as latest_exc:  # noqa: BLE001
                    print(f"[invite][warn] latest evaluation fallback failed: {latest_exc}")

            print("[invite] step=send_invite_email")
            email_result = _api_post(
                client,
                f"/jobs/{job['id']}/candidates/{candidate['id']}/invite-email",
                {
                    "evaluation_id": evaluation_id,
                    "template_code": (args.template_code or "").strip() or None,
                    "note": f"resume={resume_path.name}",
                },
                timeout=args.invitation_timeout,
            )

            invite_url = str(email_result.get("invitation_link") or "").strip()
            if not invite_url:
                raise RuntimeError("invite-email succeeded but invitation_link is empty")
            path_parts = [p for p in urlparse(invite_url).path.split("/") if p]
            if path_parts and path_parts[-2:] and len(path_parts) >= 2 and path_parts[-2] == "invitation":
                token = path_parts[-1]
            print(f"[invite] email_delivery_id={email_result.get('delivery_id')}")
            print(f"[invite] email_status={email_result.get('status')}")
            print(f"[invite] invitation_id={email_result.get('invitation_id')}")
        else:
            print("[invite] step=create_invitation")
            invitation = _api_post(
                client,
                "/ai-interviews/invitations",
                {
                    "candidate_id": candidate["id"],
                    "job_id": job["id"],
                    "note": f"resume={resume_path.name}",
                },
                timeout=args.invitation_timeout,
            )
            token = invitation["token"]
            invite_url = f"{args.frontend_base.rstrip('/')}/interview/invitation/{token}"

        print("=== Interview Invitation Generated ===")
        print(f"resume_file: {resume_path}")
        print(f"job_id: {job['id']}")
        print(f"candidate_id: {candidate['id']}")
        if invitation:
            print(f"invitation_id: {invitation['id']}")
        print(f"invitation_token: {token or '<not-parsed>'}")
        print(f"invite_url: {invite_url}")

        if args.activate:
            if not token:
                raise RuntimeError("Cannot activate invitation because token was not parsed from invitation_link")
            print("[invite] step=activate_invitation")
            activated = _api_post(client, f"/ai-interviews/invitations/token/{token}/activate", {})
            session_id = activated.get("id")
            join_url = activated.get("join_url")
            print(f"session_id: {session_id}")
            if join_url:
                absolute_join_url = (
                    join_url if join_url.startswith("http") else f"{args.frontend_base.rstrip('/')}{join_url}"
                )
                print(f"session_join_url: {absolute_join_url}")
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
        print("\nInterrupted.")
        raise SystemExit(130)
    except Exception as exc:  # noqa: BLE001
        print(f"Failed: {exc}")
        if "--debug" in sys.argv:
            traceback.print_exc()
        raise SystemExit(1)
