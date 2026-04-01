"""Streaming utilities for orchestrator."""

from __future__ import annotations
from typing import Iterable

def split_sentences(text_stream: Iterable[str]) -> Iterable[str]:
    """抽取流式文本中的完整句子，并针对首包延迟进行优化。"""
    buffer = ""
    is_first_sentence = True
    # Core sentence delimiters.
    main_delimiters = (".", "!", "?", "。", "！", "？", "\n", ";", "；")
    # Allow the first sentence to break earlier for lower TTS latency.
    extra_delimiters = (",", "，", ":", "：")
    
    for chunk in text_stream:
        if not chunk:
            continue
        buffer += chunk
        
        while True:
            # 首句允许在逗号处切分，以大幅降低首包延迟 (TTFB)
            current_delimiters = main_delimiters
            if is_first_sentence:
                current_delimiters = main_delimiters + extra_delimiters
            
            # 找到最靠前的分割点
            first_idx = -1
            for d in current_delimiters:
                pos = buffer.find(d)
                if pos != -1:
                    if first_idx == -1 or pos < first_idx:
                        first_idx = pos
            
            if first_idx != -1:
                # 提取句子，包括结束符
                sentence = buffer[:first_idx + 1].strip()
                buffer = buffer[first_idx + 1:]
                if sentence:
                    yield sentence
                    is_first_sentence = False # 只要出过一句，之后恢复正常断句逻辑
            else:
                # Lower thresholds so the first audible chunk arrives faster.
                threshold = 8 if is_first_sentence else 24
                if len(buffer) > threshold:
                    yield buffer.strip()
                    buffer = ""
                    is_first_sentence = False
                break
                
    if buffer.strip():
        yield buffer.strip()
