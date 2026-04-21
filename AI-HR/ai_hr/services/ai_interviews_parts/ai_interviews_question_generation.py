from __future__ import annotations

from .ai_interviews_shared import *


class AIInterviewQuestionGenerationMixin:
    def generate_question_set(
        self, 
        session_id: str | None = None, 
        invitation_id: str | None = None,
        force_regenerate: bool = False
    ) -> AIInterviewQuestionGenerateResult:
        """生成或获取面试题目集。支持通过 session_id 或 invitation_id。"""
        context_id = session_id or invitation_id
        if not context_id:
            raise ValueError("Either session_id or invitation_id must be provided")

        # 1. 尝试获取现有题目
        if not force_regenerate:
            existing = self._session_repository.get_latest_question_set(
                session_id=session_id, 
                invitation_id=invitation_id
            )
            if existing:
                return AIInterviewQuestionGenerateResult(
                    session_id=context_id,
                    version=existing.version,
                    question_count=len(existing.questions_json),
                    source=existing.source,
                    questions=existing.questions_json or [],
                )

        # 2. 获取业务基础数据
        if session_id:
            session_entity = self._session_repository.get(session_id)
            candidate_id = session_entity.candidate_id
            job_id = session_entity.job_id
            language = session_entity.language
        else:
            invitation_entity = self._invitation_repository.get_by_id(invitation_id)
            candidate_id = invitation_entity.candidate_id
            job_id = invitation_entity.job_id
            language = "zh-CN"

        candidate = self._candidate_repository.get(candidate_id)
        job = self._job_repository.get(job_id)

        # 3. 执行生成
        questions, mode = self._generate_questions_with_fallback(
            session_id=context_id,
            job_title=job.title or "",
            resume_text=candidate.resume_text or "",
            job_requirements=job.requirements or "",
            skills=(candidate.raw_profile or {}).get("skills", []),
            question_count=14,
            language=language
        )

        # 4. 保存
        version = self._session_repository.get_latest_question_set_version(session_id) + 1 if session_id else 1
        entity = self._session_repository.create_question_set(
            session_id=session_id,
            invitation_id=invitation_id,
            version=version,
            source=f"{mode}:invitation" if invitation_id else mode,
            questions=questions
        )

        return AIInterviewQuestionGenerateResult(
            session_id=context_id,
            version=entity.version,
            question_count=len(entity.questions_json),
            source=entity.source,
            questions=entity.questions_json or [],
        )

    def prebuild_question_pack(self, payload: AIInterviewQuestionPackPrebuildRequest) -> dict:
        """预生成题包并缓存到运行时存储。"""
        candidate = self._candidate_repository.get(payload.candidate_id)
        job = self._job_repository.get(payload.job_id)
        resume_text = candidate.resume_text or ""
        job_requirements = job.requirements or ""
        skills = (candidate.raw_profile or {}).get("skills", [])
        
        questions, generation_mode = self._generate_questions_with_fallback(
            session_id=f"prebuild:{payload.candidate_id}:{payload.job_id}",
            job_title=job.title or "",
            resume_text=resume_text,
            job_requirements=job_requirements,
            skills=skills,
            question_count=payload.question_count,
            language=payload.language,
        )
        
        resume_hash = self._compute_prebuild_resume_hash(
            resume_text=resume_text,
            job_requirements=job_requirements,
            skills=skills,
        )
        cache_key = self._build_prebuild_cache_key(
            job_id=payload.job_id,
            candidate_id=payload.candidate_id,
            language=payload.language,
            resume_hash=resume_hash,
        )
        
        question_pack = normalize_question_pack({
            PayloadKey.CANDIDATE_ID: payload.candidate_id,
            PayloadKey.JOB_ID: payload.job_id,
            "language": payload.language,
            "source": payload.source,
            "questions": questions,
            "resume_hash": resume_hash,
        })
        
        ttl_seconds = int(self._settings.ai_interview_prebuild_pack_ttl_seconds)
        self._runtime_store.save_prebuilt_pack(
            key=cache_key,
            question_pack=question_pack,
            ttl_seconds=ttl_seconds,
        )
        
        return {
            "cache_key": cache_key,
            "question_count": len(questions),
            "expires_in_seconds": ttl_seconds,
            "source": payload.source,
            "generation_mode": generation_mode,
        }

    def _generate_questions_with_fallback(
        self,
        *,
        session_id: str,
        job_title: str,
        resume_text: str,
        job_requirements: str,
        skills: list[str],
        question_count: int,
        language: str = "zh-CN",
    ) -> tuple[list[dict], str]:
        """优先使用 LLM 生成题目，仅在 LLM 异常或题目不足时回退到规则驱动。"""
        llm_questions = []
        llm_enabled = self._is_interview_llm_enabled()
        logger.info(
            "ai_interview.question_generation_start session_id=%s llm_enabled=%s question_count=%s language=%s",
            session_id,
            llm_enabled,
            question_count,
            language,
        )

        if llm_enabled:
            try:
                llm_questions = self._build_questions_with_llm(
                    session_id=session_id,
                    job_title=job_title,
                    resume_text=resume_text,
                    job_requirements=job_requirements,
                    skills=skills,
                    question_count=question_count,
                    language=language,
                )
                logger.info(
                    "ai_interview.llm_question_generation_result session_id=%s llm_question_count=%s threshold=%s",
                    session_id,
                    len(llm_questions),
                    max(3, question_count // 2),
                )
                # 如果 LLM 生成了足够的题目，直接使用 LLM 结果
                if len(llm_questions) >= max(3, question_count // 2):
                    return list(llm_questions), "llm"
            except Exception as e:
                logger.error(f"ai_interview.llm_question_generation_failed session_id={session_id} error={e}", exc_info=True)
        else:
            logger.info(
                "ai_interview.llm_question_generation_skipped session_id=%s reason=llm_disabled",
                session_id,
            )

        # 回退逻辑：生成规则题目
        rule_questions = self._build_questions(
            resume_text=resume_text,
            job_requirements=job_requirements,
            skills=skills,
            question_count=question_count,
            language=language,
        )

        # 如果有部分 LLM 题目但不足，尝试混合（增强版）
        if llm_questions:
            try:
                merged = self._merge_question_candidates(
                    rule_questions=rule_questions,
                    llm_questions=llm_questions,
                    question_count=question_count,
                    resume_text=resume_text,
                    job_requirements=job_requirements,
                    skills=skills,
                    language=language,
                )
                return list(merged), "llm_hybrid"
            except Exception as e:
                logger.error(f"ai_interview.question_merge_failed session_id={session_id} error={e}")
                return list(llm_questions) if len(llm_questions) >= 3 else list(rule_questions), "llm_hybrid_fallback"

        # 完全规则回退
        logger.warning(
            "ai_interview.question_generation_fallback_rule session_id=%s llm_enabled=%s llm_question_count=%s",
            session_id,
            llm_enabled,
            len(llm_questions),
        )
        return list(rule_questions), "rule_fallback"

    def _build_questions_with_llm(
        self,
        *,
        session_id: str,
        job_title: str,
        resume_text: str,
        job_requirements: str,
        skills: list[str],
        question_count: int,
        language: str = "zh-CN",
    ) -> list[dict]:
        """使用 LLM (v4) 生成结构化面试题目，采用更稳建的正则解析方式。"""
        route = self._llm_client._router.resolve_route(PromptTaskKey.INTERVIEW_QUESTION_SET)
        logger.info(
            "ai_interview.llm_question_generation_route session_id=%s provider=%s model=%s timeout=%s retries=%s",
            session_id,
            route.provider,
            route.model_name,
            route.timeout_seconds,
            route.max_retries,
        )
        template = self._resolve_prompt_template(
            task_key=PromptTaskKey.INTERVIEW_QUESTION_SET,
            default_version="v4"
        )
        rendered = template.render(
            language=language,
            job_title=job_title,
            job_requirements=job_requirements,
            resume_text=resume_text[:4000],
            skills=skills or [],
            question_count=question_count,
        )

        context = InvokeContext(
            task_key=PromptTaskKey.INTERVIEW_QUESTION_SET,
            trace_id=f"intv-gen-{session_id}-{uuid.uuid4().hex[:6]}",
            prompt=f"{template.system_prompt}\n{rendered}",
            entity_type="session",
            entity_id=session_id,
        )

        # 采用文本模式调用，绕过 Pydantic 契约限制（v4 模板字段多于契约定义）
        response = self._llm_client.invoke(context)
        raw_text = response.content.get("text", "") if response.content else ""
        
        if not raw_text:
            logger.warning(f"ai_interview.llm_questions_empty_response session_id={session_id}")
            return []

        questions = self._parse_questions_from_llm_text(raw_text=raw_text, session_id=session_id)
        if not questions:
            logger.warning(
                "ai_interview.llm_questions_parse_empty session_id=%s raw_preview=%s",
                session_id,
                raw_text[:300].replace("\n", "\\n"),
            )
            return []

        # 标准化题目格式，保留 LLM 生成的额外业务字段
        normalized = []
        for item in questions:
            q = self._normalize_question_item(item)
            if q:
                # 保留 LLM 输出中可能包含的、但标准归一化逻辑未涵盖的字段 (如 module, role_type 等)
                if isinstance(item, dict):
                    q.update({k: v for k, v in item.items() if k not in q})
                normalized.append(q)

        logger.info(
            "ai_interview.llm_questions_generated session_id=%s count=%s first_q=%s",
            session_id,
            len(normalized),
            normalized[0]["question"][:50] if normalized else "None",
        )

        return normalized

    def _parse_questions_from_llm_text(self, *, raw_text: str, session_id: str) -> list[dict]:
        """Parse question candidates from LLM free-form text."""
        text = str(raw_text or "").strip()
        if not text:
            return []

        candidates: list[str] = [text]
        fence_matches = re.findall(r"```(?:json)?\s*([\s\S]*?)```", text, flags=re.IGNORECASE)
        for block in fence_matches:
            block_text = str(block or "").strip()
            if block_text:
                candidates.append(block_text)

        first_obj = text.find("{")
        last_obj = text.rfind("}")
        if first_obj >= 0 and last_obj > first_obj:
            candidates.append(text[first_obj : last_obj + 1])

        first_arr = text.find("[")
        last_arr = text.rfind("]")
        if first_arr >= 0 and last_arr > first_arr:
            candidates.append(text[first_arr : last_arr + 1])

        seen: set[str] = set()
        for candidate in candidates:
            payload = candidate.strip()
            if not payload or payload in seen:
                continue
            seen.add(payload)
            try:
                parsed = json.loads(payload)
            except Exception:
                continue
            if isinstance(parsed, dict):
                questions = parsed.get("questions")
                if not questions:
                    for v in parsed.values():
                        if isinstance(v, list) and v and all(isinstance(item, dict) for item in v):
                            questions = v
                            break
                if isinstance(questions, list):
                    return [item for item in questions if isinstance(item, dict)]
            elif isinstance(parsed, list):
                if parsed and all(isinstance(item, dict) for item in parsed):
                    return [item for item in parsed if isinstance(item, dict)]

        line_questions: list[dict] = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            match = re.match(r"^(?:\d+[\).、]\s*|[-*]\s+)(.+)$", stripped)
            if not match:
                continue
            question_text = match.group(1).strip()
            if len(question_text) < 6:
                continue
            line_questions.append({"question": question_text})
            if len(line_questions) >= 14:
                break

        if line_questions:
            logger.info(
                "ai_interview.llm_questions_parsed_from_lines session_id=%s count=%s",
                session_id,
                len(line_questions),
            )
        else:
            logger.error("ai_interview.llm_questions_parse_failed session_id=%s", session_id)
        return line_questions

    def _is_interview_llm_enabled(self) -> bool:
        """Determine whether the interview LLM flow is enabled."""
        if bool(self._settings.ai_interview_llm_enabled):
            return True
        return self._runtime_repository.is_feature_enabled(
            feature_key="ai_interview_llm",
            default_enabled=self._settings.ai_interview_llm_enabled,
        )

    def _load_or_init_runtime_state(self, *, session_id: str, question_pack: dict) -> dict:
        """Cleaned docstring."""
        current = self._runtime_store.get_session_state(session_id=session_id)
        if current:
            return current
        initial = self._question_flow_engine.init_state(question_pack=question_pack)
        self._runtime_store.init_session_state(
            session_id=session_id,
            state=initial,
            ttl_seconds=int(self._settings.ai_interview_state_ttl_seconds),
        )
        return initial

    def _reset_runtime_state_for_start(self, *, session_id: str, question_pack: dict) -> dict:
        """Force a clean runtime state for every newly started interview session."""

        initial = self._question_flow_engine.init_state(question_pack=question_pack)
        self._runtime_store.init_session_state(
            session_id=session_id,
            state=initial,
            ttl_seconds=int(self._settings.ai_interview_state_ttl_seconds),
        )
        return initial

    def _refresh_runtime_question_pack_for_start(self, *, session_id: str) -> dict | None:
        """Hydrate the latest session-scoped question pack into runtime store before start."""

        latest = self._session_repository.get_latest_question_set(session_id)
        if latest is not None:
            questions = [item for item in (latest.questions_json or []) if isinstance(item, dict)]
            question_pack = {
                "session_id": session_id,
                "version": int(latest.version),
                "source": str(latest.source or "session_latest"),
                "question_count": len(questions),
                "questions": questions,
            }
            self._runtime_store.save_question_pack(
                session_id=session_id,
                version=int(latest.version),
                question_pack=question_pack,
                ttl_seconds=int(self._settings.ai_interview_question_pack_ttl_seconds),
            )
            logger.info(
                "ai_interview.question_pack_refreshed_for_start session_id=%s version=%s source=%s question_count=%s question_ids=%s",
                session_id,
                question_pack.get("version"),
                question_pack.get("source"),
                question_pack.get("question_count"),
                self._summarize_question_ids(question_pack),
            )
            return question_pack
        logger.warning("ai_interview.question_pack_missing_for_start session_id=%s", session_id)
        return self._runtime_store.get_question_pack(session_id=session_id)

    def _ensure_runtime_question_pack_for_start(self, *, session_id: str) -> dict | None:
        """Ensure every started session has a session-scoped question pack."""

        question_pack = self._refresh_runtime_question_pack_for_start(session_id=session_id)
        if question_pack and question_pack.get("questions"):
            return question_pack

        session_entity = self._session_repository.get(session_id)
        candidate = self._candidate_repository.get(session_entity.candidate_id)
        job = self._job_repository.get(session_entity.job_id)
        question_count = max(1, int((session_entity.payload or {}).get("question_count") or 14))
        questions, generation_mode = self._generate_questions_with_fallback(
            session_id=session_id,
            job_title=job.title or "",
            resume_text=candidate.resume_text or "",
            job_requirements=job.requirements or "",
            skills=(candidate.raw_profile or {}).get("skills", []),
            question_count=question_count,
            language=session_entity.language,
        )
        if not questions:
            logger.warning("ai_interview.question_pack_auto_generate_empty session_id=%s", session_id)
            return None

        version = self._session_repository.get_latest_question_set_version(session_id) + 1
        source = generation_mode
        self._session_repository.create_question_set(
            session_id=session_id,
            version=version,
            source=source,
            questions=questions,
        )
        question_pack = normalize_question_pack(
            {
                "session_id": session_id,
                "version": version,
                "source": source,
                "language": session_entity.language,
                "questions": questions,
            }
        )
        self._runtime_store.save_question_pack(
            session_id=session_id,
            version=version,
            question_pack=question_pack,
            ttl_seconds=int(self._settings.ai_interview_question_pack_ttl_seconds),
        )
        logger.info(
            "ai_interview.question_pack_auto_generated_for_start session_id=%s version=%s source=%s generation_mode=%s question_count=%s question_ids=%s",
            session_id,
            version,
            source,
            generation_mode,
            question_pack.get("question_count"),
            self._summarize_question_ids(question_pack),
        )
        return question_pack

    def _log_runtime_start_snapshot(self, *, session_id: str, question_pack: dict) -> None:
        """Emit a startup snapshot for runtime pack/state verification."""

        state = self._runtime_store.get_session_state(session_id=session_id) or {}
        logger.info(
            "ai_interview.start_runtime_ready session_id=%s question_pack_version=%s question_pack_source=%s "
            "question_count=%s state_stage=%s active_question_index=%s current_question_id=%s question_ids=%s",
            session_id,
            question_pack.get("version"),
            question_pack.get("source"),
            question_pack.get("question_count"),
            state.get("interview_stage"),
            state.get("active_question_index"),
            state.get("current_question_id"),
            self._summarize_question_ids(question_pack),
        )

    @staticmethod
    def _summarize_question_ids(question_pack: dict[str, object] | None) -> str:
        questions = question_pack.get("questions", []) if isinstance(question_pack, dict) else []
        question_ids: list[str] = []
        if isinstance(questions, list):
            for item in questions[:16]:
                if not isinstance(item, dict):
                    continue
                identifier = str(item.get("idx") or item.get("question_id") or item.get("id") or "").strip()
                if identifier:
                    question_ids.append(identifier)
        return ",".join(question_ids)

    def _get_active_question_context(self, *, session_id: str) -> dict | None:
        """Cleaned docstring."""
        question_pack = self._runtime_store.get_question_pack(session_id=session_id)
        if not question_pack:
            return None
        state = self._runtime_store.get_session_state(session_id=session_id)
        if not state:
            state = self._load_or_init_runtime_state(session_id=session_id, question_pack=question_pack)
        return self._question_flow_engine.current_question(state=state, question_pack=question_pack)

    def _advance_stage_by_question_flow(self, *, session_id: str, state: dict) -> str:
        """Cleaned docstring."""
        question_pack = self._runtime_store.get_question_pack(session_id=session_id) or {}
        stage = self._question_flow_engine.derive_stage(state=state, question_pack=question_pack)
        current = self._session_repository.get(session_id)
        self._session_repository.update_status(
            session_id,
            status=current.status,
            payload_patch={PayloadKey.INTERVIEW_STAGE: stage},
        )
        self._runtime_store.patch_session_state(
            session_id=session_id,
            patch={PayloadKey.INTERVIEW_STAGE: stage},
            ttl_seconds=int(self._settings.ai_interview_state_ttl_seconds),
        )
        return stage

    def _update_question_flow_after_turn(
        self,
        *,
        session_id: str,
        transcript: str,
        confidence: float | None,
        question_pack: dict,
    ) -> dict:
        """Cleaned docstring."""
        state = self._load_or_init_runtime_state(session_id=session_id, question_pack=question_pack)
        decision = self._runtime_engine.process_candidate_turn(
            state=state,
            question_pack=question_pack,
            transcript=transcript,
            confidence=confidence,
        )
        evaluation = decision.evaluation
        updated = dict(decision.updated_state)
        updated_stage = self._question_flow_engine.derive_stage(state=updated, question_pack=question_pack)
        updated[PayloadKey.INTERVIEW_STAGE] = updated_stage
        questions = question_pack.get("questions", []) if isinstance(question_pack, dict) else []
        total_questions = len(questions) if isinstance(questions, list) else int(question_pack.get("question_count") or 0)
        completed_questions = max(0, int(updated.get("completed_questions", 0)))
        completion_rate = (
            round(min(1.0, completed_questions / total_questions), 4)
            if total_questions > 0
            else 0.0
        )
        self._runtime_store.patch_session_state(
            session_id=session_id,
            patch=updated,
            ttl_seconds=int(self._settings.ai_interview_state_ttl_seconds),
        )
        current = self._session_repository.get(session_id)
        self._session_repository.update_status(
            session_id,
            status=current.status,
            payload_patch={
                PayloadKey.INTERVIEW_STAGE: updated_stage,
                "question_count": total_questions,
                "question_completion_rate": completion_rate,
                "question_flow": {
                    "completed_questions": completed_questions,
                    "total_questions": total_questions,
                    "active_question_index": int(updated.get("active_question_index", 0)),
                    "followup_count_current": int(updated.get("followup_count_current", 0)),
                },
            },
        )
        return {
            "need_followup": bool(evaluation.get("need_followup")),
            "reason": str(evaluation.get("reason") or ""),
            PayloadKey.INTERVIEW_STAGE: updated_stage,
            "question_completion_rate": completion_rate,
        }

    def _attach_prebuilt_question_pack(self, *, session_id: str) -> dict[str, object]:
        """Cleaned docstring."""
        try:
            session_entity = self._session_repository.get(session_id)
            candidate = self._candidate_repository.get(session_entity.candidate_id)
            job = self._job_repository.get(session_entity.job_id)
            resume_hash = self._compute_prebuild_resume_hash(
                resume_text=candidate.resume_text or "",
                job_requirements=job.requirements or "",
                skills=(candidate.raw_profile or {}).get("skills", []),
            )
            cache_key = self._build_prebuild_cache_key(
                job_id=session_entity.job_id,
                candidate_id=session_entity.candidate_id,
                language=session_entity.language,
                resume_hash=resume_hash,
            )
            prebuilt_pack = self._runtime_store.get_prebuilt_pack(key=cache_key)
            if not prebuilt_pack:
                return {"prebuilt_pack_hit": False}
            questions = prebuilt_pack.get("questions", [])
            if not isinstance(questions, list) or not questions:
                return {"prebuilt_pack_hit": False}
            latest_version = self._session_repository.get_latest_question_set_version(session_id)
            version = latest_version + 1
            source = str(prebuilt_pack.get("source") or "prebuilt")
            self._session_repository.create_question_set(
                session_id=session_id,
                version=version,
                source=source,
                questions=questions,
            )
            hydrated_pack = {
                "session_id": session_id,
                "version": version,
                "source": source,
                "language": session_entity.language,
                "question_count": len(questions),
                "questions": questions,
                "cache_key": cache_key,
            }
            self._runtime_store.save_question_pack(
                session_id=session_id,
                version=version,
                question_pack=hydrated_pack,
                ttl_seconds=int(self._settings.ai_interview_question_pack_ttl_seconds),
            )
            return {
                "prebuilt_pack_hit": True,
                "prebuilt_cache_key": cache_key,
                "question_pack_version": version,
                "question_pack_source": source,
            }
        except Exception:
            return {"prebuilt_pack_hit": False}

    def _build_prebuild_cache_key(self, *, job_id: str, candidate_id: str, language: str, resume_hash: str) -> str:
        """Cleaned docstring."""
        normalized_lang = (language or "zh-CN").strip()
        normalized_hash = (resume_hash or "").strip()[:16]
        return f"{job_id}:{candidate_id}:{normalized_lang}:{normalized_hash}"

    @staticmethod
    def _compute_prebuild_resume_hash(*, resume_text: str, job_requirements: str, skills: list[str]) -> str:
        """Cleaned docstring."""
        material = {
            "resume_text": (resume_text or "")[:4000],
            "job_requirements": (job_requirements or "")[:1200],
            "skills": [str(item).strip() for item in skills if str(item).strip()],
        }
        encoded = json.dumps(material, ensure_ascii=False, sort_keys=True).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _get_existing_question_set(self, *, session_id: str) -> dict | None:
        """Return the latest generated question set when regeneration is not required."""
        cached = self._runtime_store.get_question_pack(session_id=session_id)
        if cached and isinstance(cached.get("questions"), list) and cached.get("version") is not None:
            questions = [item for item in cached.get("questions", []) if isinstance(item, dict)]
            return {
                "session_id": session_id,
                "version": int(cached.get("version")),
                "question_count": len(questions),
                "source": str(cached.get("source") or "runtime_cache"),
                "questions": questions,
            }
        latest = self._session_repository.get_latest_question_set(session_id)
        if latest is None:
            return None
        questions = [item for item in (latest.questions_json or []) if isinstance(item, dict)]
        question_pack = {
            "session_id": session_id,
            "version": int(latest.version),
            "source": latest.source,
            "question_count": len(questions),
            "questions": questions,
        }
        self._runtime_store.save_question_pack(
            session_id=session_id,
            version=int(latest.version),
            question_pack=question_pack,
            ttl_seconds=int(self._settings.ai_interview_question_pack_ttl_seconds),
        )
        return {
            "session_id": session_id,
            "version": int(latest.version),
            "question_count": len(questions),
            "source": latest.source,
            "questions": questions,
        }

