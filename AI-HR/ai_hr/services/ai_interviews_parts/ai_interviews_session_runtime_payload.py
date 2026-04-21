from __future__ import annotations

from .ai_interviews_shared import *


class AIInterviewSessionRuntimePayloadMixin:
    def _build_rtc_payload(self, rtc_info) -> dict:
        payload = {
            "rtc_vendor": rtc_info.vendor,
            "rtc_transport": rtc_info.transport,
            "rtc_app_id": rtc_info.app_id,
            "rtc_channel_name": rtc_info.channel_name or rtc_info.room_id,
            "rtc_uid": rtc_info.uid,
        }
        if rtc_info.expire_at is not None:
            payload["rtc_token_expire_at"] = self._serialize_datetime(rtc_info.expire_at)
        metadata = dict(rtc_info.metadata or {})
        if metadata.get("ten_bot_uid"):
            payload["ten_agent_user_id"] = metadata["ten_bot_uid"]
        if metadata.get("ten_bot_token"):
            payload["ten_agent_token"] = metadata["ten_bot_token"]
        if metadata.get("ten_bot_expire_at"):
            payload["ten_agent_token_expire_at"] = metadata["ten_bot_expire_at"]
        return {key: value for key, value in payload.items() if value is not None}

    def _prepare_ten_runtime(self, entity, rtc_override=None) -> dict:
        rtc_block = self._build_rtc_dict(entity, rtc_override=rtc_override)
        if not rtc_block.get("app_id") or not rtc_block.get("channel_name"):
            return {}
        candidate = self._candidate_repository.get(entity.candidate_id)
        job = self._job_repository.get(entity.job_id)
        job_requirements = str(job.requirements or "").strip()
        runtime_payload = dict(entity.payload or {})
        runtime_payload.update(
            self._build_runtime_company_payload(
                job_id=entity.job_id,
                job_requirements=job_requirements,
                payload=runtime_payload,
            )
        )
        runtime_payload.update(
            self._build_runtime_resume_payload(
                candidate_name=str(candidate.name or "").strip(),
                resume_text=str(candidate.resume_text or "").strip(),
                job_requirements=job_requirements,
            )
        )
        runtime_payload.update(
            self._build_runtime_question_pack_payload(
                session_id=entity.id,
                payload=runtime_payload,
            )
        )
        return self._ten_runtime_manager.prepare_session(
            session_id=entity.id,
            candidate_id=entity.candidate_id,
            job_id=entity.job_id,
            language=entity.language,
            rtc={
                **rtc_block,
                "ten_bot_user_id": str((entity.payload or {}).get("ten_agent_user_id") or rtc_block.get("ten_bot_user_id") or ""),
                "ten_bot_token": str((entity.payload or {}).get("ten_agent_token") or rtc_block.get("ten_bot_token") or ""),
            },
            payload=runtime_payload,
        )

    @staticmethod
    def _build_runtime_resume_payload(
        *,
        candidate_name: str,
        resume_text: str,
        job_requirements: str,
    ) -> dict[str, str]:
        compact_resume = " ".join((resume_text or "").split())
        if len(compact_resume) > 1200:
            compact_resume = compact_resume[:1200]
        if not compact_resume:
            compact_resume = "候选人简历信息暂缺。"
        if candidate_name:
            compact_resume = f"{candidate_name}：{compact_resume}"
        return {
            "resume_summary": compact_resume,
            "job_requirements": (job_requirements or "").strip(),
        }

    def _build_runtime_question_pack_payload(
        self,
        *,
        session_id: str,
        payload: dict[str, object] | None = None,
    ) -> dict[str, object]:
        merged_payload = dict(payload or {})
        raw_question_pack = merged_payload.get("question_pack")
        if isinstance(raw_question_pack, dict):
            normalized_pack = normalize_question_pack(raw_question_pack)
            if normalized_pack.get("questions"):
                return {
                    "question_pack": normalized_pack,
                    "question_pack_source": str(
                        merged_payload.get("question_pack_source")
                        or normalized_pack.get("source")
                        or "payload"
                    ).strip(),
                    "question_pack_version": (
                        merged_payload.get("question_pack_version")
                        or normalized_pack.get("version")
                        or ""
                    ),
                }

        cached_pack = self._runtime_store.get_question_pack(session_id=session_id)
        if isinstance(cached_pack, dict) and cached_pack.get("questions"):
            normalized_pack = normalize_question_pack(cached_pack)
            return {
                "question_pack": normalized_pack,
                "question_pack_source": str(
                    merged_payload.get("question_pack_source")
                    or normalized_pack.get("source")
                    or "runtime_store"
                ).strip(),
                "question_pack_version": (
                    merged_payload.get("question_pack_version")
                    or normalized_pack.get("version")
                    or ""
                ),
            }

        existing = self._get_existing_question_set(session_id=session_id)
        if existing and existing.get("questions"):
            normalized_pack = normalize_question_pack(existing)
            return {
                "question_pack": normalized_pack,
                "question_pack_source": str(
                    merged_payload.get("question_pack_source")
                    or normalized_pack.get("source")
                    or "question_set"
                ).strip(),
                "question_pack_version": (
                    merged_payload.get("question_pack_version")
                    or normalized_pack.get("version")
                    or ""
                ),
            }
        return {}

    def _build_runtime_company_payload(
        self,
        *,
        job_id: str,
        job_requirements: str,
        payload: dict[str, object] | None = None,
    ) -> dict[str, str]:
        merged_payload = dict(payload or {})
        explicit_company_info = str(
            merged_payload.get("company_info")
            or merged_payload.get("company_profile")
            or merged_payload.get("company_intro")
            or ""
        ).strip()
        if explicit_company_info:
            return {
                "company_info": explicit_company_info,
                "company_info_source": "payload",
                "company_info_version": "runtime_v1",
            }

        fallback_company_info = self._load_company_info_fallback(
            job_id=job_id,
            job_requirements=job_requirements,
        )
        if fallback_company_info:
            return {
                "company_info": fallback_company_info,
                "company_info_source": "dev_file_fallback",
                "company_info_version": "runtime_v1",
            }
        return {}

    def _load_company_info_fallback(self, *, job_id: str, job_requirements: str) -> str:
        if str(self._settings.environment or "").strip().lower() not in {"dev", "development"}:
            return ""

        candidate_paths = [
            Path(__file__).resolve().parents[2] / "data" / "company_info.txt",
            Path("d:/24985/code/boss-cli-main/AI-HR/data/company_info.txt"),
        ]
        for path in candidate_paths:
            try:
                if path.exists():
                    text = path.read_text(encoding="utf-8").strip()
                    if text:
                        return text
            except Exception:
                logger.warning("ai_interview.company_info_fallback_read_failed path=%s", path)

        if job_requirements.strip():
            return f"岗位相关信息参考：{job_requirements.strip()[:220]}"
        if job_id:
            logger.warning("ai_interview.company_info_missing job_id=%s", job_id)
        return ""

    def _build_rtc_dict(self, entity, rtc_override=None) -> dict:
        base = self._build_rtc_payload(rtc_override) if rtc_override is not None else dict(entity.payload or {})
        return {
            "provider": str(base.get("rtc_vendor") or self._rtc_gateway.provider_name),
            "transport": str(base.get("rtc_transport") or self._settings.rtc_default_transport),
            "room_id": entity.rtc_room_id,
            "channel_name": str(base.get("rtc_channel_name") or entity.rtc_room_id),
            "token": entity.join_token,
            "app_id": base.get("rtc_app_id"),
            "uid": base.get("rtc_uid"),
            "expire_at": self._parse_datetime(base.get("rtc_token_expire_at")),
            "ten_bot_user_id": base.get("ten_agent_user_id"),
            "ten_bot_token": base.get("ten_agent_token"),
        }

    def _build_ten_runtime_response(self, entity) -> dict:
        rtc = self._build_rtc_dict(entity)
        payload = dict(entity.payload or {})
        return {
            "session_id": entity.id,
            "enabled": bool(payload.get("ten_enabled")),
            "room_id": entity.rtc_room_id,
            "provider": rtc["provider"],
            "app_id": rtc.get("app_id"),
            "channel_name": rtc.get("channel_name"),
            "agent_user_id": payload.get("ten_agent_user_id"),
            "remote_user_id": payload.get("ten_remote_user_id") or rtc.get("uid"),
            "property_file": payload.get("ten_property_file"),
            "launch_status": str(payload.get("ten_launch_status") or ("disabled" if not payload.get("ten_enabled") else "prepared")),
            "launch_command": payload.get("ten_launch_command"),
            "process_pid": payload.get("ten_process_pid"),
        }

    def _maybe_auto_launch_ten(self, entity):
        if not self._settings.ai_interview_ten_auto_launch:
            return entity
        property_file = str((entity.payload or {}).get("ten_property_file") or "")
        if not property_file:
            return entity
        current_status = str((entity.payload or {}).get("ten_launch_status") or "")
        if current_status == "launched":
            return entity
        launch_patch = self._ten_runtime_manager.launch_session(session_id=entity.id, property_file=property_file)
        return self._session_repository.update_status(entity.id, status=entity.status, payload_patch=launch_patch)

    @staticmethod
    def _serialize_datetime(value: datetime | str | None) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            return value
        return value.isoformat()

    @staticmethod
    def _parse_datetime(value: str | datetime | None) -> datetime | None:
        if isinstance(value, datetime):
            return value
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value))
        except ValueError:
            return None

    def _to_session_dict(self, entity) -> dict:
        """Cleaned docstring."""
        join_url = f"/interview/{entity.id}?token={entity.join_token}"
        rtc = self._build_rtc_dict(entity)
        ten = self._build_ten_runtime_response(entity)
        return {
            "id": entity.id,
            PayloadKey.CANDIDATE_ID: entity.candidate_id,
            PayloadKey.JOB_ID: entity.job_id,
            "status": entity.status,
            "channel": entity.channel,
            "language": entity.language,
            "rtc_room_id": entity.rtc_room_id,
            "join_token": entity.join_token,
            "join_url": join_url,
            "rtc": rtc,
            "ten": {
                "enabled": ten["enabled"],
                "room_id": ten["room_id"],
                "agent_user_id": ten["agent_user_id"],
                "remote_user_id": ten["remote_user_id"],
                "property_file": ten["property_file"],
                "launch_status": ten["launch_status"],
                "launch_command": ten["launch_command"],
            },
            "started_at": entity.started_at,
            "ended_at": entity.ended_at,
            "payload": entity.payload,
            "note": entity.note,
            "created_at": entity.created_at,
            "updated_at": entity.updated_at,
        }

    def _resolve_runtime_mode(self) -> str:
        """Cleaned docstring."""
        feature_key = "ai_interview_runtime"
        flag = self._runtime_repository.get_feature_flag(feature_key)
        if flag is None:
            return "llm_assist"
        if (flag.fallback_mode or "").strip() == "rule_only":
            return "rule_only"
        if flag.enabled and flag.rollout_percent >= 100:
            return "llm_full"
        return "llm_assist"

