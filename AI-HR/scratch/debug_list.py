from sqlalchemy import select
from ai_hr.db.session import SessionLocal
from ai_hr.repositories.job_candidates import JobCandidateRepository
from ai_hr.db.models import Job

def test_list():
    session = SessionLocal()
    repo = JobCandidateRepository(session)
    
    # Get a job ID
    job = session.execute(select(Job)).scalars().first()
    if not job:
        print("No jobs found")
        return
    
    print(f"Testing job: {job.title} ({job.id})")
    
    items, next_cursor, has_more = repo.list_by_job(job.id, limit=10)
    print(f"Items found: {len(items)}")
    for it in items:
        try:
            eval_score = it.evaluation.final_score if it.evaluation else 'None'
            print(f" - Candidate: {it.candidate.name}, Eval: {eval_score}")
        except Exception as e:
            print(f" - Error accessing attributes for candidate: {e}")
    
    session.close()

if __name__ == "__main__":
    test_list()
