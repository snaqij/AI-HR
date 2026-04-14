"""BOSS 连接器实现。"""

from __future__ import annotations

import json
import os
import uuid
import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
import requests
from urllib import parse
from urllib.parse import unquote

from ..core.exceptions import ConnectorOperationError, InvalidConnectorConfigError, CredentialsExpiredError
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
        raw_items = self._extract_raw_applicant_items(response_payload)
        current_page = self._coerce_page_number(cursor)
        next_cursor = self._extract_next_cursor(response_payload)
        if next_cursor is None:
            next_cursor = str(current_page + 1) if len(raw_items) >= 100 else None
        return {
            "items": self._extract_applicant_items(response_payload, job_external_id),
            "next_cursor": next_cursor,
            "has_more": self._extract_has_more(response_payload, next_cursor, raw_count=len(raw_items)),
            "raw_payload": response_payload,
        }

    def list_resume_ready_candidates(
        self,
        job_external_id: str | None = None,
        *,
        label_id: int = 4,
        sort: str = "",
    ) -> dict[str, Any]:
        if self._credentials.mode == "mock":
            return {
                "items": [
                    {
                        "external_candidate_id": "resume-ready-1",
                        "name": "Mock Resume Ready",
                        "resume_url": None,
                        "resume_text": None,
                        "raw_profile": {
                            "uid": 1001,
                            "encryptUid": "enc-1001",
                            "encryptFriendId": "enc-1001",
                            "encryptJobId": job_external_id or "mock-job",
                            "resumeVisible": 1,
                        },
                    }
                ],
                "raw_payload": {"mode": "mock"},
            }

        payload = {"labelId": label_id, "encJobId": job_external_id or "", "sort": sort}
        response_payload = self._send_live_request(
            self._build_live_url("/wapi/zprelation/friend/filterByLabel"),
            payload,
            method="POST",
            is_json=False,
        )
        rows = self._pick_nested_first(response_payload, [("zpData", "result")]) or []
        items: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            geek_detail = self._fetch_boss_geek_detail(
                {
                    "uid": row.get("friendId"),
                    "friendSource": row.get("friendSource", 0),
                }
            )
            if job_external_id and str(geek_detail.get("toPositionId") or "") != str(job_external_id):
                continue
            merged_profile = dict(geek_detail or {})
            merged_profile["friendId"] = row.get("friendId")
            merged_profile["encryptFriendId"] = row.get("encryptFriendId")
            merged_profile["friendSource"] = row.get("friendSource", 0)
            merged_profile["waterLevel"] = row.get("waterLevel")
            merged_profile["updateTime"] = row.get("updateTime")
            items.append(
                {
                    "external_candidate_id": str(geek_detail.get("securityId") or row.get("encryptFriendId") or row.get("friendId")),
                    "name": geek_detail.get("name") or "Unknown",
                    "resume_url": None,
                    "resume_text": None,
                    "raw_profile": merged_profile,
                }
            )
        return {"items": items, "raw_payload": response_payload}

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
            if cursor is None:
                return {
                    "messages": [
                        {
                            "external_message_id": f"{conversation_external_id}-msg-1",
                            "direction": "inbound",
                            "sender": "candidate",
                            "content": "您好，我对这个岗位感兴趣。",
                            "sent_at": datetime.now(UTC).replace(tzinfo=None).isoformat(),
                            "meta": {"mode": "mock"},
                        }
                    ],
                    "next_cursor": "cursor-1",
                    "has_more": True,
                    "raw_payload": {"mode": "mock"},
                }
            if cursor == "cursor-1":
                return {
                    "messages": [
                        {
                            "external_message_id": f"{conversation_external_id}-msg-2",
                            "direction": "inbound",
                            "sender": "candidate",
                            "content": "这个岗位薪资范围大概是多少？",
                            "sent_at": datetime.now(UTC).replace(tzinfo=None).isoformat(),
                            "meta": {"mode": "mock"},
                        }
                    ],
                    "next_cursor": "cursor-2",
                    "has_more": True,
                    "raw_payload": {"mode": "mock"},
                }
            return {
                "messages": [],
                "next_cursor": None,
                "has_more": False,
                "raw_payload": {"mode": "mock"},
            }

        fetch_messages_path = self._credentials.fetch_messages_path
        if not fetch_messages_path:
            raise InvalidConnectorConfigError("BOSS fetch_messages_path is required in live mode")
        payload: dict[str, Any] = {"conversationId": conversation_external_id}
        if cursor:
            payload["cursor"] = cursor
        response_payload = self._send_live_request(self._build_live_url(fetch_messages_path), payload)
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

        send_message_path = self._credentials.send_message_path
        if send_message_path and not numeric_uid and not numeric_job_id:
            response_payload = self._send_live_request(
                self._build_live_url(send_message_path),
                {"conversationId": target_id, "message": message},
            )
            return {
                "status": "sent",
                "message_id": self._extract_message_id(response_payload) or f"boss-live-msg-{uuid.uuid4()}",
                "raw_payload": response_payload,
            }

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

    def fetch_resume_attachment(self, candidate_external_id: str, raw_profile: dict[str, Any] | None = None) -> dict[str, Any]:
        if self._credentials.mode == "mock":
            content = b"%PDF-1.4 mock resume content\n%%EOF"
            return {
                "file_name": "mock-resume.pdf",
                "content_type": "application/pdf",
                "source_url": "https://example.com/mock-resume.pdf",
                "file_size_bytes": len(content),
                "file_sha256": hashlib.sha256(content).hexdigest(),
                "content_bytes": content,
                "raw_payload": {"mode": "mock", "candidate_external_id": candidate_external_id},
            }

        profile = raw_profile or {}
        geek_detail = self._fetch_boss_geek_detail(profile)
        download_result = self._download_resume_via_docdownload(geek_detail, candidate_external_id)
        if download_result is not None:
            return download_result

        detail_payload = self._fetch_resume_detail_payload(candidate_external_id, profile)
        attachment = self._extract_resume_attachment(detail_payload)
        source_url = attachment.get("source_url")
        if not source_url:
            raise ConnectorOperationError("BOSS resume detail response did not include a downloadable attachment URL")

        file_bytes, content_type = self._download_binary(source_url)
        file_name = attachment.get("file_name") or self._derive_filename_from_url(source_url)
        return {
            "file_name": file_name,
            "content_type": attachment.get("content_type") or content_type,
            "source_url": source_url,
            "file_size_bytes": len(file_bytes),
            "file_sha256": hashlib.sha256(file_bytes).hexdigest(),
            "content_bytes": file_bytes,
            "raw_payload": detail_payload,
            "resume_text": attachment.get("resume_text"),
        }

    def request_resume_access(self, candidate_external_id: str, raw_profile: dict[str, Any] | None = None) -> dict[str, Any]:
        if self._credentials.mode == "mock":
            profile = raw_profile or {}
            visible = bool(profile.get("mock_resume_visible_after_request", True))
            detail = {
                "uid": 123,
                "securityId": candidate_external_id,
                "encryptUid": "mock-encrypt-uid",
                "resumeVisible": 1 if visible else 0,
                "friendSource": 0,
            }
            return {
                "request_status": 0,
                "request_sent": True,
                "resume_visible": visible,
                "security_id": candidate_external_id,
                "detail": detail,
                "raw_payload": {"mode": "mock", "request": {"type": 4, "securityId": candidate_external_id}},
            }

        profile = raw_profile or {}
        geek_detail = self._fetch_boss_geek_detail(profile)
        security_id = (
            geek_detail.get("securityId")
            or profile.get("securityId")
            or candidate_external_id
        )
        if not security_id:
            raise ConnectorOperationError("BOSS resume request requires candidate securityId")

        if int(geek_detail.get("resumeVisible") or 0) == 1:
            return {
                "request_status": 4,
                "request_sent": False,
                "resume_visible": True,
                "security_id": str(security_id),
                "detail": geek_detail,
                "raw_payload": {
                    "request": None,
                    "detail": geek_detail,
                    "short_circuit": "already_resume_visible",
                },
            }

        request_payload = {"type": 4, "securityId": security_id}
        response = self._send_live_request(
            self._build_live_url("/wapi/zpchat/exchange/request"),
            request_payload,
            method="POST",
            is_json=False,
        )
        refreshed_detail = self._fetch_boss_geek_detail(
            {
                **profile,
                "uid": geek_detail.get("uid") or profile.get("uid"),
                "friendSource": geek_detail.get("friendSource", profile.get("friendSource", 0)),
            }
        )
        merged_detail = dict(geek_detail or {})
        merged_detail.update(refreshed_detail or {})
        status = self._pick_nested_first(response, [("zpData", "status")])
        return {
            "request_status": int(status) if status is not None else None,
            "request_sent": status in (0, 1),
            "resume_visible": int(merged_detail.get("resumeVisible") or 0) == 1,
            "security_id": str(merged_detail.get("securityId") or security_id),
            "detail": merged_detail,
            "raw_payload": {
                "request": response,
                "detail": refreshed_detail,
            },
        }

    def check_resume_access(self, candidate_external_id: str, raw_profile: dict[str, Any] | None = None) -> dict[str, Any]:
        if self._credentials.mode == "mock":
            profile = raw_profile or {}
            visible = bool(profile.get("mock_resume_retry_visible", profile.get("mock_resume_visible_after_request", True)))
            detail = {
                "uid": profile.get("uid", 123),
                "securityId": candidate_external_id,
                "encryptUid": profile.get("encryptUid", "mock-encrypt-uid"),
                "resumeVisible": 1 if visible else 0,
                "friendSource": profile.get("friendSource", 0),
            }
            return {
                "resume_visible": visible,
                "security_id": candidate_external_id,
                "detail": detail,
                "raw_payload": {"mode": "mock", "detail": detail},
            }

        profile = raw_profile or {}
        geek_detail = self._fetch_boss_geek_detail(profile)
        security_id = geek_detail.get("securityId") or profile.get("securityId") or candidate_external_id
        return {
            "resume_visible": int(geek_detail.get("resumeVisible") or 0) == 1,
            "security_id": str(security_id) if security_id else None,
            "detail": geek_detail,
            "raw_payload": {"detail": geek_detail},
        }

    def _fetch_boss_geek_detail(self, raw_profile: dict[str, Any]) -> dict[str, Any]:
        """内部方法：同步获取候选人原始详情报文。"""
        if self._credentials.mode == "mock":
            return raw_profile

        uid = raw_profile.get("uid")
        if not uid:
            return raw_profile
            
        response = self._send_live_request(
            self._build_live_url("/wapi/zpboss/h5/chat/geek.json"),
            {"uid": uid, "geekSource": raw_profile.get("friendSource", 0)},
            method="GET",
        )
        return self._pick_nested_first(response, [("zpData", "data")]) or {}

    def fetch_candidate_detail(self, raw_profile: dict[str, Any]) -> dict[str, Any]:
        """抓取候选人详细画像信息。"""
        if self._credentials.mode == "mock":
            return {
                "school": "Mock University",
                "degree": "Master",
                "work_experience": "5 years",
                "expected_salary": "20k-30k",
                "latest_company": "Mock Corp",
                "raw_profile": {"detail": "mock"},
            }

        data = self._fetch_boss_geek_detail(raw_profile)
        
        # 详情报文解析逻辑
        detail_info = {
            "school": self._pick_first(data, ("school", "schoolName", "university")),
            "degree": self._pick_first(data, ("degree", "edu", "degreeName", "education")),
            "work_experience": self._pick_first(data, ("experience", "workYears", "workExperience", "lastWorkExpr")),
            "expected_salary": self._pick_first(data, ("salaryDesc", "expectSalary", "salary")),
            "latest_company": self._pick_first(data, ("companyName", "company", "latestCompany", "lastCompany")),
            "raw_profile": data,
        }

        # 深度回溯：如果关键字段缺失，尝试从列表字段中提取
        if not detail_info["degree"]:
            edu_list = data.get("eduExpList") or data.get("educationList")
            if edu_list and isinstance(edu_list, list) and len(edu_list) > 0:
                first_edu = edu_list[0]
                detail_info["degree"] = self._pick_first(first_edu, ("degree", "education"))
                if not detail_info["school"]:
                    detail_info["school"] = self._pick_first(first_edu, ("school", "schoolName"))

        if not detail_info["latest_company"]:
            work_list = data.get("workExpList") or data.get("experienceList")
            if work_list and isinstance(work_list, list) and len(work_list) > 0:
                detail_info["latest_company"] = self._pick_first(work_list[0], ("company", "companyName"))

        return detail_info

    def _download_resume_via_docdownload(
        self,
        geek_detail: dict[str, Any],
        candidate_external_id: str,
    ) -> dict[str, Any] | None:
        candidate_ids = [
            geek_detail.get("encryptUid"),
            geek_detail.get("encryptFriendId"),
            geek_detail.get("encryptExpectId"),
            geek_detail.get("uid"),
            geek_detail.get("expectId"),
            candidate_external_id,
            geek_detail.get("securityId"),
        ]
        errors: list[str] = []
        for candidate_id in candidate_ids:
            if candidate_id in (None, ""):
                continue
            try:
                response = self._request_docdownload(candidate_id)
            except ConnectorOperationError as exc:
                errors.append(f"{candidate_id}: {exc}")
                continue

            content_type = response.headers.get("Content-Type", "")
            content_disposition = response.headers.get("Content-Disposition", "")
            if self._looks_like_file_response(response):
                file_name = self._filename_from_content_disposition(content_disposition) or f"boss-resume-{candidate_id}.bin"
                return {
                    "file_name": file_name,
                    "content_type": content_type or "application/octet-stream",
                    "source_url": str(response.url),
                    "file_size_bytes": len(response.content),
                    "file_sha256": hashlib.sha256(response.content).hexdigest(),
                    "content_bytes": response.content,
                    "raw_payload": {"geek_detail": geek_detail, "docdownload_candidate_id": str(candidate_id)},
                    "resume_text": None,
                }

            html_text = response.text
            if "抱歉，您没有权限查看该文件" in html_text:
                errors.append(f"{candidate_id}: no permission to view attachment")
                continue
            if "牛人信息错误" in html_text:
                errors.append(f"{candidate_id}: invalid candidate identifier for download4boss")
                continue
            errors.append(f"{candidate_id}: unexpected docdownload response content-type={content_type}")

        if geek_detail:
            raise ConnectorOperationError(
                "BOSS attachment download is currently unavailable for this candidate. "
                f"signals=resumeVisible:{geek_detail.get('resumeVisible')}, "
                f"showCandidate:{geek_detail.get('showCandidate')}, "
                f"completeType:{geek_detail.get('completeType')}. "
                f"attempted={errors[:6]}"
            )
        return None

    def _request_docdownload(self, candidate_id: Any) -> requests.Response:
        headers = self._build_headers()
        headers["Accept"] = "*/*"
        headers["Referer"] = f"{self._credentials.base_url}/web/chat/index"
        candidate_id_str = str(candidate_id)
        urls = [
            f"https://docdownload.zhipin.com/wflow/zpgeek/download/download4boss/{candidate_id_str}?id=",
            f"https://docdownload.zhipin.com/wapi/zpgeek/resume/attachment/download4boss/{candidate_id_str}",
        ]
        errors: list[str] = []
        for url in urls:
            try:
                response = requests.get(url, headers=headers, timeout=20, allow_redirects=True, verify=False)
                response.raise_for_status()
                return response
            except requests.exceptions.RequestException as exc:
                errors.append(f"{url}: {exc}")
        raise ConnectorOperationError(f"BOSS docdownload failed: {errors[:2]}")

    def _looks_like_file_response(self, response: requests.Response) -> bool:
        content_type = (response.headers.get("Content-Type") or "").lower()
        if any(token in content_type for token in ("application/pdf", "application/msword", "application/vnd", "application/octet-stream")):
            return True
        content_disposition = (response.headers.get("Content-Disposition") or "").lower()
        return "attachment" in content_disposition or "filename=" in content_disposition

    def _filename_from_content_disposition(self, content_disposition: str | None) -> str | None:
        if not content_disposition:
            return None
        for token in content_disposition.split(";"):
            token = token.strip()
            if token.lower().startswith("filename*="):
                encoded = token.split("''", 1)[-1]
                return unquote(encoded).strip().strip('"')
            if token.lower().startswith("filename="):
                return unquote(token.split("=", 1)[1].strip().strip('"'))
        return None

    def _fetch_resume_detail_payload(self, candidate_external_id: str, raw_profile: dict[str, Any]) -> dict[str, Any]:
        errors: list[str] = []
        for request in self._iter_resume_detail_requests():
            for payload_label, payload in self._iter_resume_detail_payloads(candidate_external_id, raw_profile):
                try:
                    response = self._send_live_request(
                        self._build_live_url(request["path"]),
                        payload,
                        method=request["method"],
                        is_json=request["is_json"],
                    )
                except ConnectorOperationError as exc:
                    errors.append(f'{request["method"]} {request["path"]} [{payload_label}]: {exc}')
                    continue

                attachment = self._extract_resume_attachment(response)
                if attachment.get("source_url") or attachment.get("resume_text"):
                    response.setdefault("_matched_resume_request", {**request, "payload_label": payload_label})
                    return response
                errors.append(
                    f'{request["method"]} {request["path"]} [{payload_label}]: response did not include attachment fields'
                )

        raise ConnectorOperationError(
            "BOSS resume detail probing failed for candidate "
            f"{candidate_external_id}. attempted={errors[:8]}"
        )

    def _iter_resume_detail_requests(self) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        seen: set[tuple[str, str, bool]] = set()

        def add(path: str | None, method: str, is_json: bool) -> None:
            if not path:
                return
            key = (path, method, is_json)
            if key in seen:
                return
            seen.add(key)
            candidates.append({"path": path, "method": method, "is_json": is_json})

        add(self._credentials.resume_detail_path, "GET", True)
        add(self._credentials.resume_detail_path, "POST", False)
        add(self._credentials.resume_detail_path, "POST", True)

        fallback_paths = [
            "/wapi/zprelation/resume/detail.json",
            "/wapi/zprelation/resume/attachment/detail.json",
            "/wapi/zprelation/resume/attachment.json",
            "/wapi/zprelation/geek/resume/detail.json",
            "/wapi/zprelation/geek/resume/attachment.json",
            "/wapi/zpgeek/resume/detail.json",
            "/wapi/zpgeek/resume/attachment/detail.json",
            "/wapi/zpgeek/view/geek/resume/detail.json",
            "/wapi/zpgeek/view/geek/resume/attachment.json",
            "/wapi/zpboss/h5/geek/resume/detail",
            "/wapi/zpboss/h5/geek/resume/attachment",
        ]
        for path in fallback_paths:
            add(path, "GET", True)
            add(path, "POST", False)

        return candidates

    def _iter_resume_detail_payloads(
        self,
        candidate_external_id: str,
        raw_profile: dict[str, Any],
    ) -> list[tuple[str, dict[str, Any]]]:
        base_payload = self._build_resume_detail_payload(candidate_external_id, raw_profile)
        variants: list[tuple[str, dict[str, Any]]] = []
        seen: set[str] = set()

        def add(label: str, payload: dict[str, Any]) -> None:
            normalized = {key: value for key, value in payload.items() if value not in (None, "")}
            fingerprint = json.dumps(normalized, sort_keys=True, ensure_ascii=True)
            if not normalized or fingerprint in seen:
                return
            seen.add(fingerprint)
            variants.append((label, normalized))

        add("all", base_payload)
        add("security_only", {"securityId": candidate_external_id})
        add("security_uid", {"securityId": candidate_external_id, "uid": raw_profile.get("uid")})
        add("security_encrypt_uid", {"securityId": candidate_external_id, "encryptUid": raw_profile.get("encryptUid")})
        add("security_job", {"securityId": candidate_external_id, "jobId": raw_profile.get("jobId")})
        add("security_encrypt_job", {"securityId": candidate_external_id, "encryptJobId": raw_profile.get("encryptJobId")})
        add("security_expect", {"securityId": candidate_external_id, "expectId": raw_profile.get("expectId")})
        add("uid_job", {"uid": raw_profile.get("uid"), "jobId": raw_profile.get("jobId")})
        add(
            "encrypt_uid_job",
            {"encryptUid": raw_profile.get("encryptUid"), "encryptJobId": raw_profile.get("encryptJobId")},
        )
        return variants

    def schedule_interview(self, candidate_external_id: str, slot: dict[str, Any]) -> dict[str, Any]:
        if self._credentials.mode == "mock":
            return {
                "status": "scheduled",
                "external_interview_id": f"mock-intv-{candidate_external_id}",
                "raw_payload": {"mode": "mock", "slot": slot},
            }

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
            return {
                "status": "scheduled",
                "external_interview_id": external_interview_id,
                "raw_payload": {"mode": "mock"},
            }

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
        headers = self._build_headers()

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
            message = parsed.get('message', 'Unknown error')
            # code 7 is a common session expiration code in BOSS
            if code in (7, 401) or "未登录" in message or "会话过期" in message:
                raise CredentialsExpiredError(f"BOSS credentials expired: {message}")
            raise ConnectorOperationError(f"BOSS request failed: code={code}, message={message}")
        return parsed

    def _build_resume_detail_payload(self, candidate_external_id: str, raw_profile: dict[str, Any]) -> dict[str, Any]:
        payload: dict[str, Any] = {"securityId": candidate_external_id}
        for field in ("uid", "encryptUid", "jobId", "encryptJobId", "expectId", "encryptExpectId"):
            value = raw_profile.get(field)
            if value not in (None, ""):
                payload[field] = value
        return payload

    def _extract_resume_attachment(self, payload: dict[str, Any]) -> dict[str, Any]:
        candidate_paths = [
            ("zpData", "attachmentInfo"),
            ("zpData", "resumeAttachment"),
            ("zpData", "resumeFile"),
            ("zpData", "resume"),
            ("data", "attachmentInfo"),
            ("data", "resumeAttachment"),
            ("attachmentInfo",),
            ("resumeAttachment",),
        ]
        attachment_payload: dict[str, Any] = {}
        for path in candidate_paths:
            value = self._pick_nested_first(payload, [path])
            if isinstance(value, dict):
                attachment_payload = value
                break

        source_url = self._pick_nested_first(
            payload,
            paths=[
                ("zpData", "resumeUrl"),
                ("zpData", "resumeAttachmentUrl"),
                ("zpData", "attachmentUrl"),
                ("zpData", "downloadUrl"),
                ("zpData", "pdfUrl"),
                ("zpData", "resumeFileUrl"),
                ("zpData", "resumeFile", "url"),
                ("zpData", "resumeAttachment", "url"),
                ("zpData", "attachmentInfo", "url"),
                ("data", "resumeUrl"),
                ("data", "downloadUrl"),
                ("resumeUrl",),
                ("downloadUrl",),
            ],
        )
        if not source_url and attachment_payload:
            source_url = self._pick_first(attachment_payload, ("url", "downloadUrl", "resumeUrl", "attachmentUrl", "fileUrl", "pdfUrl"))

        file_name = self._pick_nested_first(
            payload,
            paths=[
                ("zpData", "resumeFileName"),
                ("zpData", "fileName"),
                ("zpData", "attachmentInfo", "fileName"),
                ("data", "fileName"),
                ("fileName",),
            ],
        )
        if not file_name and attachment_payload:
            file_name = self._pick_first(attachment_payload, ("fileName", "name", "attachmentName"))

        content_type = None
        if attachment_payload:
            content_type = self._pick_first(attachment_payload, ("contentType", "mimeType", "fileType"))

        resume_text = self._pick_nested_first(
            payload,
            paths=[("zpData", "resumeText"), ("zpData", "content"), ("data", "resumeText"), ("resumeText",), ("content",)],
        )
        return {
            "source_url": str(source_url) if source_url else None,
            "file_name": str(file_name) if file_name else None,
            "content_type": str(content_type) if content_type else None,
            "resume_text": str(resume_text) if resume_text else None,
        }

    def _derive_filename_from_url(self, source_url: str) -> str:
        parsed_url = parse.urlparse(source_url)
        name = os.path.basename(parsed_url.path or "").strip()
        return name or f"boss-resume-{uuid.uuid4()}.bin"

    def _download_binary(self, url: str) -> tuple[bytes, str | None]:
        headers = self._build_headers()
        resolved_url = self._build_live_url(url)
        try:
            response = requests.get(resolved_url, headers=headers, timeout=20)
            response.raise_for_status()
        except requests.exceptions.RequestException as exc:
            raise ConnectorOperationError(f"BOSS download failed: {exc}") from exc
        return response.content, response.headers.get("Content-Type")

    def _build_live_url(self, path: str | None) -> str:
        base_url = (self._credentials.base_url or "").rstrip("/")
        resolved_path = path or ""
        if resolved_path.startswith(("http://", "https://")):
            return resolved_path
        return parse.urljoin(base_url + "/", resolved_path.lstrip("/"))

    def _build_headers(self) -> dict[str, str]:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Cookie": self._credentials.cookie_header or "",
            "Referer": f"{self._credentials.base_url}/web/chat/index",
            "Origin": self._credentials.base_url or "",
            "X-Requested-With": "XMLHttpRequest",
        }
        zp_token = self._extract_cookie_value("bst")
        if zp_token:
            headers["zp_token"] = zp_token
        return headers

    def _extract_cookie_value(self, key: str) -> str | None:
        cookie_header = self._resolve_cookie_header() or self._credentials.cookie_header or ""
        for part in cookie_header.split(";"):
            part = part.strip()
            if not part or "=" not in part:
                continue
            name, value = part.split("=", 1)
            if name.strip() == key:
                value = value.strip()
                return value or None
        return None

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
        raw_items = self._extract_raw_applicant_items(payload)
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

            # 使用稳定 ID：优先使用 encryptUid (全局唯一且固定)
            # securityId 在 BOSS 中是加密动态 ID，同一人在不同时间/上下文中可能不同，会导致重复抓取
            external_candidate_id = self._pick_first(item, ("encryptUid", "uid", "encryptExpectId", "candidateId", "geekId", "userId", "id", "securityId"))
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
                    "school": self._pick_first(item, ("schoolName", "school", "university")),
                    "degree": self._pick_first(item, ("degree", "edu", "degreeName", "education")),
                    "work_experience": self._pick_first(item, ("experienceName", "experience", "workYears", "lastWorkExpr")),
                    "expected_salary": self._pick_first(item, ("expectSalary", "salaryDesc", "salary")),
                    "latest_company": self._pick_first(item, ("companyName", "company", "lastCompany")),
                    "applied_at": self._parse_boss_timestamp(self._pick_first(item, ("applyTime", "addTime", "createTime"))),
                    "raw_profile": item,
                }
            )
            
            # 如果元数据为空但存在摘要字段，则尝试从摘要中解包信息 (BOSS 常用模式: "公司 · 5年 · 本科")
            summary_expr = item.get("lastWorkExpr")
            if summary_expr and isinstance(summary_expr, str):
                parts = [p.strip() for p in summary_expr.split("·")]
                current_item = normalized[-1]
                if len(parts) >= 2:
                    if not current_item.get("latest_company"):
                        current_item["latest_company"] = parts[0]
                    if not current_item.get("work_experience"):
                        current_item["work_experience"] = parts[1]
                    if len(parts) >= 3 and not current_item.get("degree"):
                        current_item["degree"] = parts[2]
                elif not current_item.get("work_experience"):
                    current_item["work_experience"] = summary_expr
        return normalized

    def _extract_raw_applicant_items(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
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
        return [item for item in raw_items if isinstance(item, dict)]

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

    def _extract_has_more(self, payload: dict[str, Any], next_cursor: str | None, raw_count: int | None = None) -> bool:
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
        if raw_count is not None:
            return raw_count >= 100
        return next_cursor is not None

    def _parse_boss_timestamp(self, ts: Any) -> str | None:
        if ts is None:
            return None
        try:
            # BOSS 经常返回 13 位毫秒级时间戳
            val = int(ts)
            if val > 10**11:
                val /= 1000
            return datetime.fromtimestamp(val, UTC).replace(tzinfo=None).isoformat()
        except (ValueError, TypeError):
            return str(ts) if ts else None

    def _coerce_page_number(self, cursor: str | None) -> int:
        if not cursor:
            return 1
        try:
            return max(1, int(cursor))
        except (TypeError, ValueError):
            return 1

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
