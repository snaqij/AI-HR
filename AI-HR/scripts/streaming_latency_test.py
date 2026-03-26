"""Verification script for Pipelined Streaming Latency."""

import time
import uuid
import json
from ai_hr.services.ai_interviews import get_ai_interview_service
from ai_hr.core.config import get_settings
from sqlalchemy import create_mock_engine # or real one if possible

def test_streaming_latency():
    print("=== Pipelined Streaming Latency Test ===")
    
    # Note: In a real environment, we'd need a DB session. 
    # For this verification, we'll assume the code is syntactically correct and logic is sound.
    # We can perform a dry-run or unit test of the orchestrator if needed.
    
    from ai_hr.services.orchestrator.realtime import RealtimeOrchestrator
    from ai_hr.services.speech.base import ASRProvider, TTSProvider, TTSStreamResult
    from unittest.mock import MagicMock
    
    mock_asr = MagicMock(spec=ASRProvider)
    mock_tts = MagicMock(spec=TTSProvider)
    mock_tts.provider_name = "mock"
    
    # Simulate TTS streaming
    def mock_synthesize_stream_iter(session_id, text, voice, chunk_size):
        yield {"index": 1, "audio_uri": "http://mock/1.mp3", "text": text, "is_final_packet": True}
        
    mock_tts.synthesize_stream_iter = mock_synthesize_stream_iter
    
    orchestrator = RealtimeOrchestrator(asr_provider=mock_asr, tts_provider=mock_tts)
    
    # Mock LLM stream
    def mock_build_llm_stream(transcript, confidence, stage, language):
        yield "Hello. "
        yield "How can I "
        yield "help you today?"
    
    mock_build_llm_stream.is_streaming = True
    
    packets = []
    def on_packet(p):
        packets.append(p)
        print(f"Captured packet: {p['text']}")

    print("Running process_candidate_turn...")
    start_time = time.perf_counter()
    orchestrator.process_candidate_turn(
        session_id="test-session",
        seq=1,
        transcript_hint="Hello AI",
        audio_base64=None,
        confidence=1.0,
        language="en-US",
        runtime_mode="llm_full",
        llm_enabled=True,
        decide_action=lambda t, c: ("followup", "test", []),
        build_rule_followup=lambda *args: None,
        build_llm_followup=mock_build_llm_stream,
        interview_stage="intro",
        on_audio_packet=on_packet
    )
    end_time = time.perf_counter()
    
    print(f"Total time: {(end_time - start_time)*1000:.2f}ms")
    print(f"Total packets: {len(packets)}")
    
    if len(packets) > 0:
        print("SUCCESS: Streaming pipeline is functional.")
    else:
        print("FAILURE: No audio packets generated.")

if __name__ == "__main__":
    test_streaming_latency()
