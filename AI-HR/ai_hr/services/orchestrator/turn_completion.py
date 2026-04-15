"""Turn completion judgement for realtime interview conversations."""

from __future__ import annotations

from dataclasses import dataclass

from ai_hr.services.interview_runtime.realtime_policy import StageRealtimePolicy


@dataclass(frozen=True, slots=True)
class FinalizeDecision:
    """Structured turn-completion decision."""

    should_finalize: bool
    confidence: float
    reason: str
    need_more_wait_ms: int
    semantic_completion_score: float


class TurnCompletionJudge:
    """Blend timing and semantic signals to decide whether a turn is complete."""

    _STRONG_ENDINGS = (
        "\u5dee\u4e0d\u591a\u5c31\u662f\u8fd9\u4e9b",
        "\u5927\u6982\u5c31\u662f\u8fd9\u6837",
        "\u57fa\u672c\u5c31\u8fd9\u4e9b",
        "\u6211\u8fd9\u8fb9\u8bf4\u5b8c\u4e86",
        "\u4e3b\u8981\u5c31\u662f\u8fd9\u51e0\u5757",
        "\u6574\u4f53\u4e0a\u5c31\u662f\u8fd9\u4e2a\u601d\u8def",
    )
    _WEAK_ENDINGS = (
        "\u5c31\u8fd9\u6837",
        "\u5c31\u8fd9\u4e2a",
        "\u5c31\u662f\u8fd9\u6837",
        "\u5927\u6982\u662f\u8fd9\u6837",
        "\u57fa\u672c\u4e0a\u662f\u8fd9\u6837",
    )
    _STRONG_CONTINUATIONS = (
        "然后",
        "还有",
        "另外",
        "其次",
        "后面的话",
        "我再补充一下",
        "我想一下",
        "还有一个点",
        "比如说",
        "像刚才那个",
    )
    _WEAK_CONTINUATIONS = (
        "嗯",
        "啊",
        "就是",
        "这个",
        "那个",
    )
    # Thinking-pause phrases: candidate is mid-thought, NOT done speaking.
    # These must strongly suppress finalization to avoid cutting off technical answers.
    _THINKING_PAUSE_STRONG = (
        "让我想想",
        "让我想一下",
        "我想想",
        "我想一想",
        "我想一下",
        "稍等一下",
        "稍等",
        "等一下",
        "怎么说呢",
        "怎么讲呢",
        "嗯这个",
        "嗯那个",
        "就是说",
        "我回忆一下",
        "让我回想一下",
        "我看看",
    )
    _THINKING_PAUSE_WEAK = (
        "嗯嗯",
        "啊这个",
        "然后这个",
        "就是那个",
        "应该是",
    )

    def judge(
        self,
        *,
        transcript: str,
        stage: str,
        policy: StageRealtimePolicy,
        speaking_elapsed_ms: int,
        silence_ms: int,
        resumed_recently: bool,
    ) -> FinalizeDecision:
        text = " ".join((transcript or "").strip().split())
        semantic_score = self._semantic_completion_score(text)

        pause_confidence = 0.0
        if silence_ms >= policy.hard_done_ms:
            pause_confidence = 1.0
        elif silence_ms >= policy.likely_done_ms:
            pause_confidence = 0.72
        elif silence_ms >= policy.soft_pause_ms:
            pause_confidence = 0.42

        hold_satisfied = speaking_elapsed_ms >= policy.min_speaking_hold_ms
        early_close = semantic_score >= 0.92

        if resumed_recently:
            return FinalizeDecision(
                should_finalize=False,
                confidence=0.05,
                reason="recent_resume_guard",
                need_more_wait_ms=max(200, policy.resume_grace_ms),
                semantic_completion_score=semantic_score,
            )

        if silence_ms < policy.soft_pause_ms:
            return FinalizeDecision(
                should_finalize=False,
                confidence=0.05,
                reason="below_soft_pause",
                need_more_wait_ms=max(120, policy.soft_pause_ms - silence_ms),
                semantic_completion_score=semantic_score,
            )

        if silence_ms >= policy.max_force_finalize_ms:
            confidence = min(0.98, 0.70 + semantic_score * 0.15)
            return FinalizeDecision(
                should_finalize=True,
                confidence=confidence,
                reason="max_silence_force_finalize",
                need_more_wait_ms=0,
                semantic_completion_score=semantic_score,
            )

        if not hold_satisfied and not early_close:
            return FinalizeDecision(
                should_finalize=False,
                confidence=min(0.35, pause_confidence),
                reason="below_min_hold_and_semantically_open",
                need_more_wait_ms=max(200, min(1000, policy.hard_done_ms - silence_ms)),
                semantic_completion_score=semantic_score,
            )

        if silence_ms >= policy.hard_done_ms and (hold_satisfied or early_close):
            confidence = min(0.99, 0.55 + pause_confidence * 0.25 + semantic_score * 0.20)
            return FinalizeDecision(
                should_finalize=True,
                confidence=confidence,
                reason="hard_pause_with_completion_signal",
                need_more_wait_ms=0,
                semantic_completion_score=semantic_score,
            )

        if silence_ms >= policy.likely_done_ms and early_close:
            confidence = min(0.95, 0.45 + pause_confidence * 0.20 + semantic_score * 0.30)
            return FinalizeDecision(
                should_finalize=True,
                confidence=confidence,
                reason="semantic_early_finish",
                need_more_wait_ms=0,
                semantic_completion_score=semantic_score,
            )

        return FinalizeDecision(
            should_finalize=False,
            confidence=min(0.65, 0.20 + pause_confidence * 0.25 + semantic_score * 0.20),
            reason="need_more_wait_for_completion",
            need_more_wait_ms=max(180, min(1200, policy.hard_done_ms - silence_ms)),
            semantic_completion_score=semantic_score,
        )

    def _semantic_completion_score(self, text: str) -> float:
        if not text:
            return 0.0

        score = 0.25 if text.endswith(("。", "！", "？", ".", "!", "?")) else 0.10

        if any(phrase in text for phrase in self._STRONG_ENDINGS):
            score += 0.55
        elif any(phrase in text for phrase in self._WEAK_ENDINGS):
            score += 0.22

        if any(phrase in text for phrase in self._STRONG_CONTINUATIONS):
            score -= 0.45
        elif any(phrase in text for phrase in self._WEAK_CONTINUATIONS):
            score -= 0.18

        # Suppress finalization when candidate shows clear thinking / hesitation signals.
        # These commonly appear mid-answer during technical questions and must not trigger
        # early completion even if the sentence superficially sounds finished.
        if any(phrase in text for phrase in self._THINKING_PAUSE_STRONG):
            score -= 0.55
        elif any(phrase in text for phrase in self._THINKING_PAUSE_WEAK):
            score -= 0.25

        if text.endswith(("然后", "还有", "另外")):
            score -= 0.25

        # Length bonuses: reward substantive answers so they reach completion naturally.
        # This also prevents very short answers from accidentally scoring high.
        n = len(text)
        if n >= 200:
            score += 0.18
        elif n >= 100:
            score += 0.12
        elif n >= 40:
            score += 0.08

        return max(0.0, min(1.0, score))
