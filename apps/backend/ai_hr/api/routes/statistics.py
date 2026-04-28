"""Statistics and dashboard API endpoints."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...db.session import get_db_session
from ...core.responses import Envelope
from ...db.models import (
    AIInterviewSession,
    Candidate,
    Job,
)

router = APIRouter(prefix="/statistics", tags=["statistics"])


@router.get("/dashboard")
def get_dashboard_statistics(
    session: Session = Depends(get_db_session),
):
    """
    获取仪表板统计数据
    
    返回:
    - 职位总数及变化
    - 候选人总数及变化
    - 面试完成数及变化
    - 录用转化率及变化
    """
    now = datetime.now(UTC)
    week_ago = now - timedelta(days=7)
    two_weeks_ago = now - timedelta(days=14)
    
    # 职位总数
    total_jobs_stmt = select(func.count(Job.id))
    total_jobs = session.scalar(total_jobs_stmt) or 0
    
    # 上周新增职位
    last_week_jobs_stmt = select(func.count(Job.id)).where(
        Job.created_at >= week_ago
    )
    last_week_jobs = session.scalar(last_week_jobs_stmt) or 0
    
    # 候选人总数
    total_candidates_stmt = select(func.count(Candidate.id))
    total_candidates = session.scalar(total_candidates_stmt) or 0
    
    # 上周新增候选人
    last_week_candidates_stmt = select(func.count(Candidate.id)).where(
        Candidate.created_at >= week_ago
    )
    last_week_candidates = session.scalar(last_week_candidates_stmt) or 0
    
    # 面试完成数（状态为 completed 的会话）
    completed_interviews_stmt = select(func.count(AIInterviewSession.id)).where(
        AIInterviewSession.status == "completed"
    )
    completed_interviews = session.scalar(completed_interviews_stmt) or 0
    
    # 上周完成的面试
    last_week_completed_stmt = select(func.count(AIInterviewSession.id)).where(
        AIInterviewSession.status == "completed",
        AIInterviewSession.updated_at >= week_ago
    )
    last_week_completed = session.scalar(last_week_completed_stmt) or 0
    
    # 录用转化率计算
    # 总面试数
    total_interviews_stmt = select(func.count(AIInterviewSession.id)).where(
        AIInterviewSession.status == "completed"
    )
    total_interviews = session.scalar(total_interviews_stmt) or 0
    
    # 录用数（假设通过评估分数判断，评估分数 >= 70 为录用）
    hired_stmt = select(func.count(AIInterviewSession.id)).where(
        AIInterviewSession.status == "completed",
        AIInterviewSession.overall_score >= 70.0
    )
    hired_count = session.scalar(hired_stmt) or 0
    
    # 上周录用数
    last_week_hired_stmt = select(func.count(AIInterviewSession.id)).where(
        AIInterviewSession.status == "completed",
        AIInterviewSession.overall_score >= 70.0,
        AIInterviewSession.updated_at >= week_ago
    )
    last_week_hired = session.scalar(last_week_hired_stmt) or 0
    
    # 前一周录用数（用于计算变化）
    prev_week_hired_stmt = select(func.count(AIInterviewSession.id)).where(
        AIInterviewSession.status == "completed",
        AIInterviewSession.overall_score >= 70.0,
        AIInterviewSession.updated_at >= two_weeks_ago,
        AIInterviewSession.updated_at < week_ago
    )
    prev_week_hired = session.scalar(prev_week_hired_stmt) or 0
    
    # 计算转化率
    hire_rate = (hired_count / total_interviews * 100) if total_interviews > 0 else 0.0
    
    # 计算上周转化率
    last_week_total_stmt = select(func.count(AIInterviewSession.id)).where(
        AIInterviewSession.status == "completed",
        AIInterviewSession.updated_at >= week_ago
    )
    last_week_total = session.scalar(last_week_total_stmt) or 0
    last_week_rate = (last_week_hired / last_week_total * 100) if last_week_total > 0 else 0.0
    
    # 计算前一周转化率
    prev_week_total_stmt = select(func.count(AIInterviewSession.id)).where(
        AIInterviewSession.status == "completed",
        AIInterviewSession.updated_at >= two_weeks_ago,
        AIInterviewSession.updated_at < week_ago
    )
    prev_week_total = session.scalar(prev_week_total_stmt) or 0
    prev_week_rate = (prev_week_hired / prev_week_total * 100) if prev_week_total > 0 else 0.0
    
    rate_delta = last_week_rate - prev_week_rate
    
    return Envelope.success({
        "job_count": {
            "total": total_jobs,
            "delta": last_week_jobs,
            "delta_text": f"较上周 +{last_week_jobs}"
        },
        "candidate_count": {
            "total": total_candidates,
            "delta": last_week_candidates,
            "delta_text": f"较上周 +{last_week_candidates}"
        },
        "interview_completed": {
            "total": completed_interviews,
            "delta": last_week_completed,
            "delta_text": f"较上周 +{last_week_completed}"
        },
        "hire_rate": {
            "rate": round(hire_rate, 1),
            "delta": round(rate_delta, 1),
            "delta_text": f"较上周 {'+' if rate_delta >= 0 else ''}{round(rate_delta, 1)}%"
        }
    })


@router.get("/trends")
def get_recruitment_trends(
    session: Session = Depends(get_db_session),
    days: int = 7,
):
    """
    获取招聘趋势数据（按天统计）
    
    参数:
    - days: 统计天数，默认 7 天
    
    返回每天的候选人新增数量
    """
    now = datetime.now(UTC)
    trends = []
    
    # 获取最近 N 天的数据
    for i in range(days - 1, -1, -1):
        day_start = (now - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        
        # 统计当天新增候选人数
        stmt = select(func.count(Candidate.id)).where(
            Candidate.created_at >= day_start,
            Candidate.created_at < day_end
        )
        count = session.scalar(stmt) or 0
        
        # 获取星期几
        weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        weekday = weekday_names[day_start.weekday()]
        
        trends.append({
            "date": day_start.strftime("%Y-%m-%d"),
            "label": weekday,
            "value": count
        })
    
    return Envelope.success({"trends": trends})


@router.get("/channels")
def get_channel_performance(
    session: Session = Depends(get_db_session),
):
    """
    获取渠道表现数据
    
    返回各渠道的转化率和描述
    """
    # 统计各渠道的候选人数和面试完成数
    channels = []
    
    # BOSS 直聘
    boss_candidates_stmt = select(func.count(Candidate.id)).where(
        Candidate.source_channel == "boss"
    )
    boss_candidates = session.scalar(boss_candidates_stmt) or 0
    
    boss_completed_stmt = select(func.count(AIInterviewSession.id)).where(
        AIInterviewSession.status == "completed",
        Candidate.id == AIInterviewSession.candidate_id,
        Candidate.source_channel == "boss"
    ).select_from(AIInterviewSession).join(Candidate)
    boss_completed = session.scalar(boss_completed_stmt) or 0
    
    boss_rate = (boss_completed / boss_candidates * 100) if boss_candidates > 0 else 0.0
    
    channels.append({
        "label": "BOSS 直聘",
        "rate": round(boss_rate, 1),
        "rate_text": f"转化率 {round(boss_rate, 1)}%",
        "desc": "投递量持续增长，技术岗位的候选人质量稳定。",
        "candidates": boss_candidates,
        "completed": boss_completed
    })
    
    # 猎聘（如果有数据）
    liepin_candidates_stmt = select(func.count(Candidate.id)).where(
        Candidate.source_channel == "liepin"
    )
    liepin_candidates = session.scalar(liepin_candidates_stmt) or 0
    
    if liepin_candidates > 0:
        liepin_completed_stmt = select(func.count(AIInterviewSession.id)).where(
            AIInterviewSession.status == "completed",
            Candidate.id == AIInterviewSession.candidate_id,
            Candidate.source_channel == "liepin"
        ).select_from(AIInterviewSession).join(Candidate)
        liepin_completed = session.scalar(liepin_completed_stmt) or 0
        
        liepin_rate = (liepin_completed / liepin_candidates * 100) if liepin_candidates > 0 else 0.0
        
        channels.append({
            "label": "猎聘",
            "rate": round(liepin_rate, 1),
            "rate_text": f"转化率 {round(liepin_rate, 1)}%",
            "desc": "高年限岗位表现较优，建议继续保留预算。",
            "candidates": liepin_candidates,
            "completed": liepin_completed
        })
    
    # 内推渠道
    referral_candidates_stmt = select(func.count(Candidate.id)).where(
        Candidate.source_channel == "referral"
    )
    referral_candidates = session.scalar(referral_candidates_stmt) or 0
    
    if referral_candidates > 0:
        referral_completed_stmt = select(func.count(AIInterviewSession.id)).where(
            AIInterviewSession.status == "completed",
            Candidate.id == AIInterviewSession.candidate_id,
            Candidate.source_channel == "referral"
        ).select_from(AIInterviewSession).join(Candidate)
        referral_completed = session.scalar(referral_completed_stmt) or 0
        
        referral_rate = (referral_completed / referral_candidates * 100) if referral_candidates > 0 else 0.0
        
        channels.append({
            "label": "内推渠道",
            "rate": round(referral_rate, 1),
            "rate_text": f"转化率 {round(referral_rate, 1)}%",
            "desc": "质量最高，适合重点岗位优先曝光与跟进。",
            "candidates": referral_candidates,
            "completed": referral_completed
        })
    
    return Envelope.success({"channels": channels})
