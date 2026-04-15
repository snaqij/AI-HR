"""TEN runtime preparation and launch helpers."""

from __future__ import annotations

import json
import logging
import os
import shlex
import subprocess
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..core.config import PROJECT_ROOT, Settings
from ..core.exceptions import InvalidConnectorConfigError

logger = logging.getLogger(__name__)


class TENRuntimeManager:
    """Owns session-scoped TEN property generation and optional process launch."""

    def __init__(self, settings: Settings):
        self._settings = settings

    def prepare_session(
        self,
        *,
        session_id: str,
        candidate_id: str,
        job_id: str,
        language: str,
        rtc: dict[str, Any],
        payload: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if not self._settings.ai_interview_ten_enabled:
            return {
                "ten_enabled": False,
                "ten_launch_status": "disabled",
            }

        property_file = self._session_dir() / f"{session_id}.property.json"
        local_property_file = self._to_local_path(str(property_file))
        local_property_file.parent.mkdir(parents=True, exist_ok=True)
        template = self._load_template()
        runtime = self._build_runtime_graph(
            template=template,
            session_id=session_id,
            candidate_id=candidate_id,
            job_id=job_id,
            language=language,
            rtc=rtc,
            payload=payload or {},
        )
        local_property_file.write_text(json.dumps(runtime, ensure_ascii=False, indent=2), encoding="utf-8")

        patch = {
            "ten_enabled": True,
            "ten_property_file": str(property_file),
            "ten_agent_dir": str(self._agent_dir()),
            "ten_agent_user_id": rtc.get("ten_bot_user_id") or "",
            "ten_remote_user_id": rtc.get("uid") or "",
            "ten_launch_command": self._launch_command(str(property_file)),
            "ten_launch_status": "prepared",
            "ten_last_prepared_at": datetime.now(tz=UTC).isoformat(),
        }
        return patch

    def launch_session(self, *, session_id: str, property_file: str) -> dict[str, Any]:
        if not self._settings.ai_interview_ten_enabled:
            return {"ten_enabled": False, "ten_launch_status": "disabled"}

        agent_dir = self._agent_dir()
        local_property_path = self._to_local_path(property_file)
        if not local_property_path.exists():
            raise InvalidConnectorConfigError(f"TEN property file does not exist: {property_file} (Local: {local_property_path})")

        # Generate the manual command for the user to copy-paste into WSL
        tman_cmd = self._settings.ai_interview_ten_tman_cmd
        wsl_property_file = self._to_wsl_path(str(property_file))
        launch_cmd = f"cd {agent_dir} && {tman_cmd} run start -- --property '{wsl_property_file}'"
        
        banner = "=" * 80
        msg = f"\n{banner}\n!!! [MANUAL MODE] COPY AND RUN THIS IN YOUR WSL TERMINAL !!!\n\n{launch_cmd}\n{banner}\n"
        print(msg, flush=True)
        logger.info("Manual launch command generated for session %s", session_id)

        return {
            "ten_enabled": True,
            "ten_launch_status": "manual_ready",
            "ten_launch_command": launch_cmd,
            "ten_last_launched_at": datetime.now(tz=UTC).isoformat(),
        }

    def _build_runtime_graph(
        self,
        *,
        template: dict[str, Any],
        session_id: str,
        candidate_id: str,
        job_id: str,
        language: str,
        rtc: dict[str, Any],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        runtime = deepcopy(template)
        graph = runtime.setdefault("ten", {}).setdefault("predefined_graphs", [])[0]["graph"]
        self._normalize_graph_connections(graph)
        for node in graph.get("nodes", []):
            name = str(node.get("name") or "")
            prop = node.setdefault("property", {})
            if name == "agora_rtc":
                metadata = rtc.get("metadata") or {}
                bot_id_val = rtc.get("ten_bot_user_id") or metadata.get("ten_bot_uid") or 0
                remote_id_val = rtc.get("uid") or 0
                token = rtc.get("ten_bot_token") or metadata.get("ten_bot_token") or ""
                
                # Use str() for user_id/remote_user_id to satisfy manifest typing (string)
                # Use int() for uid/remote_uid to satisfy internal extension logic (integer)
                prop.update(
                    {
                        "app_id": rtc.get("app_id") or self._settings.agora_app_id or "",
                        "app_certificate": self._settings.agora_app_certificate or "",
                        "channel": rtc.get("channel_name") or rtc.get("room_id") or "",
                        "token": token,
                        "stream_id": int(bot_id_val),
                        "remote_stream_id": int(remote_id_val),
                        "user_id": str(bot_id_val),
                        "remote_user_id": str(remote_id_val),
                        "enable_string_uid": False,
                        "subscribe_audio": True,
                        "publish_audio": True,
                        "publish_data": False,
                        "auto_join": True,
                    }
                )
                print(f"[TEN-DEBUG] Generated agora_rtc props: {prop}", flush=True)
            elif name == "ten_vad":
                prop.setdefault("dump", False)
                prop.update({"silence_duration_ms": 500})
            elif name == "asr_aliyun_nls":
                prop.update(
                    {
                        "appkey": self._settings.asr_aliyun_appkey or "",
                        "access_key_id": self._settings.aliyun_access_key_id or "",
                        "access_key_secret": self._settings.aliyun_access_key_secret or "",
                    }
                )
            elif name == "tts_tencent":
                prop.update(
                    {
                        "secret_id": self._settings.tencent_secret_id or self._settings.tts_api_key or "",
                        "secret_key": self._settings.tencent_secret_key or "",
                        "region": self._settings.tencent_region,
                        "app_id": self._settings.tts_tencent_app_id or "",
                    }
                )
            elif name == "interview_orchestrator":
                question_pack = payload.get("question_pack")
                prop.update(
                    {
                        "session_id": session_id,
                        "candidate_id": candidate_id,
                        "job_id": job_id,
                        "language": language,
                        "task_key": "interview_followup",
                        "max_followup": int(payload.get("ten_max_followup") or 2),
                        "resume_summary": str(payload.get("resume_summary") or "").strip(),
                        "job_requirements": str(payload.get("job_requirements") or "").strip(),
                        "company_info": str(
                            payload.get("company_info")
                            or payload.get("company_profile")
                            or payload.get("company_intro")
                            or ""
                        ).strip(),
                        "company_info_source": str(payload.get("company_info_source") or "").strip(),
                        "company_info_version": str(payload.get("company_info_version") or "").strip(),
                        "question_pack": question_pack if isinstance(question_pack, dict) else {},
                        "question_pack_source": str(payload.get("question_pack_source") or "").strip(),
                        "question_pack_version": str(payload.get("question_pack_version") or "").strip(),
                    }
                )
                pack_questions = question_pack.get("questions", []) if isinstance(question_pack, dict) else []
                pack_ids: list[str] = []
                if isinstance(pack_questions, list):
                    for item in pack_questions[:16]:
                        if not isinstance(item, dict):
                            continue
                        identifier = str(item.get("idx") or item.get("question_id") or item.get("id") or "").strip()
                        if identifier:
                            pack_ids.append(identifier)
                logger.info(
                    "ten_runtime.interview_orchestrator_payload_ready session_id=%s question_pack_source=%s question_pack_version=%s question_count=%s question_ids=%s company_info_source=%s resume_chars=%s jd_chars=%s",
                    session_id,
                    str(payload.get("question_pack_source") or "").strip(),
                    str(payload.get("question_pack_version") or "").strip(),
                    len(pack_questions) if isinstance(pack_questions, list) else 0,
                    ",".join(pack_ids),
                    str(payload.get("company_info_source") or "").strip(),
                    len(str(payload.get("resume_summary") or "").strip()),
                    len(str(payload.get("job_requirements") or "").strip()),
                )
        return runtime

    def _normalize_graph_connections(self, graph: dict[str, Any]) -> None:
        connections = graph.setdefault("connections", [])

        def _find_extension_connection(extension: str) -> dict[str, Any] | None:
            for item in connections:
                if str(item.get("extension") or "") == extension:
                    return item
            return None

        def _ensure_cmd_dest(
            extension: str,
            cmd_name: str,
            dest_extension: str,
        ) -> None:
            connection = _find_extension_connection(extension)
            if connection is None:
                connection = {"extension": extension, "cmd": []}
                connections.append(connection)
            cmd_list = connection.setdefault("cmd", [])
            target_cmd = None
            for cmd in cmd_list:
                if str(cmd.get("name") or "") == cmd_name:
                    target_cmd = cmd
                    break
            if target_cmd is None:
                target_cmd = {"name": cmd_name, "dest": []}
                cmd_list.append(target_cmd)
            dests = target_cmd.setdefault("dest", [])
            if not any(str(dest.get("extension") or "") == dest_extension for dest in dests):
                dests.append({"extension": dest_extension})

        _ensure_cmd_dest("ten_vad", "start_of_sentence", "tts_tencent")
        _ensure_cmd_dest("ten_vad", "start_of_sentence", "interview_orchestrator")
        _ensure_cmd_dest("ten_vad", "start_of_sentence", "asr_aliyun_nls")
        _ensure_cmd_dest("ten_vad", "end_of_sentence", "asr_aliyun_nls")
        _ensure_cmd_dest("ten_vad", "end_of_sentence", "interview_orchestrator")
        _ensure_cmd_dest("interview_orchestrator", "interrupt", "tts_tencent")
        _ensure_cmd_dest("agora_rtc", "on_connected", "interview_orchestrator")
        _ensure_cmd_dest("agora_rtc", "on_connection_error", "interview_orchestrator")
        _ensure_cmd_dest("agora_rtc", "on_connection_failure", "interview_orchestrator")
        _ensure_cmd_dest("agora_rtc", "on_token_expired", "interview_orchestrator")

    def _load_template(self) -> dict[str, Any]:
        template_val = self._settings.ai_interview_ten_property_template
        if not template_val:
            template_path = self._to_local_path(str(self._agent_dir() / "property.json"))
        else:
            template_path = self._to_local_path(template_val)

        if not template_path.exists():
            raise InvalidConnectorConfigError(f"TEN property template not found: {template_path}")
        return json.loads(template_path.read_text(encoding="utf-8"))

    def _to_local_path(self, path_str: str) -> Path:
        """Translate WSL path to local Windows path if running on Windows."""
        if os.name == "nt" and path_str.startswith("/mnt/"):
            # /mnt/d/path -> D:\path
            drive = path_str[5].upper()
            return Path(f"{drive}:") / path_str[7:].replace("/", "\\")
        return Path(path_str)

    def _to_wsl_path(self, path_str: str) -> str:
        """Translate Windows path to WSL path if running on Windows."""
        if os.name == "nt":
            path_obj = Path(path_str).resolve()
            if path_obj.drive:
                # D:\path -> /mnt/d/path
                drive = path_obj.drive.replace(":", "").lower()
                posix_path = path_obj.as_posix()
                return f"/mnt/{drive}{posix_path[len(path_obj.drive):]}"
        return path_str

    def _agent_dir(self) -> Path:
        if self._settings.ai_interview_ten_agent_dir:
            return Path(self._settings.ai_interview_ten_agent_dir).expanduser().resolve()
        return (PROJECT_ROOT / "ten_agent").resolve()


    def _load_template(self) -> dict[str, Any]:
        template_val = self._settings.ai_interview_ten_property_template
        if not template_val:
            template_path = self._to_local_path(str(self._agent_dir() / "property.json"))
        else:
            template_path = self._to_local_path(template_val)

        if not template_path.exists():
            raise InvalidConnectorConfigError(f"TEN property template not found: {template_path}")
        return json.loads(template_path.read_text(encoding="utf-8"))

    def _to_local_path(self, path_str: str) -> Path:
        """Translate WSL path to local Windows path if running on Windows."""
        if os.name == "nt" and path_str.startswith("/mnt/"):
            # /mnt/d/path -> D:\path
            drive = path_str[5].upper()
            return Path(f"{drive}:") / path_str[7:].replace("/", "\\")
        return Path(path_str)

    def _to_wsl_path(self, path_str: str) -> str:
        """Translate Windows path to WSL path if running on Windows."""
        if os.name == "nt":
            path_obj = Path(path_str).resolve()
            if path_obj.drive:
                # D:\path -> /mnt/d/path
                drive = path_obj.drive.replace(":", "").lower()
                posix_path = path_obj.as_posix()
                return f"/mnt/{drive}{posix_path[len(path_obj.drive):]}"
        return path_str

    def _agent_dir(self) -> Path:
        if self._settings.ai_interview_ten_agent_dir:
            return Path(self._settings.ai_interview_ten_agent_dir).expanduser().resolve()
        return (PROJECT_ROOT / "ten_agent").resolve()

    def _session_dir(self) -> Path:
        if self._settings.ai_interview_ten_session_dir:
            return Path(self._settings.ai_interview_ten_session_dir).expanduser().resolve()
        return self._agent_dir() / ".ten_sessions"

    def _launch_command(self, property_file: str) -> str:
        wsl_path = self._to_wsl_path(property_file)
        return f"{self._settings.ai_interview_ten_tman_cmd} run start -- --property {shlex.quote(wsl_path)}"
