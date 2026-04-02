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
                # 为了首句秒回，增加“语气词特快通道”
                acknowledgments = ["明白了", "好的", "理解了", "原来如此", "收到", "没问题", "确实"]
                
                # 如果缓冲区开头是这些语气词，且后面有停顿趋势，优先切出
                for ack in acknowledgments:
                    if buffer.startswith(ack) and len(buffer) > len(ack):
                        # 如果紧跟标点或空格，立即切出
                        if not buffer[len(ack)].isalnum():
                            yield buffer[:len(ack)+1].strip()
                            buffer = buffer[len(ack)+1:]
                            is_first_sentence = False
                            break

                # 常规首句切分逻辑
                threshold = 16 if is_first_sentence else 24
                
                # 优化：如果缓冲区末尾是英文或数字（如 AI, HR），先不切分，防止切断专业术语
                if len(buffer) > threshold and not (buffer[-1].isalnum() or buffer[-1] == '-'):
                    yield buffer.strip()
                    buffer = ""
                    is_first_sentence = False
                break
                
    if buffer.strip():
        yield buffer.strip()
