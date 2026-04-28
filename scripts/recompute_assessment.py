#!/usr/bin/env python3
"""重新计算面试评估（使用新的 AI 总结功能）"""
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "apps", "backend"))

from ai_hr.db.session import get_db_session
from ai_hr.services.enterprise_assessment import get_enterprise_assessment_service

def recompute_assessment(session_id: str):
    """重新计算评估"""
    
    print(f"🔄 重新计算评估: {session_id}")
    print(f"{'='*80}\n")
    
    with next(get_db_session()) as session:
        try:
            service = get_enterprise_assessment_service(session)
            
            print("📊 调用 compute_interview_assessment...")
            assessment, queue_id = service.compute_interview_assessment(
                session_id=session_id,
                run_mode="sync",
                policy_code="default",
                policy_version=None,
                force_recompute=True
            )
            
            print(f"✅ 评估计算完成!\n")
            print(f"{'='*80}")
            print(f"评估 ID: {assessment.id}")
            print(f"版本: {assessment.assessment_version}")
            print(f"状态: {assessment.status}")
            print(f"总分: {assessment.total_score}/100")
            print(f"推荐: {assessment.recommendation}")
            print(f"\n维度得分:")
            print(f"  - 专业能力: {assessment.competency_score}")
            print(f"  - 沟通表达: {assessment.communication_score}")
            print(f"  - 逻辑一致性: {assessment.consistency_score}")
            print(f"  - 稳定性: {assessment.stability_score}")
            print(f"  - 覆盖率: {assessment.coverage_score}")
            print(f"\n评估总结:")
            print(f"{assessment.summary}")
            print(f"\n优势 ({len(assessment.strengths_json or [])}):")
            for strength in (assessment.strengths_json or []):
                print(f"  - {strength}")
            print(f"\n不足 ({len(assessment.gaps_json or [])}):")
            for gap in (assessment.gaps_json or []):
                print(f"  - {gap}")
            print(f"\n风险标签 ({len(assessment.risk_flags_json or [])}):")
            for risk in (assessment.risk_flags_json or []):
                print(f"  - {risk}")
            print(f"\n{'='*80}")
            
        except Exception as e:
            print(f"❌ 评估失败: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python recompute_assessment.py <session_id>")
        print("示例: python recompute_assessment.py 20b4b821-7ee2-4dae-ba7c-ed09a5901698")
        sys.exit(1)
    
    session_id = sys.argv[1]
    recompute_assessment(session_id)
