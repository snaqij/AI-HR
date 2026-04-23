from __future__ import annotations

import random

from .ai_interviews_shared import *


class AIInterviewQuestionBankMixin:
    _OPENING_GREETING_TEMPLATES_ZH = (
        "你好，先确认下音频是否清晰。如果能听到，请先做一个1到2分钟的自我介绍，重点讲最近经历和你的核心职责。",
        "你好，欢迎参加面试。先确认一下你这边声音正常吗？没问题的话，请做一个1到2分钟的自我介绍。",
        "你好，我们先做个声音确认。听得到的话，请你先用1到2分钟介绍一下自己，聚焦最近项目和角色定位。",
        "你好，很高兴和你交流。先确认音频可以吗？可以的话先来一个1到2分钟的自我介绍，重点说近期经验。",
        "你好，面试开始前先确认一下通话质量。若声音正常，请先做1到2分钟自我介绍，讲清你最近负责的方向。",
    )
    _OPENING_GREETING_TEMPLATES_EN = (
        "Hi, before we start, can you hear me clearly? If yes, please give a 1-2 minute self-introduction focused on your recent experience and role.",
        "Hello, quick audio check first. If the sound is clear, please start with a 1-2 minute self-introduction about your recent projects and ownership.",
        "Hi, nice to meet you. Can you hear me well? If yes, please do a 1-2 minute self-introduction, focusing on what you recently worked on.",
        "Hello, let's do a quick sound check. If everything is good, please give a 1-2 minute self-introduction with your current direction and main responsibilities.",
    )

    @classmethod
    def _build_opening_greeting_question(cls, *, language: str) -> str:
        if language == "en-US":
            return random.choice(cls._OPENING_GREETING_TEMPLATES_EN)
        return random.choice(cls._OPENING_GREETING_TEMPLATES_ZH)

    @staticmethod
    def _shorten_question_text(question: str) -> str:
        """Lightly normalize question text without aggressive truncation."""

        text = re.sub(r"\s+", " ", str(question or "")).strip()
        return text

    @staticmethod
    def _normalize_stage_code(raw_stage: str, dimension: str = "") -> str:
        stage = str(raw_stage or "").strip().upper()
        if stage in {
            InterviewStage.SELF_INTRO,
            InterviewStage.TECH_STACK,
            InterviewStage.PROJECT_DEEP_DIVE,
            InterviewStage.JD_MATCH,
            InterviewStage.GENERAL_PROBE,
            InterviewStage.COMPANY_QA,
        }:
            return stage

        hint = f"{raw_stage} {dimension}".lower()
        if any(
            token in hint
            for token in ("自我介绍", "候选人画像", "经历概述", "intro", "self_intro", "introduction")
        ):
            return InterviewStage.SELF_INTRO
        if any(
            token in hint
            for token in ("项目深挖", "项目经验", "ownership", "模块", "挑战", "project", "tradeoff")
        ):
            return InterviewStage.PROJECT_DEEP_DIVE
        if any(token in hint for token in ("实习", "职责", "协作", "intern", "experience_validation")):
            return InterviewStage.JD_MATCH
        if any(
            token in hint
            for token in ("系统设计", "排查", "性能", "故障", "system", "troubleshooting", "capability_probe")
        ):
            return InterviewStage.GENERAL_PROBE
        if any(token in hint for token in ("反问", "团队", "公司介绍", "qa", "company_qa")):
            return InterviewStage.COMPANY_QA
        return InterviewStage.TECH_STACK

    @staticmethod
    def _repair_question_text(question: str, *, dimension: str, language: str = "zh-CN") -> str:
        text = str(question or "").strip()
        if not text or language == "en-US":
            return text

        interrogatives = (
            "怎么",
            "为什么",
            "如何",
            "哪些",
            "哪块",
            "哪个",
            "有没有",
            "举例",
            "结合",
            "什么",
        )
        if text.endswith(("？", "?")) and not any(token in text for token in interrogatives):
            stem = text.rstrip("？").rstrip("。")
            if stem.startswith(("你提到", "你说", "你简历里写了", "你简历里提到", "你对", "你熟悉", "你做过", "岗位要求")):
                return f"{stem}，能具体说说吗？"
        if len(text) < 14 and text.endswith(("？", "?")):
            stem = text.rstrip("？").rstrip("。")
            return f"{stem}，具体是怎么做的？"
        return text

    @staticmethod
    def _normalize_question_item(item: dict | object) -> dict | None:
        normalized = normalize_question_item(item)
        if normalized is None:
            return None
        question = AIInterviewQuestionBankMixin._shorten_question_text(str(normalized.get("question") or "").strip())
        question = AIInterviewQuestionBankMixin._repair_question_text(
            question,
            dimension=str(normalized.get("dimension") or "communication"),
            language="zh-CN",
        )
        if not question:
            return None
        normalized["question"] = question
        return normalized

    @staticmethod
    def _extract_keyword_tokens(*, skills: list[str], job_requirements: str, resume_text: str, language: str) -> set[str]:
        tokens = {str(item).strip().lower() for item in (skills or []) if str(item).strip()}
        text = f"{(job_requirements or '')[:500]} {(resume_text or '')[:500]}".lower()
        if language == "en-US":
            for token in re.findall(r"[a-z][a-z0-9_+\-.]{2,}", text):
                tokens.add(token)
        else:
            for term in ("性能", "并发", "架构", "稳定性", "排查", "数据库", "系统", "线上", "故障", "可用性", "扩展性"):
                if term in text:
                    tokens.add(term)
        return {token for token in tokens if token}

    def _score_question_item(self, *, question: dict, source: str, keyword_tokens: set[str], language: str) -> int:
        text = f"{question.get('question', '')} {question.get('expected_signal', '')} {question.get('followup_condition', '')}".lower()
        base = 70 if source == "llm" else 48
        if source == "seed":
            base += 15  # Seed questions have higher priority.
        if question.get("expected_signal"):
            base += 8
        if question.get("followup_condition"):
            base += 6
        hit_count = sum(1 for token in keyword_tokens if token and token in text)
        base += min(20, hit_count * 4)

        dimension = str(question.get("dimension") or "").strip().lower()
        if dimension in {"project_experience", "problem_solving", "ownership", "job_fit", "communication", "system_design"}:
            base += 6
        question_len = len(str(question.get("question") or ""))
        if 18 <= question_len <= 120:
            base += 4
        if language == "en-US":
            if any(term in text for term in ("latency", "throughput", "tradeoff", "incident", "scalability", "observability")):
                base += 8
        else:
            if any(term in text for term in ("\u6027\u80fd", "\u5e76\u53d1", "\u67b6\u6784", "\u6392\u67e5", "\u6307\u6807", "\u5bb9\u91cf", "\u7a33\u5b9a\u6027", "\u6545\u969c", "\u6743\u8861")):
                base += 8
        return base

    @staticmethod
    def _stage_quota_plan(question_count: int) -> dict[str, int]:
        total = max(1, int(question_count or 0))
        if total >= 14:
            return {
                InterviewStage.SELF_INTRO: 1,
                InterviewStage.TECH_STACK: 8,
                InterviewStage.PROJECT_DEEP_DIVE: 2,
                InterviewStage.JD_MATCH: 1,
                InterviewStage.GENERAL_PROBE: 1,
                InterviewStage.COMPANY_QA: 1,
            }
        if total >= 12:
            return {
                InterviewStage.SELF_INTRO: 1,
                InterviewStage.TECH_STACK: 7,
                InterviewStage.PROJECT_DEEP_DIVE: 1,
                InterviewStage.JD_MATCH: 1,
                InterviewStage.GENERAL_PROBE: 1,
                InterviewStage.COMPANY_QA: 1,
            }
        if total >= 10:
            return {
                InterviewStage.SELF_INTRO: 1,
                InterviewStage.TECH_STACK: 6,
                InterviewStage.PROJECT_DEEP_DIVE: 1,
                InterviewStage.JD_MATCH: 1,
                InterviewStage.GENERAL_PROBE: 1,
            }
        return {
            InterviewStage.SELF_INTRO: 1,
            InterviewStage.TECH_STACK: max(1, total - 3),
            InterviewStage.PROJECT_DEEP_DIVE: 1,
            InterviewStage.GENERAL_PROBE: 1,
        }

    @staticmethod
    def _question_bucket(question: dict) -> str:
        bucket = str(question.get("bucket") or "").strip().lower()
        if bucket in {"profile", "stack", "scenario", "experience", "wrap_up"}:
            return bucket
        stage = str(question.get("stage") or InterviewStage.TECH_STACK).strip()
        dimension = str(question.get("dimension") or "").strip().lower()
        if stage == InterviewStage.SELF_INTRO:
            return "profile"
        if stage in {InterviewStage.COMPANY_QA, InterviewStage.CLOSING}:
            return "wrap_up"
        if stage == InterviewStage.PROJECT_DEEP_DIVE or dimension in {
            "performance_troubleshooting",
            "system_design",
            "scenario_design",
        }:
            return "scenario"
        if stage == InterviewStage.JD_MATCH or dimension in {
            "focus_experience",
            "experience_validation",
            "jd_match",
            "jd_match_case",
            "jd_readiness",
            "jd_gap_analysis",
            "project_deep_dive",
            "project_tradeoff",
            "internship_experience",
            "project_experience",
        }:
            return "experience"
        return "stack"

    @staticmethod
    def _technical_bucket_plan(question_count: int) -> dict[str, dict[str, int]]:
        total = max(1, int(question_count or 0))
        if total >= 12:
            scenario_target = 3
            stack_target = min(8, max(5, total - scenario_target - 5))
            experience_target = max(3, total - scenario_target - stack_target)
            return {
                "stack": {"min": 5, "target": stack_target, "max": 8},
                "scenario": {"min": 3, "target": scenario_target, "max": 3},
                "experience": {"min": 3, "target": min(5, experience_target), "max": 5},
            }
        if total >= 9:
            scenario_target = 3
            stack_target = max(4, total - scenario_target - 3)
            experience_target = max(2, total - scenario_target - stack_target)
            return {
                "stack": {"min": 4, "target": min(6, stack_target), "max": 7},
                "scenario": {"min": 3, "target": 3, "max": 3},
                "experience": {"min": 2, "target": min(4, experience_target), "max": 4},
            }
        scenario_target = min(2, max(1, total // 3))
        stack_target = max(1, total - scenario_target - 1)
        experience_target = max(1, total - scenario_target - stack_target)
        return {
            "stack": {"min": 1, "target": stack_target, "max": max(1, total - scenario_target)},
            "scenario": {"min": scenario_target, "target": scenario_target, "max": scenario_target},
            "experience": {"min": 1, "target": experience_target, "max": max(1, total - stack_target - scenario_target)},
        }

    def _build_stage_seed_questions(
        self,
        *,
        job_requirements: str,
        skills: list[str],
        language: str,
    ) -> list[dict]:
        primary_skill = next((str(item).strip() for item in (skills or []) if str(item).strip()), "核心技能")
        job_hint = (job_requirements or "").strip()[:80] or "岗位要求"
        if language == "en-US":
            primary_skill = primary_skill or "core skill"
            job_hint = (job_requirements or "").strip()[:80] or "job requirements"
            return [
                {"stage": InterviewStage.SELF_INTRO, "question": "Please give me a short self-introduction, focusing on your recent project and role.", "dimension": "self_intro", "expected_signal": "Recent experience, role, and main project", "followup_condition": "Follow up if the introduction is scattered", "max_followups": 1, "success_signals": ["recent experience", "role", "main project"]},
                {"stage": InterviewStage.PROJECT_DEEP_DIVE, "question": f"In the project where you used {primary_skill} most deeply, what was the hardest part you handled yourself?", "dimension": "project_deep_dive", "expected_signal": "Personal ownership, technical challenge, handling approach", "followup_condition": "Follow up if ownership is unclear", "max_followups": 2, "success_signals": ["personal ownership", "technical challenge", "handling approach"]},
                {"stage": InterviewStage.PROJECT_DEEP_DIVE, "question": "Which design choice in that project needed the most trade-off, and why?", "dimension": "project_tradeoff", "expected_signal": "Trade-off thinking, constraints, design rationale", "followup_condition": "Follow up if trade-offs are missing", "max_followups": 2, "success_signals": ["trade-off", "constraints", "design rationale"]},
                {"stage": InterviewStage.JD_MATCH, "question": "Looking at your collaboration or internship-like experience, what did you really own end to end?", "dimension": "experience_validation", "expected_signal": "Actual ownership, delivery depth, collaboration boundary", "followup_condition": "Follow up if the answer stays at team level", "max_followups": 2, "success_signals": ["actual ownership", "delivery depth", "collaboration boundary"]},
                {"stage": InterviewStage.GENERAL_PROBE, "question": "If one of your services suddenly slows down online, what troubleshooting order would you follow?", "dimension": "capability_probe", "expected_signal": "Troubleshooting path, metrics awareness, diagnosis order", "followup_condition": "Follow up if there are no concrete steps", "max_followups": 2, "success_signals": ["troubleshooting path", "metrics awareness", "diagnosis order"]},
                {"stage": InterviewStage.COMPANY_QA, "question": "After the technical part, what would you most want to know about this role or team?", "dimension": "company_qa", "expected_signal": "Candidate concern, role understanding focus", "followup_condition": "No follow-up unless unclear", "max_followups": 1, "success_signals": ["candidate concern", "role understanding focus"]},
            ]
        return [
            {"stage": InterviewStage.SELF_INTRO, "question": "先简单介绍一下你自己，重点说最近的项目和你的角色。", "dimension": "self_intro", "expected_signal": "最近经历、项目方向、角色定位", "followup_condition": "如果介绍发散，追问最近项目和核心职责", "max_followups": 1, "success_signals": ["最近经历", "项目方向", "角色定位"]},
            {"stage": InterviewStage.PROJECT_DEEP_DIVE, "question": f"你用 {primary_skill} 最深的那个项目里，最难的点是什么？你当时是怎么处理的？", "dimension": "project_deep_dive", "expected_signal": "个人职责、技术难点、处理方式", "followup_condition": "如果没有讲清本人做了什么，继续追问", "max_followups": 2, "success_signals": ["个人职责", "技术难点", "处理方式"]},
            {"stage": InterviewStage.PROJECT_DEEP_DIVE, "question": "那个项目里有没有哪个方案你们反复权衡过？最后为什么这么定？", "dimension": "project_tradeoff", "expected_signal": "取舍思路、约束条件、方案原因", "followup_condition": "如果没有说清取舍和约束，继续追问", "max_followups": 2, "success_signals": ["取舍思路", "约束条件", "方案原因"]},
            {"stage": InterviewStage.JD_MATCH, "question": "如果看实习或协作经历，你真正独立负责到交付的是哪一块？", "dimension": "experience_validation", "expected_signal": "真实负责范围、交付深度、协作边界", "followup_condition": "如果回答还停留在团队层面，继续追问", "max_followups": 2, "success_signals": ["真实负责范围", "交付深度", "协作边界"]},
            {"stage": InterviewStage.GENERAL_PROBE, "question": "如果你负责的服务线上突然变慢了，你一般按什么顺序排查？", "dimension": "capability_probe", "expected_signal": "排查路径、指标意识、定位顺序", "followup_condition": "如果没有具体排查步骤，继续追问", "max_followups": 2, "success_signals": ["排查路径", "指标意识", "定位顺序"]},
            {"stage": InterviewStage.COMPANY_QA, "question": f"技术部分聊完后，结合这个岗位“{job_hint}”，你最想了解我们哪一块？", "dimension": "company_qa", "expected_signal": "候选人关注点、岗位理解方向", "followup_condition": "除非候选人的问题不清楚，否则不继续追问", "max_followups": 1, "success_signals": ["候选人关注点", "岗位理解方向"]},
        ]

    def _merge_question_candidates(
        self,
        *,
        rule_questions: list[dict],
        llm_questions: list[dict],
        question_count: int,
        resume_text: str,
        job_requirements: str,
        skills: list[str],
        language: str,
    ) -> list[dict]:
        """Blend rule + LLM questions with hard stage quotas."""
        keyword_tokens = self._extract_keyword_tokens(
            skills=skills,
            job_requirements=job_requirements,
            resume_text=resume_text,
            language=language,
        )
        candidates: list[dict] = []
        stage_seeds = self._build_stage_seed_questions(
            job_requirements=job_requirements,
            skills=skills,
            language=language,
        )
        # Randomize opening greeting template each generation to avoid repetitive first-turn wording.
        opening_seed = self._build_opening_greeting_question(language=language)
        for seed_item in stage_seeds:
            if str(seed_item.get("stage") or "").strip() == InterviewStage.SELF_INTRO:
                seed_item["question"] = opening_seed
                break

        for source, questions in (("rule", rule_questions), ("llm", llm_questions), ("seed", stage_seeds)):
            for raw in questions:
                normalized = self._normalize_question_item(raw)
                if normalized is None:
                    continue
                normalized_text = re.sub(r"\s+", " ", normalized["question"]).strip().lower()
                if not normalized_text:
                    continue
                candidates.append(
                    {
                        "source": source,
                        "normalized_text": normalized_text,
                        "score": self._score_question_item(
                            question=normalized,
                            source=source,
                            keyword_tokens=keyword_tokens,
                            language=language,
                        ),
                        "question": normalized,
                    }
                )
        if not candidates:
            return list(rule_questions)[:question_count]

        dedup: dict[str, dict] = {}
        for item in sorted(candidates, key=lambda entry: entry["score"], reverse=True):
            key = item["normalized_text"]
            if key not in dedup:
                dedup[key] = item
        ranked = list(dedup.values())
        ranked.sort(
            key=lambda entry: (
                entry["score"],
                1 if entry["source"] == "llm" else 0,
                1 if entry["source"] == "seed" else 0,
            ),
            reverse=True,
        )

        bucket_plan = self._technical_bucket_plan(question_count)
        bucket_order = ("stack", "scenario", "experience")
        picked: list[dict] = []
        seen_questions: set[str] = set()
        seen_dimensions_by_bucket: dict[str, set[str]] = {}
        seen_skills_by_bucket: dict[str, set[str]] = {}
        bucket_counts = {bucket: 0 for bucket in bucket_order}

        def _bucket_items(bucket_name: str, *, seeds_only: bool | None = None) -> list[dict]:
            filtered: list[dict] = []
            for item in ranked:
                if self._question_bucket(item["question"]) != bucket_name:
                    continue
                if seeds_only is True and item["source"] != "seed":
                    continue
                if seeds_only is False and item["source"] == "seed":
                    continue
                filtered.append(item)
            return filtered

        def _try_pick(item: dict, bucket_name: str, *, enforce_diversity: bool) -> bool:
            question = item["question"]
            normalized_text = item["normalized_text"]
            if normalized_text in seen_questions:
                return False
            dimension = str(question.get("dimension") or "communication").strip().lower()
            target_skill = str(question.get("target_skill") or "").strip().lower()
            bucket_dims = seen_dimensions_by_bucket.setdefault(bucket_name, set())
            bucket_skills = seen_skills_by_bucket.setdefault(bucket_name, set())
            if enforce_diversity:
                if dimension and dimension in bucket_dims and item["source"] != "seed":
                    return False
                if target_skill and target_skill in bucket_skills and item["source"] != "seed":
                    return False
            picked.append(question)
            seen_questions.add(normalized_text)
            if dimension:
                bucket_dims.add(dimension)
            if target_skill:
                bucket_skills.add(target_skill)
            bucket_counts[bucket_name] = bucket_counts.get(bucket_name, 0) + 1
            return True

        for bucket_name in bucket_order:
            minimum = int(bucket_plan.get(bucket_name, {}).get("min", 0))
            for strict_mode in (True, False):
                if bucket_counts[bucket_name] >= minimum:
                    break
                for item in _bucket_items(bucket_name, seeds_only=False):
                    if _try_pick(item, bucket_name, enforce_diversity=strict_mode):
                        if bucket_counts[bucket_name] >= minimum or len(picked) >= question_count:
                            break
                if len(picked) >= question_count:
                    return picked[:question_count]
            if bucket_counts[bucket_name] >= minimum:
                continue
            for item in _bucket_items(bucket_name, seeds_only=True):
                if _try_pick(item, bucket_name, enforce_diversity=False):
                    if bucket_counts[bucket_name] >= minimum or len(picked) >= question_count:
                        break
            if len(picked) >= question_count:
                return picked[:question_count]

        for bucket_name in bucket_order:
            target = int(bucket_plan.get(bucket_name, {}).get("target", bucket_counts.get(bucket_name, 0)))
            maximum = int(bucket_plan.get(bucket_name, {}).get("max", target))
            limit = min(maximum, max(target, bucket_counts.get(bucket_name, 0)))
            for strict_mode in (True, False):
                if bucket_counts[bucket_name] >= limit:
                    break
                for item in _bucket_items(bucket_name, seeds_only=None):
                    if _try_pick(item, bucket_name, enforce_diversity=strict_mode):
                        if bucket_counts[bucket_name] >= limit or len(picked) >= question_count:
                            break
                if len(picked) >= question_count:
                    return picked[:question_count]

        ordered: list[dict] = []
        for bucket_name in bucket_order:
            for question in picked:
                if self._question_bucket(question) == bucket_name:
                    ordered.append(question)

        if len(ordered) >= question_count:
            return ordered[:question_count]

        for item in ranked:
            if len(ordered) >= question_count:
                break
            normalized_text = item["normalized_text"]
            if normalized_text in seen_questions:
                continue
            question = item["question"]
            bucket_name = self._question_bucket(question)
            maximum = int(bucket_plan.get(bucket_name, {}).get("max", question_count))
            if bucket_counts.get(bucket_name, 0) >= maximum and bucket_name in bucket_plan:
                continue
            if _try_pick(item, bucket_name, enforce_diversity=False):
                ordered.append(question)

        if len(ordered) >= question_count:
            return ordered[:question_count]

        for item in ranked:
            if len(ordered) >= question_count:
                break
            normalized_text = item["normalized_text"]
            if normalized_text in seen_questions:
                continue
            question = item["question"]
            if _try_pick(item, self._question_bucket(question), enforce_diversity=False):
                ordered.append(question)
        return ordered[:question_count]

    def _build_questions(
        self,
        *,
        resume_text: str,
        job_requirements: str,
        skills: list[str],
        question_count: int,
        language: str,
    ) -> list[dict]:
        """Build a stable fallback question pack."""

        normalized_skills = [str(item).strip() for item in (skills or []) if str(item).strip()]
        if not normalized_skills:
            normalized_skills = ["Java", "Spring Boot", "MySQL", "Redis"]

        middleware_keywords = ("mysql", "postgres", "redis", "kafka", "rocketmq", "rabbitmq", "es", "elasticsearch", "mongodb", "clickhouse")
        core_skills = normalized_skills[:2]
        while len(core_skills) < 2:
            core_skills.append("核心技术栈" if language != "en-US" else "core stack")

        middleware_skills = [
            skill for skill in normalized_skills
            if any(keyword in skill.lower() for keyword in middleware_keywords) and skill not in core_skills
        ][:2]
        for candidate in ["MySQL", "Redis"]:
            if len(middleware_skills) >= 2:
                break
            if candidate not in middleware_skills and candidate not in core_skills:
                middleware_skills.append(candidate)

        supplemental_skills = [
            skill for skill in normalized_skills
            if skill not in core_skills and skill not in middleware_skills
        ][:4]

        def _signals(*items: str) -> list[str]:
            return [item for item in items if item]

        def _q(*, question: str, dimension: str, expected_signal: str, followup_condition: str, stage: str = InterviewStage.TECH_STACK, bucket: str = "", max_followups: int = 2, success_signals: list[str] | None = None, target_skill: str = "", source_evidence: str = "") -> dict:
            return {
                "question": question,
                "dimension": dimension,
                "expected_signal": expected_signal,
                "followup_condition": followup_condition,
                "stage": stage,
                "bucket": bucket,
                "max_followups": max_followups,
                "success_signals": success_signals or [],
                "target_skill": target_skill,
                "source_evidence": source_evidence,
            }

        question_bank: list[dict] = []

        for skill in core_skills[:2]:
            if language == "en-US":
                question_bank.append(_q(question=f"You highlighted {skill} in your resume. In which project did you use it most deeply, and what exactly were you responsible for?", dimension="core_stack_validation", expected_signal="Project context, ownership, and depth of usage", followup_condition="Follow up if ownership or usage depth is unclear", bucket="stack", success_signals=_signals("project context", "ownership", "depth of usage"), target_skill=skill, source_evidence=f"resume_skill:{skill}"))
            else:
                question_bank.append(_q(question=f"你简历里重点写了 {skill}，它在哪个项目里用得最深？你当时具体负责了什么？", dimension="core_stack_validation", expected_signal="项目场景、个人职责、使用深度", followup_condition="如果没有讲清个人职责或真实使用深度，继续追问", bucket="stack", success_signals=_signals("项目场景", "个人职责", "使用深度"), target_skill=skill, source_evidence=f"resume_skill:{skill}"))

        for skill in middleware_skills[:2]:
            if language == "en-US":
                question_bank.append(_q(question=f"In your project, where did {skill} sit in the architecture, and why did you choose it there?", dimension="middleware_usage", expected_signal="Architecture position, selection reason, and practical usage", followup_condition="Follow up if the reason for using this component is vague", bucket="stack", success_signals=_signals("architecture position", "selection reason", "practical usage"), target_skill=skill, source_evidence=f"resume_skill:{skill}"))
            else:
                question_bank.append(_q(question=f"在你的真实项目里，{skill} 主要放在系统的哪个位置？你们为什么要在那一层用它？", dimension="middleware_usage", expected_signal="架构位置、选型原因、实际使用方式", followup_condition="如果没有说明为什么要用它，继续追问", bucket="stack", success_signals=_signals("架构位置", "选型原因", "实际使用方式"), target_skill=skill, source_evidence=f"resume_skill:{skill}"))

        for skill in supplemental_skills:
            if language == "en-US":
                question_bank.append(_q(question=f"For {skill}, what concrete problem did it help you solve in a real project, and how did you verify the effect afterward?", dimension="stack_verification", expected_signal="Real usage context, solved problem, and verification", followup_condition="Follow up if the answer lacks project evidence", bucket="stack", success_signals=_signals("real usage context", "solved problem", "verification"), target_skill=skill, source_evidence=f"resume_skill:{skill}"))
            else:
                question_bank.append(_q(question=f"回到你简历里的 {skill}，它在真实项目里主要帮你解决了什么问题？你后面是怎么验证效果的？", dimension="stack_verification", expected_signal="真实使用场景、解决的问题、验证方式", followup_condition="如果没有结合项目证据，继续追问", bucket="stack", success_signals=_signals("真实使用场景", "解决的问题", "验证方式"), target_skill=skill, source_evidence=f"resume_skill:{skill}"))

        if language == "en-US":
            question_bank.extend([
                _q(question="If the system latency suddenly rises after a release, what signals would you look at first, and how would you narrow it down?", dimension="performance_troubleshooting", expected_signal="Monitoring signals, diagnosis order, troubleshooting path", followup_condition="Follow up if there are no concrete troubleshooting steps", stage=InterviewStage.PROJECT_DEEP_DIVE, bucket="scenario", success_signals=_signals("monitoring signals", "diagnosis order", "troubleshooting path")),
                _q(question="Pick one design choice in your recent project that affected performance or stability. Why did you settle on that option?", dimension="system_design", expected_signal="Trade-off, constraints, design rationale", followup_condition="Follow up if the trade-off is unclear", stage=InterviewStage.PROJECT_DEEP_DIVE, bucket="scenario", success_signals=_signals("trade-off", "constraints", "design rationale")),
                _q(question="Suppose a core interface suddenly faces traffic several times higher than usual. How would you protect availability and avoid cascading failures?", dimension="scenario_design", expected_signal="Capacity protection, degradation strategy, stability thinking", followup_condition="Follow up if there are no concrete fallback measures", stage=InterviewStage.PROJECT_DEEP_DIVE, bucket="scenario", success_signals=_signals("capacity protection", "degradation strategy", "stability thinking")),
            ])
        else:
            question_bank.extend([
                _q(question="如果一次发布之后系统延迟突然升高了，你会先看哪些信号？再怎么一步步缩小排查范围？", dimension="performance_troubleshooting", expected_signal="监控信号、定位顺序、排查路径", followup_condition="如果没有具体排查步骤，继续追问", stage=InterviewStage.PROJECT_DEEP_DIVE, bucket="scenario", success_signals=_signals("监控信号", "定位顺序", "排查路径")),
                _q(question="结合你最近的项目，挑一个明显影响性能或稳定性的设计选择，说说你们为什么最后这么定。", dimension="system_design", expected_signal="取舍思路、系统约束、设计依据", followup_condition="如果没有说明取舍和约束，继续追问", stage=InterviewStage.PROJECT_DEEP_DIVE, bucket="scenario", success_signals=_signals("取舍思路", "系统约束", "设计依据")),
                _q(question="假设你负责的核心接口流量突然涨到平时的好几倍，你会怎么做才能先保住可用性，避免整个系统被拖垮？", dimension="scenario_design", expected_signal="容量保护、降级策略、稳定性思路", followup_condition="如果没有具体保护动作或兜底方案，继续追问", stage=InterviewStage.PROJECT_DEEP_DIVE, bucket="scenario", success_signals=_signals("容量保护", "降级策略", "稳定性思路")),
            ])

        job_hint = job_requirements[:120] if job_requirements else ("role requirements" if language == "en-US" else "岗位要求")
        if language == "en-US":
            question_bank.extend([
                _q(question=f"From the requirement '{job_hint}', which part matches your past experience most directly? Walk me through a concrete case.", dimension="jd_match_case", expected_signal="JD mapping, concrete case, evidence", followup_condition="Follow up if the answer is broad but not evidence-based", stage=InterviewStage.JD_MATCH, bucket="experience", success_signals=_signals("JD mapping", "concrete case", "evidence"), source_evidence=f"jd:{job_hint}"),
                _q(question="Which requirement in this role would you be most ready to pick up immediately, and what experience gives you that confidence?", dimension="jd_readiness", expected_signal="Readiness judgment, delivery experience", followup_condition="Follow up if confidence is not backed by actual work", stage=InterviewStage.JD_MATCH, bucket="experience", success_signals=_signals("readiness judgment", "delivery experience"), source_evidence=f"jd:{job_hint}"),
                _q(question="Which requirement in this JD is less familiar to you, and how would you close that gap after joining?", dimension="jd_gap_analysis", expected_signal="Gap awareness, learning plan, realistic assessment", followup_condition="Follow up if there is no concrete plan", stage=InterviewStage.JD_MATCH, bucket="experience", success_signals=_signals("gap awareness", "learning plan", "realistic assessment"), source_evidence=f"jd:{job_hint}"),
                _q(question="Looking back at your internship or project work, which part best reflects your real ownership from design to delivery?", dimension="experience_validation", expected_signal="Ownership boundary, delivery depth, concrete responsibility", followup_condition="Follow up if the answer stays at team level", stage=InterviewStage.JD_MATCH, bucket="experience", success_signals=_signals("ownership boundary", "delivery depth", "concrete responsibility")),
            ])
        else:
            question_bank.extend([
                _q(question=f"结合这个岗位要求“{job_hint}”，你过去哪段经历和它最直接匹配？请讲一个具体例子。", dimension="jd_match_case", expected_signal="JD 对应关系、具体案例、真实证据", followup_condition="如果只有泛泛匹配没有案例，继续追问", stage=InterviewStage.JD_MATCH, bucket="experience", success_signals=_signals("JD 对应关系", "具体案例", "真实证据"), source_evidence=f"jd:{job_hint}"),
                _q(question="这个岗位里你觉得自己上手最快、最有把握的是哪一块？你的信心来自哪段真实经历？", dimension="jd_readiness", expected_signal="就绪度判断、交付经历", followup_condition="如果信心没有建立在真实经历上，继续追问", stage=InterviewStage.JD_MATCH, bucket="experience", success_signals=_signals("就绪度判断", "交付经历"), source_evidence=f"jd:{job_hint}"),
                _q(question="如果看这份 JD，有哪一块是你相对不熟的？如果入职后要补上，你会怎么补？", dimension="jd_gap_analysis", expected_signal="差距认知、补足计划、现实评估", followup_condition="如果没有具体补足计划，继续追问", stage=InterviewStage.JD_MATCH, bucket="experience", success_signals=_signals("差距认知", "补足计划", "现实评估"), source_evidence=f"jd:{job_hint}"),
                _q(question="回头看你的实习或项目经历，哪一部分最能体现你是从设计到交付真正负责过的？", dimension="experience_validation", expected_signal="职责边界、交付深度、真实负责内容", followup_condition="如果回答还停留在团队层面，继续追问", stage=InterviewStage.JD_MATCH, bucket="experience", success_signals=_signals("职责边界", "交付深度", "真实负责内容")),
            ])

        return question_bank[:question_count]

