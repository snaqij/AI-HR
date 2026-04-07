"""Structured interview question flow engine."""

from __future__ import annotations

from typing import Any


class InterviewQuestionFlowEngine:
    """Manage active question pointer and stage progression."""

    def init_state(self, *, question_pack: dict[str, Any]) -> dict[str, Any]:
        questions = question_pack.get("questions", []) if isinstance(question_pack, dict) else []
        question_count = len(questions) if isinstance(questions, list) else 0
        return {
            "active_question_index": 0,
            "question_statuses": ["pending"] * question_count,
            "followup_count_current": 0,
            "completed_questions": 0,
            "interview_stage": "S1",  # S1: Greeting, S2: Self-Intro, S3: Project Selection, S4: Deep Dive, S5: Skill Drill, S6: Stress, S7: QA, S8: Closing

            "context_flags": {
                "greeted": False,
                "connectivity_confirmed": False,
                "intro_ready": False,
                "company_info_shared": False,
                "closing_started": False
            }
        }

    def current_question(self, *, state: dict[str, Any], question_pack: dict[str, Any]) -> dict[str, Any] | None:
        questions = question_pack.get("questions", []) if isinstance(question_pack, dict) else []
        if not isinstance(questions, list) or not questions:
            return None
        idx = int(state.get("active_question_index", 0))
        if idx < 0 or idx >= len(questions):
            return None
        question = questions[idx]
        if isinstance(question, dict):
            return {"index": idx, **question}
        return None

    def evaluate_answer(self, *, transcript: str, confidence: float | None, min_len: int = 15) -> dict[str, Any]:
        normalized = " ".join((transcript or "").strip().split())
        need_followup = False
        reason = "sufficient"
        
        # 针对空响应或极短响应（通常是噪音或由于 ASR 误触发）的判断
        if not normalized or len(normalized) < 4:
            need_followup = True
            reason = "too_short_or_noise"
        elif confidence is not None and confidence < 0.50:
            need_followup = True
            reason = "low_confidence"
        elif len(normalized) < int(min_len):
            # 标记为需要追问，除非满足其它满意度条件
            need_followup = True
            reason = "insufficient_detail"
        # 检查是否有单调且无意义的重复
        elif len(set(normalized.split())) <= 2 and len(normalized) > 10:
             need_followup = True
             reason = "repetitive_content"
             
        return {
            "need_followup": need_followup,
            "reason": reason,
            "normalized_len": len(normalized),
            "confidence": confidence,
        }

    def apply_turn_result(self, *, state: dict[str, Any], evaluation: dict[str, Any], current_q_max_followups: int = 2, force_complete: bool = False) -> dict[str, Any]:
        merged = dict(state)
        statuses = list(merged.get("question_statuses", []))
        
        # S1 和 S7/S8 阶段的逻辑由 Orchestrator 结合语义决定切换
        if not statuses:
            merged["interview_stage"] = self.derive_stage(state=merged)
            return merged

        idx = max(0, int(merged.get("active_question_index", 0)))
        
        # 如果已经超过题目索引，说明进入了 P5/P6
        if idx >= len(statuses):
             merged["interview_stage"] = self.derive_stage(state=merged)
             return merged

        current_stage = merged.get("interview_stage", "S1")
        if current_stage in ["S1", "S2", "S3"]:
             return merged

        need_followup = bool(evaluation.get("need_followup"))
        followup_count = max(0, int(merged.get("followup_count_current", 0)))
        
        # 核心逻辑：满足以下任一条件即完成当前题目并推进：
        # 1. 明确被外部强制完成 (force_complete - 用于 LLM 判定回答已经较好)
        # 2. 评估认为不需要追问
        # 3. 已经达到了该题设定的最大追问次数
        if force_complete or not need_followup or followup_count >= current_q_max_followups:
            statuses[idx] = "completed" if (not need_followup or force_complete) else "completed_with_gap"
            merged["active_question_index"] = idx + 1
            merged["followup_count_current"] = 0
        else:
            statuses[idx] = "asked"
            merged["followup_count_current"] = followup_count + 1

        merged["question_statuses"] = statuses
        merged["completed_questions"] = sum(1 for item in statuses if str(item).startswith("completed"))
        merged["interview_stage"] = self.derive_stage(state=merged)
        return merged

    def derive_stage(self, *, state: dict[str, Any]) -> str:
        """根据题目进度和上下文标记派生面试阶段。"""
        active_stage = state.get("interview_stage", "P1")
        
        # 如果已经进入 S7/S8，保持或由 Orchestrator 切换
        if active_stage in ["S7", "S8"]:
            return active_stage

        statuses = list(state.get("question_statuses", []))
        active_idx = int(state.get("active_question_index", 0))
        
        # 初始阶段
        if active_stage == "S1":
             return "S1"
        
        # 题库题目跑完，进入 S7 QA 环节
        if statuses and active_idx >= len(statuses):
            return "S7"

        return active_stage

