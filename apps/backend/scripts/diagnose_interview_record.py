"""Diagnose interview record data issues."""

from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import func, select

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from ai_hr.db.models import (
    AIInterviewAnswerRecord,
    AIInterviewInvitation,
    AIInterviewQuestionSet,
    AIInterviewSession,
    AIInterviewTurn,
    Event,
)
from ai_hr.db.session import SessionLocal


def diagnose_interview():
    """诊断面试记录数据"""
    session = SessionLocal()
    try:
        # 1. Find recent interview sessions
        print("=" * 80)
        print("1. Recent Interview Sessions")
        print("=" * 80)
        
        sessions = session.execute(
            select(AIInterviewSession)
            .order_by(AIInterviewSession.created_at.desc())
            .limit(5)
        ).scalars().all()
        
        if not sessions:
            print("❌ 没有找到任何面试会话")
            return
        
        for s in sessions:
            print(f"\nSession ID: {s.id}")
            print(f"  候选人: {s.candidate_id}")
            print(f"  岗位: {s.job_id}")
            print(f"  状态: {s.status}")
            print(f"  开始时间: {s.started_at}")
            print(f"  结束时间: {s.ended_at}")
            print(f"  Created at: {s.created_at}")
        
        # 2. Select a session for detailed inspection
        target_session = sessions[0]
        print("\n" + "=" * 80)
        print(f"2. Detailed Session Inspection: {target_session.id}")
        print("=" * 80)
        
        # Check question sets
        question_sets = session.execute(
            select(AIInterviewQuestionSet)
            .where(AIInterviewQuestionSet.session_id == target_session.id)
        ).scalars().all()
        
        print(f"\nQuestion Set Count: {len(question_sets)}")
        for qs in question_sets[:1]:  # Show only the first one
            print(f"\n  Question Set ID: {qs.id}")
            print(f"    Version: {qs.version}")
            print(f"    来源: {qs.source}")
            print(f"    问题数量: {len(qs.questions_json) if qs.questions_json else 0}")
            if qs.questions_json:
                for i, q in enumerate(qs.questions_json[:3], 1):
                    print(f"    Question #{i}: {q.get('question_text', '')[:80]}...")
        
        # Check conversation turns (including transcriptions)
        turns = session.execute(
            select(AIInterviewTurn)
            .where(AIInterviewTurn.session_id == target_session.id)
            .order_by(AIInterviewTurn.turn_no)
        ).scalars().all()
        
        print(f"\nConversation Turn Count: {len(turns)}")
        for t in turns[:10]:  # Show first 10
            print(f"\n  Turn #{t.turn_no}")
            print(f"    ID: {t.id}")
            print(f"    发言者: {t.speaker}")
            print(f"    问题ID: {t.question_id}")
            print(f"    问题序号: {t.question_seq}")
            print(f"    问题尝试ID: {t.question_attempt_id}")
            print(f"    转写文本: {t.transcript[:100] if t.transcript else '(空)'}...")
            print(f"    Audio URI: {t.audio_uri or '(none)'}")
        
        # Check answer records
        answers = session.execute(
            select(AIInterviewAnswerRecord)
            .where(AIInterviewAnswerRecord.session_id == target_session.id)
            .order_by(AIInterviewAnswerRecord.created_at)
        ).scalars().all()
        
        print(f"\nAnswer Record Count: {len(answers)}")
        for a in answers[:10]:  # Show first 10
            print(f"\n  Answer Record ID: {a.id}")
            print(f"    Question Attempt ID: {a.question_attempt_id}")
            print(f"    回答序号: {a.answer_no}")
            print(f"    回答轮次ID: {a.answer_turn_id}")
            print(f"    回答文本: {a.answer_text[:100] if a.answer_text else '(空)'}...")
            print(f"    是否最终: {a.is_final}")
            print(f"    来源: {a.source}")
            print(f"    Created at: {a.created_at}")
        
        # 3. Check invitation records (by candidate and job)
        print("\n" + "=" * 80)
        print("3. Check Invitation Records")
        print("=" * 80)
        
        invitation = session.execute(
            select(AIInterviewInvitation)
            .where(
                AIInterviewInvitation.candidate_id == target_session.candidate_id,
                AIInterviewInvitation.job_id == target_session.job_id
            )
            .order_by(AIInterviewInvitation.created_at.desc())
        ).first()
        
        if invitation:
            inv = invitation[0]
            print(f"\n邀请 ID: {inv.id}")
            print(f"  Token: {inv.token}")
            print(f"  状态: {inv.status}")
            print(f"  过期时间: {inv.expires_at}")
            print(f"  激活时间: {inv.activated_at}")
            print(f"  使用次数: {inv.used_count}/{inv.max_use_count}")
        else:
            print("\n❌ No associated invitation record found")
        
        # 4. Check interview events in Event table
        print("\n" + "=" * 80)
        print("4. Check Interview Events in Event Table")
        print("=" * 80)
        
        events = session.execute(
            select(Event)
            .where(Event.aggregate_id == target_session.id)
            .order_by(Event.created_at)
        ).scalars().all()
        
        print(f"\nEvent Count: {len(events)}")
        for e in events[:20]:  # Show first 20
            print(f"\n  Event ID: {e.id}")
            print(f"    Type: {e.event_type}")
            print(f"    聚合ID: {e.aggregate_id}")
            print(f"    创建时间: {e.created_at}")
            if e.payload:
                print(f"    Payload keys: {list(e.payload.keys())[:10]}")
        
        # 5. Statistics
        print("\n" + "=" * 80)
        print("5. Database Statistics")
        print("=" * 80)
        
        total_sessions = session.execute(select(func.count(AIInterviewSession.id))).scalar()
        total_turns = session.execute(select(func.count(AIInterviewTurn.id))).scalar()
        total_answers = session.execute(select(func.count(AIInterviewAnswerRecord.id))).scalar()
        total_events = session.execute(
            select(func.count(Event.id))
            .where(Event.aggregate_id == target_session.id)
        ).scalar()
        
        print(f"\n总会话数: {total_sessions}")
        print(f"总对话轮次: {total_turns}")
        print(f"总回答记录: {total_answers}")
        print(f"Events for this session: {total_events}")
        
        # 6. Check empty transcriptions
        print("\n" + "=" * 80)
        print("6. Check Empty Transcriptions")
        print("=" * 80)
        
        empty_transcripts = session.execute(
            select(AIInterviewTurn)
            .where(
                AIInterviewTurn.session_id == target_session.id,
                (AIInterviewTurn.transcript == None) | 
                (AIInterviewTurn.transcript == "")
            )
        ).scalars().all()
        
        print(f"\n空转写轮次数量: {len(empty_transcripts)}")
        for t in empty_transcripts[:5]:
            print(f"\n  轮次 ID: {t.id}")
            print(f"    会话: {t.session_id}")
            print(f"    轮次号: {t.turn_no}")
            print(f"    发言者: {t.speaker}")
            print(f"    问题ID: {t.question_id}")
            print(f"    Created at: {t.created_at}")
        
        # 7. Check empty answer texts
        print("\n" + "=" * 80)
        print("7. Check Empty Answer Texts")
        print("=" * 80)
        
        empty_answers = session.execute(
            select(AIInterviewAnswerRecord)
            .where(
                AIInterviewAnswerRecord.session_id == target_session.id,
                (AIInterviewAnswerRecord.answer_text == None) | 
                (AIInterviewAnswerRecord.answer_text == "")
            )
        ).scalars().all()
        
        print(f"\n空回答文本记录数量: {len(empty_answers)}")
        for a in empty_answers[:5]:
            print(f"\n  回答记录 ID: {a.id}")
            print(f"    问题尝试ID: {a.question_attempt_id}")
            print(f"    回答轮次ID: {a.answer_turn_id}")
            print(f"    创建时间: {a.created_at}")
    
    finally:
        session.close()


if __name__ == "__main__":
    diagnose_interview()
