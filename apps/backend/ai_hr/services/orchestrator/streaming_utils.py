"""Streaming utilities for orchestrator."""

from __future__ import annotations
from typing import AsyncIterable, AsyncIterator, Iterable

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
            # Allow comma-based split for the first sentence to significantly reduce first-byte latency (TTFB)
            current_delimiters = main_delimiters
            if is_first_sentence:
                current_delimiters = main_delimiters + extra_delimiters
            
            # Find the earliest split point
            first_idx = -1
            for d in current_delimiters:
                pos = buffer.find(d)
                if pos != -1:
                    if first_idx == -1 or pos < first_idx:
                        first_idx = pos
            
            if first_idx != -1:
                # Extract sentence including trailing punctuation
                sentence = buffer[:first_idx + 1].strip()
                buffer = buffer[first_idx + 1:]
                if sentence:
                    yield sentence
                    is_first_sentence = False # After first output sentence, resume normal sentence-splitting logic
            else:
                # Add a fast-path for filler words to speed up first-sentence response
                acknowledgments = ["明白了", "好的", "理解了", "原来如此", "收到", "没问题", "确实"]
                
                # If buffer starts with filler words and shows pause tendency, split early
                for ack in acknowledgments:
                    if buffer.startswith(ack) and len(buffer) > len(ack):
                        # If immediately followed by punctuation/space, split immediately
                        if not buffer[len(ack)].isalnum():
                            yield buffer[:len(ack)+1].strip()
                            buffer = buffer[len(ack)+1:]
                            is_first_sentence = False
                            break

                threshold = 8 if is_first_sentence else 24

                if len(buffer) > threshold and not (buffer[-1].isalnum() or buffer[-1] == '-'):
                    yield buffer.strip()
                    buffer = ""
                    is_first_sentence = False
                break
                
    if buffer.strip():
        yield buffer.strip()

async def split_sentences_async(text_stream: AsyncIterable[str]) -> AsyncIterator[str]:
    """抽取流式文本中的完整句子 (异步版本)。"""
    buffer = ""
    is_first_sentence = True
    main_delimiters = (".", "!", "?", "。", "！", "？", "\n", ";", "；")
    extra_delimiters = (",", "，", ":", "：")
    
    async for chunk in text_stream:
        if not chunk:
            continue
        buffer += chunk
        
        while True:
            current_delimiters = main_delimiters
            if is_first_sentence:
                current_delimiters = main_delimiters + extra_delimiters
            
            first_idx = -1
            for d in current_delimiters:
                pos = buffer.find(d)
                if pos != -1:
                    if first_idx == -1 or pos < first_idx:
                        first_idx = pos
            
            if first_idx != -1:
                sentence = buffer[:first_idx + 1].strip()
                buffer = buffer[first_idx + 1:]
                if sentence:
                    yield sentence
                    is_first_sentence = False
            else:
                acknowledgments = ["明白了", "好的", "理解了", "原来如此", "收到", "没问题", "确实"]
                for ack in acknowledgments:
                    if buffer.startswith(ack) and len(buffer) > len(ack):
                        if not buffer[len(ack)].isalnum():
                            yield buffer[:len(ack)+1].strip()
                            buffer = buffer[len(ack)+1:]
                            is_first_sentence = False
                            break

                threshold = 8 if is_first_sentence else 24
                if len(buffer) > threshold and not (buffer[-1].isalnum() or buffer[-1] == '-'):
                    yield buffer.strip()
                    buffer = ""
                    is_first_sentence = False
                break
                
    if buffer.strip():
        yield buffer.strip()
