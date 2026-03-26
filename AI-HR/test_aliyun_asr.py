import os
import sys
import time
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).parent
sys.path.append(str(PROJECT_ROOT))

from ai_hr.core.config import Settings
from ai_hr.services.speech.aliyun_providers import AliyunASRProvider

def test_aliyun_asr_init():
    print("Testing Aliyun ASR Provider Initialization...")
    
    # Try to import dashscope to verify installation
    try:
        import dashscope
        print(f"Dashscope SDK version: {dashscope.__version__}")
    except ImportError:
        print("Error: dashscope SDK not found. Run 'pip install dashscope'")
        return

    # Mock settings
    api_key = os.getenv("AI_HR_ASR_ALIYUN_API_KEY", "sk-test-key")
    
    provider = AliyunASRProvider(
        api_key=api_key,
        model="paraformer-realtime-v1",
        streaming_enabled=True
    )
    
    print(f"Provider created: {provider.provider_name}")
    
    # Test base64 decoding and basic structure (without real network call)
    try:
        # This will likely fail if the key is 'sk-test-key' but we just want to see it reach the SDK
        res = provider.transcribe_stream(
            session_id="verify_test",
            seq=1,
            text_hint="pre-defined",
            audio_base64=None,
            confidence=0.0,
            latency_ms=0,
            is_final=True
        )
        print(f"No-audio result: {res}")
    except Exception as e:
        print(f"Caught expected error or result: {e}")

if __name__ == "__main__":
    test_aliyun_asr_init()
