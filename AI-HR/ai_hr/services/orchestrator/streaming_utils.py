"""Streaming utilities for orchestrator."""

from __future__ import annotations
from typing import Iterable

def split_sentences(text_stream: Iterable[str]) -> Iterable[str]:
    """抽取流式文本中的完整句子。"""
    buffer = ""
    # 常用中英文句子结束符
    delimiters = (".", "!", "?", "。", "！", "？", "\n", ";", "；")
    
    for chunk in text_stream:
        if not chunk:
            continue
        buffer += chunk
        
        while True:
            # 找到最靠前的分割点
            first_idx = -1
            for d in delimiters:
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
            else:
                # 如果缓冲区太长（比如 LLM 一直不给标点），也强制切分一次
                if len(buffer) > 100:
                    yield buffer.strip()
                    buffer = ""
                break
                
    if buffer.strip():
        yield buffer.strip()
