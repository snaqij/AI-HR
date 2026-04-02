"""BOSS 连接器实现。"""

from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
import requests
from urllib import parse

from ..core.exceptions import ConnectorOperationError, InvalidConnectorConfigError
from .base import ConnectorCredentials, PublishJobResult, SyncJobStatusResult


class BossConnector:
    """将统一招聘动作映射到 BOSS 平台接口。"""

    channel = "boss"

    def __init__(self, credentials: ConnectorCredentials):
        self._credentials = credentials

    def validate_credentials(self) -> None:
        """校验连接器配置。"""
        if not self._credentials.account.strip():
            raise InvalidConnectorConfigError("BOSS account is required")
        if self._credentials.mode not in {"mock", "live"}:
            raise InvalidConnectorConfigError("BOSS mode must be either 'mock' or 'live'")
        if self._credentials.mode == "mock":
            if not self._credentials.secret.strip():
                raise InvalidConnectorConfigError("BOSS secret is required")
            return

        required_fields = {
            "base_url": self._credentials.base_url,
            "publish_path": self._credentials.publish_path,
            "status_path": self._credentials.status_path,
            "list_jobs_path": self._credentials.list_jobs_path,
            "applicants_path": self._credentials.applicants_path,
        }
        for key, value in required_fields.items():
            if not value:
                raise InvalidConnectorConfigError(f"BOSS {key} is required in live mode")

    def publish_job(self, job_payload: dict[str, Any]) -> PublishJobResult:
        if self._credentials.mode == "mock":
            external_job_id = f"boss-{uuid.uuid4()}"
            return PublishJobResult(
                channel=self.channel,
                external_job_id=external_job_id,
                status="published",
                raw_payload={"mode": "mock", "external_job_id": external_job_id, "received_title": job_payload.get("title")},
            )

        request_payload = self._build_live_publish_payload(job_payload)
        response_payload = self._send_publish_request(request_payload)
        external_job_id = self._extract_external_job_id(response_payload)
        return PublishJobResult(
            channel=self.channel,
            external_job_id=external_job_id,
            status="published",
            raw_payload=response_payload,
        )

    def sync_job_status(self, external_job_id: str) -> SyncJobStatusResult:
        if self._credentials.mode == "mock":
            return SyncJobStatusResult(
                channel=self.channel,
                external_job_id=external_job_id,
                status="published",
                raw_payload={"mode": "mock", "external_job_id": external_job_id},
            )

        response_payload = self._send_status_request(external_job_id)
        return SyncJobStatusResult(
            channel=self.channel,
            external_job_id=external_job_id,
            status=self._extract_job_status(response_payload),
            raw_payload=response_payload,
        )

    def list_jobs(self, page: int = 1, page_size: int = 20) -> dict[str, Any]:
        """拉取当前账号下的职位列表。"""
        if self._credentials.mode == "mock":
            return {
                "items": [
                    {"external_job_id": "mock-job-1", "title": "Mock Python Engineer", "status": "published", "city": "Beijing"},
                    {"external_job_id": "mock-job-2", "title": "Mock Go Developer", "status": "published", "city": "Shanghai"},
                ],
                "total": 2
            }

        list_jobs_path = self._credentials.list_jobs_path
        if not list_jobs_path:
            raise InvalidConnectorConfigError("BOSS list_jobs_path is required in live mode")

        # 对齐抓包到的真实参数
        payload = {
            "position": 0,
            "type": 0,
            "searchStr": "",
            "comId": "",
            "tagIdStr": "",
            "page": page,
            "pageSize": page_size
        }

        response_payload = self._send_live_request(
            self._build_live_url(list_jobs_path),
            payload,
            method="GET"
        )
        return {
            "items": self._extract_job_items(response_payload),
            "raw_payload": response_payload,
        }

    def _extract_job_items(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        raw_items = self._find_first_list(
            payload,
            paths=[("zpData", "data"), ("zpData", "list"), ("data", "list"), ("list",)]
        )
        if not raw_items:
            return []
        normalized = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            normalized.append({
                "external_job_id": self._pick_first(item, ("encryptJobId", "jobId", "postId", "securityId", "id")),
                "title": self._pick_first(item, ("jobName", "title", "name")),
                "status": self._pick_first(item, ("jobStatus", "status", "publishStatus")),
                "salary": self._pick_first(item, ("salaryDesc", "salary")),
                "city": self._pick_first(item, ("locationName", "cityName", "city")),
            })
        return normalized

    def list_applicants(self, job_external_id: str, cursor: str | None = None) -> dict[str, Any]:
        if self._credentials.mode == "mock":
            if cursor is None:
                return {
                    "items": [
                        {
                            "external_candidate_id": f"{job_external_id}-cand-1",
                            "name": "Mock Candidate 1",
                            "resume_url": "https://example.com/mock-candidate-1.pdf",
                            "resume_text": "Python FastAPI SQLAlchemy",
                            "raw_profile": {"skills": ["Python", "FastAPI", "SQLAlchemy"], "source_cursor": "initial"},
                        }
                    ],
                    "next_cursor": "cursor-1",
                    "has_more": True,
                }
            if cursor == "cursor-1":
                return {
                    "items": [
                        {
                            "external_candidate_id": f"{job_external_id}-cand-2",
                            "name": "Mock Candidate 2",
                            "resume_url": "https://example.com/mock-candidate-2.pdf",
                            "resume_text": "Golang distributed systems",
                            "raw_profile": {"skills": ["Golang", "Distributed Systems"], "source_cursor": "cursor-1"},
                        }
                    ],
                    "next_cursor": "cursor-2",
                    "has_more": True,
                }
            return {"items": [], "next_cursor": None, "has_more": False}

        response_payload = self._send_list_applicants_request(job_external_id, cursor=cursor)
        return {
            "items": self._extract_applicant_items(response_payload, job_external_id),
            "next_cursor": self._extract_next_cursor(response_payload),
            "has_more": self._extract_has_more(response_payload, self._extract_next_cursor(response_payload)),
            "raw_payload": response_payload,
        }

    def send_greeting(self, candidate_external_id: str, template_id: str, variables: dict[str, Any]) -> dict[str, Any]:
        if self._credentials.mode == "mock":
            conversation_id = f"boss-conv-{candidate_external_id}"
            return {
                "status": "sent",
                "external_conversation_id": conversation_id,
                "message_id": f"{conversation_id}-greet-{uuid.uuid4()}",
                "content": f"Hi {variables.get('name', '')}".strip(),
                "mode": "mock",
            }

        greet_path = self._credentials.greet_path
        if not greet_path:
            raise InvalidConnectorConfigError("BOSS greet_path is required in live mode")
        response_payload = self._send_live_request(
            self._build_live_url(greet_path),
            {"candidateId": candidate_external_id, "templateId": template_id, "variables": variables},
        )
        return {
            "status": "sent",
            "external_conversation_id": self._extract_conversation_id(response_payload, candidate_external_id),
            "message_id": self._extract_message_id(response_payload),
            "content": self._extract_message_content(response_payload),
            "raw_payload": response_payload,
        }

    def fetch_messages(self, conversation_external_id: str, cursor: str | None = None) -> dict[str, Any]:
        if self._credentials.mode == "mock":
            # ... (mock code stays same)
            pass

        fetch_messages_path = self._credentials.fetch_messages_path
        if not fetch_messages_path:
            raise InvalidConnectorConfigError("BOSS fetch_messages_path is required in live mode")
        payload: dict[str, Any] = {"conversationId": conversation_external_id}
        if cursor:
            payload["cursor"] = cursor
        response_payload = self._send_live_request(self._build_live_url(fetch_messages_path), payload, method="GET")
        return {
            "messages": self._extract_message_items(response_payload),
            "next_cursor": self._extract_next_cursor(response_payload),
            "has_more": self._extract_has_more(response_payload, self._extract_next_cursor(response_payload)),
            "raw_payload": response_payload,
        }

    def send_message(self, target_id: str, message: str, job_id: str | None = None, numeric_uid: int | str | None = None, numeric_job_id: int | str | None = None) -> dict[str, Any]:
        """向候选人发送私信消息。采用 解锁 (block/v2) + 私信 (send.json) 鲁棒双保险策略。"""
        if self._credentials.mode == "mock":
            return {"status": "sent", "message_id": f"mock-{uuid.uuid4()}"}

        # --- 第 1 步：解锁并回复投递意向 (block/v2) ---
        print(f"[boss_connector] Step 1: Triggering block/v2 for recruitment action...", flush=True)
        unblock_path = "/wapi/zpblock/chat/reply/block/v2"
        unblock_payload = {
            "securityId": target_id,
            "encryptJid": job_id or "",
            "autoRelease": 1,
            "bgSource": 1,
            "msg": message,       # 兼容一些老版本的直发
            "message": message    # 冗余
        }
        
        try:
            # 第一步不一定要成功（如果已经解锁过），报错则忽略并进入下一步
            unblock_resp = self._send_live_request(
                self._build_live_url(unblock_path),
                unblock_payload,
                method="POST",
                is_json=True
            )
            print(f"[boss_connector] Step 1 Response: {unblock_resp.get('message', 'Success')}", flush=True)
        except Exception as e:
            # 特别处理 121 报错，告知用户这通常是因为重复解锁
            print(f"[boss_connector] Step 1 Unblock logic skipped (possibly already unblocked): {e}", flush=True)

        # --- 第 2 步：核心投递 (send.json) ---
        # 如果有 UID，这一步是产生 App 聊天记录的关键
        if not numeric_uid:
            print("[boss_connector] Warning: No numeric_uid provided, Step 2 might fail for new candidates.", flush=True)

        print(f"[boss_connector] Step 2: Sending direct chat message via send.json to UID {numeric_uid}...", flush=True)
        send_path = "/wapi/zpchat/conversation/send.json"
        
        send_payload = {
            "toId": numeric_uid or "",
            "msg": message,
            "jobId": numeric_job_id or "",
            "securityId": target_id
        }

        response_payload = self._send_live_request(
            self._build_live_url(send_path),
            send_payload,
            method="POST",
            is_json=True
        )
        
        print(f"[boss_connector] Step 2 Response: {json.dumps(response_payload)}", flush=True)

        return {
            "status": "sent",
            "message_id": self._extract_message_id(response_payload) or f"boss-live-msg-{uuid.uuid4()}",
            "raw_payload": response_payload,
        }

    def schedule_interview(self, candidate_external_id: str, slot: dict[str, Any]) -> dict[str, Any]:
        if self._credentials.mode == "mock":
            # ...
            pass

        schedule_path = self._credentials.interview_schedule_path
        if not schedule_path:
            raise InvalidConnectorConfigError("BOSS interview_schedule_path is required in live mode")
        payload = {
            "candidateId": candidate_external_id,
            "scheduledAt": slot.get("scheduled_at"),
            "meetingLink": slot.get("meeting_link"),
            "meetingProvider": slot.get("meeting_provider"),
            "note": slot.get("note"),
        }
        response_payload = self._send_live_request(self._build_live_url(schedule_path), payload, method="POST")
        return {
            "status": self._extract_interview_status(response_payload, default="scheduled"),
            "external_interview_id": self._extract_external_interview_id(response_payload),
            "raw_payload": response_payload,
        }

    def sync_interview_status(self, external_interview_id: str) -> dict[str, Any]:
        if self._credentials.mode == "mock":
            # ...
            pass

        status_path = self._credentials.interview_status_path
        if not status_path:
            raise InvalidConnectorConfigError("BOSS interview_status_path is required in live mode")
        response_payload = self._send_live_request(
            self._build_live_url(status_path),
            {"interviewId": external_interview_id},
            method="GET"
        )
        return {
            "status": self._extract_interview_status(response_payload, default="unknown"),
            "external_interview_id": external_interview_id,
            "raw_payload": response_payload,
        }

    def _build_live_publish_payload(self, job_payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "jobName": job_payload.get("title"),
            "postDescription": job_payload.get("requirements"),
            "cityName": job_payload.get("city"),
            "salaryDesc": job_payload.get("salary_range"),
            "department": job_payload.get("department"),
        }

    def _send_publish_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._send_live_request(self._build_live_url(self._credentials.publish_path), payload, method="POST")

    def _send_status_request(self, external_job_id: str) -> dict[str, Any]:
        # BOSS 状态查询通常是 GET
        return self._send_live_request(self._build_live_url(self._credentials.status_path), {"jobId": external_job_id}, method="GET")

    def _send_list_applicants_request(self, job_external_id: str | None = None, cursor: str | None = None) -> dict[str, Any]:
        # 用户提供的最新抓包结果显示，该列表是 POST 请求
        payload: dict[str, Any] = {
            "page": 1,
            "pageSize": 50
        }
        if job_external_id:
            payload["jobId"] = job_external_id
            
        if cursor:
            payload["page"] = cursor # 或其他分页逻辑
            
        return self._send_live_request(self._build_live_url(self._credentials.applicants_path), payload, method="POST", is_json=False)

    def _send_live_request(self, url: str, payload: dict[str, Any], method: str = "POST", is_json: bool = True) -> dict[str, Any]:
        """增强型请求处理器，支持 JSON 和 Form-Data 双模态。"""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Cookie": self._credentials.cookie_header or "",
            "Referer": f"{self._credentials.base_url}/web/boss/index",
            "Origin": self._credentials.base_url
        }

        # 动态处理 Content-Type
        if is_json:
            headers["Content-Type"] = "application/json; charset=UTF-8"
            body = json.dumps(payload) if method.upper() == "POST" else None
            params = payload if method.upper() == "GET" else None
        else:
            # application/x-www-form-urlencoded 是列表类接口的标配
            # requests.request(data=payload) 且不设置 Content-Type 时会自动填充
            body = payload if method.upper() == "POST" else None
            params = payload if method.upper() == "GET" else None

        try:
            response = requests.request(
                method=method,
                url=url,
                headers=headers,
                data=body,
                params=params,
                timeout=12
            )
            
            # 记录原始文本用于调试
            raw_text = response.text
            response.raise_for_status()
            
            parsed = response.json()
        except requests.exceptions.RequestException as exc:
            msg = f"BOSS request {method} {url} failed: {exc}"
            if hasattr(exc, 'response') and exc.response is not None:
                msg += f" | Response: {exc.response.text[:200]}"
            raise ConnectorOperationError(msg) from exc
        except Exception as exc:
            raise ConnectorOperationError(f"BOSS processing failed: {exc}") from exc

        code = parsed.get("code")
        if code not in (None, 0):
            raise ConnectorOperationError(f"BOSS request failed: code={code}, message={parsed.get('message', 'Unknown error')}")
        return parsed

    def _build_live_url(self, path: str | None) -> str:
        base_url = (self._credentials.base_url or "").rstrip("/")
        resolved_path = path or ""
        if resolved_path.startswith(("http://", "https://")):
            return resolved_path
        return parse.urljoin(base_url + "/", resolved_path.lstrip("/"))

    def _build_live_headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://www.zhipin.com/web/geek/chat",
            "Origin": "https://www.zhipin.com",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        cookie_header = self._resolve_cookie_header()
        if cookie_header:
            headers["Cookie"] = cookie_header
        if self._credentials.secret.strip():
            headers["Authorization"] = f"Bearer {self._credentials.secret.strip()}"
        return headers

    def _resolve_cookie_header(self) -> str | None:
        if self._credentials.cookie_header:
            return self._credentials.cookie_header.strip() or None
        env_cookie = os.getenv("AI_HR_BOSS_COOKIES") or os.getenv("BOSS_COOKIES")
        if env_cookie:
            return env_cookie.strip()
        credential_path = self._credentials.credential_file or os.getenv("AI_HR_BOSS_CREDENTIAL_FILE")
        if credential_path:
            loaded = self._load_cookie_header_from_file(Path(credential_path))
            if loaded:
                return loaded
        return self._load_cookie_header_from_file(Path.home() / ".config" / "boss-cli" / "credential.json")

    def _load_cookie_header_from_file(self, file_path: Path) -> str | None:
        if not file_path.exists():
            return None
        try:
            content = json.loads(file_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        cookies = content.get("cookies")
        if not isinstance(cookies, dict) or not cookies:
            return None
        pairs = [f"{key}={value}" for key, value in cookies.items() if str(key).strip() and str(value).strip()]
        return "; ".join(pairs) if pairs else None

    def _extract_external_job_id(self, payload: dict[str, Any]) -> str:
        value = self._pick_nested_first(
            payload,
            paths=[("zpData", "jobId"), ("zpData", "postId"), ("zpData", "securityId"), ("data", "jobId"), ("jobId",), ("id",)],
        )
        return str(value) if value else f"boss-live-{uuid.uuid4()}"

    def _extract_job_status(self, payload: dict[str, Any]) -> str:
        value = self._pick_nested_first(
            payload,
            paths=[("zpData", "status"), ("zpData", "publishStatus"), ("data", "status"), ("status",), ("publishStatus",)],
        )
        return str(value).strip().lower() if value else "unknown"

    def _extract_applicant_items(self, payload: dict[str, Any], filter_job_id: str | None = None) -> list[dict[str, Any]]:
        raw_items = self._find_first_list(
            payload,
            paths=[
                ("zpData", "friendList"),
                ("zpData", "items"),
                ("zpData", "candidates"),
                ("zpData", "geekList"),
                ("data", "friendList"),
                ("items",),
                ("list",),
            ],
        )
        if not raw_items:
            return []
        normalized = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            
            # 如果提供了职位 ID，则过滤出对应岗位的候选人
            item_job_id = self._pick_first(item, ("encryptJobId", "jobId"))
            if filter_job_id and item_job_id and str(item_job_id) != str(filter_job_id):
                continue

            external_candidate_id = self._pick_first(item, ("securityId", "encryptUid", "candidateId", "geekId", "userId", "id"))
            if not external_candidate_id:
                continue
            
            normalized.append(
                {
                    "external_candidate_id": str(external_candidate_id),
                    "name": self._pick_first(item, ("name", "candidateName", "geekName", "userName")),
                    "phone_hash": self._pick_first(item, ("phone_hash", "phoneHash", "mobileHash")),
                    "email_hash": self._pick_first(item, ("email_hash", "emailHash")),
                    "resume_url": self._pick_first(item, ("resume_url", "resumeUrl", "cvUrl")),
                    "resume_text": self._pick_first(item, ("resume_text", "resumeText", "cvText")),
                    "raw_profile": item,
                }
            )
        return normalized

    def _extract_message_items(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        raw_items = self._find_first_list(
            payload,
            paths=[("zpData", "messages"), ("zpData", "messageList"), ("data", "messages"), ("messages",), ("list",)],
        )
        if not raw_items:
            return []
        normalized = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            content = self._pick_first(item, ("content", "message", "text"))
            if not content:
                continue
            sender = self._pick_first(item, ("sender", "senderRole", "from")) or "candidate"
            direction = "outbound" if str(sender).lower() in {"hr", "recruiter", "system", "outbound"} else "inbound"
            normalized.append(
                {
                    "external_message_id": self._pick_first(item, ("messageId", "msgId", "id", "message_id")),
                    "direction": direction,
                    "sender": "hr" if direction == "outbound" else "candidate",
                    "content": str(content),
                    "sent_at": self._pick_first(item, ("sentAt", "sendTime", "timestamp", "createdAt")) or datetime.now(UTC).replace(tzinfo=None).isoformat(),
                    "meta": item,
                }
            )
        return normalized

    def _extract_next_cursor(self, payload: dict[str, Any]) -> str | None:
        value = self._pick_nested_first(
            payload,
            paths=[("zpData", "next_cursor"), ("zpData", "nextCursor"), ("data", "next_cursor"), ("data", "nextCursor"), ("next_cursor",), ("nextCursor",), ("cursor",)],
        )
        return str(value).strip() if value is not None and str(value).strip() else None

    def _extract_has_more(self, payload: dict[str, Any], next_cursor: str | None) -> bool:
        value = self._pick_nested_first(
            payload,
            paths=[("zpData", "has_more"), ("zpData", "hasMore"), ("data", "has_more"), ("data", "hasMore"), ("has_more",), ("hasMore",), ("more",)],
        )
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            return value != 0
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"true", "1", "yes", "y"}:
                return True
            if lowered in {"false", "0", "no", "n"}:
                return False
        return next_cursor is not None

    def _extract_conversation_id(self, payload: dict[str, Any], fallback: str) -> str:
        value = self._pick_nested_first(
            payload,
            paths=[("zpData", "conversationId"), ("data", "conversationId"), ("conversationId",), ("id",)],
        )
        return str(value) if value else f"boss-conv-{fallback}"

    def _extract_message_id(self, payload: dict[str, Any]) -> str | None:
        value = self._pick_nested_first(
            payload,
            paths=[("zpData", "messageId"), ("zpData", "msgId"), ("data", "messageId"), ("messageId",), ("msgId",), ("id",)],
        )
        return str(value).strip() if value is not None and str(value).strip() else None

    def _extract_message_content(self, payload: dict[str, Any]) -> str | None:
        value = self._pick_nested_first(
            payload,
            paths=[("zpData", "content"), ("zpData", "message"), ("data", "content"), ("content",), ("message",)],
        )
        return str(value).strip() if value is not None and str(value).strip() else None

    def _extract_external_interview_id(self, payload: dict[str, Any]) -> str:
        value = self._pick_nested_first(
            payload,
            paths=[("zpData", "interviewId"), ("zpData", "appointmentId"), ("data", "interviewId"), ("interviewId",), ("appointmentId",), ("id",)],
        )
        return str(value) if value else f"boss-intv-{uuid.uuid4()}"

    def _extract_interview_status(self, payload: dict[str, Any], *, default: str) -> str:
        value = self._pick_nested_first(
            payload,
            paths=[("zpData", "status"), ("zpData", "interviewStatus"), ("data", "status"), ("status",), ("interviewStatus",)],
        )
        if value is None:
            return default
        normalized = str(value).strip().lower()
        return normalized or default

    def _find_first_list(self, payload: dict[str, Any], paths: list[tuple[str, ...]]) -> list[Any] | None:
        for path in paths:
            value = self._dig(payload, path)
            if isinstance(value, list):
                return value
        return None

    def _pick_nested_first(self, payload: dict[str, Any], paths: list[tuple[str, ...]]) -> Any:
        for path in paths:
            value = self._dig(payload, path)
            if value is not None:
                return value
        return None

    def _dig(self, payload: dict[str, Any], path: tuple[str, ...]) -> Any:
        current: Any = payload
        for key in path:
            if not isinstance(current, dict):
                return None
            current = current.get(key)
        return current

    def _pick_first(self, payload: dict[str, Any], keys: tuple[str, ...]) -> Any:
        for key in keys:
            value = payload.get(key)
            if value is not None and str(value).strip():
                return value
        return None

