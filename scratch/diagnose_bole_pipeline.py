
import os
import sys
import re
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

# 将项目根目录加入路径
sys.path.append(os.path.join(os.getcwd(), "AI-HR"))

from ai_hr.core.config import get_settings
from ai_hr.db.models import Job, Candidate, CandidateJobPipeline

def diagnose():
    settings = get_settings()
    engine = create_engine(settings.database_url)
    
    with Session(engine) as session:
        print("=== 1. 岗位配置诊断 ===")
        jobs = session.query(Job).filter(Job.auto_request_resume == True).all()
        if not jobs:
            print("警告: 没有任何岗位开启了 'auto_request_resume'!")
            return
            
        for job in jobs:
            print(f"岗位: {job.title} | 门槛: {job.min_degree}/{job.min_experience_years}年 | 每日限额: {job.max_daily_resume_requests}")
            
            # 检查今日已申请数量
            import datetime
            now = datetime.datetime.now()
            start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
            requested_today = session.query(CandidateJobPipeline).filter(
                CandidateJobPipeline.job_id == job.id,
                CandidateJobPipeline.last_resume_requested_at >= start_of_day
            ).count()
            print(f"  - 今日已申请: {requested_today} / {job.max_daily_resume_requests}")

        print("\n=== 2. 候选人流水线诊断 ===")
        # 统计符合基本条件的候选人
        pending_count = session.query(CandidateJobPipeline).join(Job).join(Candidate).filter(
            Job.auto_request_resume == True,
            CandidateJobPipeline.resume_request_status.is_(None),
            Candidate.metadata_synced_at.is_not(None)
        ).count()
        print(f"处于'待申请'排队中的候选人总数: {pending_count}")

        if pending_count > 0:
            print("\n=== 3. 筛选门槛模拟测试 (随机取5人) ===")
            samples = session.query(CandidateJobPipeline).join(Job).join(Candidate).filter(
                Job.auto_request_resume == True,
                CandidateJobPipeline.resume_request_status.is_(None),
                Candidate.metadata_synced_at.is_not(None)
            ).limit(5).all()

            degree_order = {"博士": 5, "硕士": 4, "本科": 3, "大专": 2, "中专": 1, "高中": 0}
            
            for p in samples:
                c = session.get(Candidate, p.candidate_id)
                j = session.get(Job, p.job_id)
                print(f"测试候选人: {c.name}")
                print(f"  - 候选人学历: [{c.degree}] | 岗位门槛: [{j.min_degree}]")
                
                # 学历比对逻辑
                c_rank = degree_order.get(c.degree or "", -1)
                j_rank = degree_order.get(j.min_degree or "", 0)
                degree_pass = c_rank >= j_rank
                print(f"  - 学历比对结果: {'通过' if degree_pass else '失败'}")
                
                # 经验比对逻辑
                exp_pass = True
                if j.min_experience_years:
                    exp_str = c.work_experience or ""
                    match = re.search(r"(\d+)", exp_str)
                    years = int(match.group(1)) if match else 0
                    exp_pass = years >= j.min_experience_years
                    print(f"  - 候选人经验: {exp_str} ({years}年) | 岗位门槛: {j.min_experience_years}年")
                    print(f"  - 经验比对结果: {'通过' if exp_pass else '失败'}")

        print("\n=== 4. 调度器运行检查 ===")
        print(f"Scheduler Enabled in Config: {settings.job_sync_scheduler_enabled}")

if __name__ == "__main__":
    diagnose()
