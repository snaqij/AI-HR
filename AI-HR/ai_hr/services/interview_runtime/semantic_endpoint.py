"""Semantic Endpoint Engine to determine visual completeness of speech bursts."""

from __future__ import annotations
import re

# Conjunctions or transition words that heavily imply an unfinished sentence.
HANGING_TAILS = (
    "然后", "而且", "不过", "但是", "因为", "所以", "并且",
    "至于", "其实", "一方面", "另外", "另一方面", "可能",
    "主要是", "像是", "大概是", "那个", "这个", "具体的", "比如说", "就是说"
)

# Particles or functional words that imply the sentence is grammatically suspended.
UNCLOSED_PARTICLES = (
    "的话", "的", "地", "得", "对于", "关于", "把", "被", "基于", "交给", "提到", "说起"
)

# Filler words or hesitation sounds.
THINKING_FILLERS = (
    "那个", "呃", "嗯", "就是", "我觉得", "可能因为", "我想想", 
    "让我想一下", "稍等", "这个", "啊", "哦", "对", "让我想想看",
    "我整理一下思路", "呢", "吧", "那个啥", "呃那"
)

def _clean_text(text: str) -> str:
    """Remove punctuation often automatically added by ASR ending."""
    cleaned = str(text or "").strip()
    return re.sub(r'[，。！？、,.\!?\;\؛\s]+$', '', cleaned)

def is_thinking_filler(text: str) -> bool:
    """Return True if the text is entirely or overwhelmingly a filler sound/phrase."""
    cleaned = _clean_text(text)
    if not cleaned:
        return True
    
    if cleaned in THINKING_FILLERS:
        return True
    
    # Check if ends with a filler (very high probability of more coming)
    for filler in THINKING_FILLERS:
        if len(filler) >= 2 and cleaned.endswith(filler):
            return True
        
    if len(cleaned) <= 6:
        for filler in THINKING_FILLERS:
            # For short phrases like "呃那个", if any known filler spans most of the string
            if filler in cleaned:
                return True
                
    return False

def is_syntactically_complete(text: str) -> bool:
    """Return False if text likely ends mid-sentence based on structural heuristics."""
    cleaned = _clean_text(text)
    if not cleaned:
        return False
        
    for tail in HANGING_TAILS:
        if cleaned.endswith(tail):
            return False
            
    for particle in UNCLOSED_PARTICLES:
        if cleaned.endswith(particle):
            return False
            
    return True

def evaluate_semantic_floor(text: str, stage: str = "S3") -> str:
    """Evaluate a transcript burst and determine the floor control action.
    
    Returns:
        "YIELD": LLM should immediately take over.
        "HOLD": Do not trigger LLM. System stays quiet.
        "DEBOUNCE_LONG": Borderline completeness. May require delayed fallback.
    """
    cleaned = _clean_text(text)
    
    if not cleaned:
        return "HOLD"
        
    if is_thinking_filler(cleaned):
        return "HOLD"
        
    if not is_syntactically_complete(cleaned):
        return "HOLD"
        
    # In technical stages, relatively short strings (even if grammatically okay)
    # warrant waiting to avoid interrupting complex multi-part thoughts.
    # S2 (Self-intro) is now treated with the same caution as S3/S4/S5.
    if len(cleaned) < 18 and stage in ("S2", "S3", "S4", "S5"):
        return "DEBOUNCE_LONG"
        
    return "YIELD"
