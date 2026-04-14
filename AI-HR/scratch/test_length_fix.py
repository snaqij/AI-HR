from ai_hr.schemas.candidates import CandidateImportItem
from pydantic import ValidationError

# A very long string (200 chars) to test the fix
long_id = "a" * 200

try:
    item = CandidateImportItem(
        name="Test User",
        source_channel="boss",
        external_candidate_id=long_id,
        raw_profile={}
    )
    print("SUCCESS: CandidateImportItem accepted long external_candidate_id")
except ValidationError as e:
    print(f"FAILURE: ValidationError still occurring: {e}")
except Exception as e:
    print(f"ERROR: {e}")
