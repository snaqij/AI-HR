import sys
import os
from datetime import datetime

# Add the project directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "AI-HR")))

from ai_hr.schemas.candidates import CandidateImportItem
from pydantic import ValidationError

def test_metadata_mapping():
    print("Testing CandidateImportItem with new metadata fields...")
    
    raw_data = {
        "name": "Metadata Test",
        "source_channel": "boss",
        "external_candidate_id": "test-id-123",
        "school": "Tsinghua University",
        "degree": "PhD",
        "work_experience": "10 years",
        "expected_salary": "50k-80k",
        "latest_company": "BigTech Corp",
        "applied_at": "2026-04-13T10:00:00",
        "raw_profile": {"original": "payload"}
    }
    
    try:
        item = CandidateImportItem(**raw_data)
        print("[OK] Successfully created CandidateImportItem with metadata.")
        assert item.school == "Tsinghua University"
        assert item.degree == "PhD"
        assert item.work_experience == "10 years"
        assert item.expected_salary == "50k-80k"
        assert item.latest_company == "BigTech Corp"
        print("[OK] All fields correctly mapped and validated.")
    except ValidationError as e:
        print(f"[FAIL] Validation failed: {e}")
        sys.exit(1)
    except AssertionError as e:
        print(f"[FAIL] Assertion failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    test_metadata_mapping()
