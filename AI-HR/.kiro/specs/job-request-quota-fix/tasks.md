# Implementation Plan

- [ ] 1. Write bug condition exploration test
  - **Property 1: Bug Condition** - Quota Count Includes Non-Request Records
  - **CRITICAL**: This test MUST FAIL on unfixed code - failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior - it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate the bug exists
  - **Scoped PBT Approach**: Scope the property to concrete failing case: a pipeline record where mark_resume_visible() was called but mark_resume_requested() was never called
  - Test that count_requests_today() incorrectly includes records where last_resume_requested_at was set by mark_resume_visible() (resume_request_count = 0) instead of mark_resume_requested()
  - Create a test scenario: mark a pipeline as "visible" with last_resume_requested_at=None, verify count_requests_today() incorrectly counts it
  - Run test on UNFIXED code
  - **EXPECTED OUTCOME**: Test FAILS (count includes the record even though resume_request_count = 0)
  - Document counterexamples found to understand root cause
  - Mark task complete when test is written, run, and failure is documented
  - _Requirements: 1.1, 1.2, 1.3, 1.4_

- [ ] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** - Existing Request Tracking Behavior
  - **IMPORTANT**: Follow observation-first methodology
  - Observe behavior on UNFIXED code for actual resume request scenarios
  - Write property-based tests capturing observed behavior patterns:
    - mark_resume_requested() increments resume_request_count
    - mark_resume_requested() sets last_resume_requested_at to current time
    - mark_resume_visible() sets resume_request_status to "visible"
    - Individual pipeline records maintain their last_resume_requested_at and resume_request_count fields
  - Property-based testing generates many test cases for stronger guarantees
  - Run tests on UNFIXED code
  - **EXPECTED OUTCOME**: Tests PASS (this confirms baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [ ] 3. Fix for daily resume request quota counting

  - [ ] 3.1 Implement the fix in count_requests_today()
    - Modify count_requests_today() method in CandidateJobPipelineRepository
    - Replace the timestamp-based counting logic (last_resume_requested_at >= start_of_day)
    - Use sum of resume_request_count field for records created/updated today
    - Query: SELECT SUM(resume_request_count) WHERE job_id = ? AND (created_at >= start_of_day OR updated_at >= start_of_day)
    - _Bug_Condition: isBugCondition(record) = (record.last_resume_requested_at is set by mark_resume_visible() AND record.resume_request_count = 0)_
    - _Expected_Behavior: count_requests_today() returns sum of resume_request_count for actual requests only_
    - _Preservation: mark_resume_requested() continues to increment resume_request_count and set last_resume_requested_at; mark_resume_visible() continues to set status; retry logic continues to work; individual record fields remain accessible_
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 3.3, 3.4, 3.5_

  - [ ] 3.2 Verify bug condition exploration test now passes
    - **Property 1: Expected Behavior** - Quota Count Excludes Non-Request Records
    - **IMPORTANT**: Re-run the SAME test from task 1 - do NOT write a new test
    - The test from task 1 encodes the expected behavior
    - When this test passes, it confirms the expected behavior is satisfied
    - Run bug condition exploration test from step 1
    - **EXPECTED OUTCOME**: Test PASSES (count_requests_today() now correctly excludes records with resume_request_count = 0)
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [ ] 3.3 Verify preservation tests still pass
    - **Property 2: Preservation** - Existing Request Tracking Behavior
    - **IMPORTANT**: Re-run the SAME tests from task 2 - do NOT write new tests
    - Run preservation property tests from step 2
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions)
    - Confirm all tests still pass after fix (no regressions)

- [ ] 4. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.
