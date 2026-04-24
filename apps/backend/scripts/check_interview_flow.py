"""Check interview data flow."""

from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import select

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from ai_hr.db.models import AIInterviewSession, Event
from ai_hr.db.session import SessionLocal

def check_interview_flow():
    """检查面试的数据流"""
    session = SessionLocal()
    try:
        # 获取最近的面试会话
        interview_session = session.execute(
            select(AIInterviewSession)
            .order_by(AIInterviewSession.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        
        if not interview_session:
            print("❌ 没有找到面试会话")
            return
        
        print(f"面试会话 ID: {interview_session.id}")
        print(f"状态: {interview_session.status}")
        print(f"Channel: {interview_session.channel}")
        print(f"开始时间: {interview_session.started_at}")
        print(f"结束时间: {interview_session.ended_at}")
        print(f"Payload keys: {list(interview_session.payload.keys()) if interview_session.payload else 'None'}")
        
        # 检查Event表中的相关事件
        print("\n" + "=" * 80)
        print("检查Event表中的事件")
        print("=" * 80)
        
        events = session.execute(
            select(Event)
            .where(Event.entity_id == interview_session.id)
            .order_by(Event.created_at)
        ).scalars().all()
        
        print(f"\n总事件数: {len(events)}")
        
        # 按事件类型分组
        event_types = {}
        for e in events:
            event_types[e.event_type] = event_types.get(e.event_type, 0) + 1
        
        print("\n事件类型统计:")
        for event_type, count in sorted(event_types.items()):
            print(f"  {event_type}: {count}")
        
        # 显示详细事件
        print("\n详细事件列表:")
        for e in events[:30]:
            print(f"\n  事件类型: {e.event_type}")
            print(f"    时间: {e.created_at}")
            print(f"    状态: {e.status}")
            if e.payload:
                # 显示关键payload字段
                keys = list(e.payload.keys())[:10]
                print(f"    Payload keys: {keys}")
                if 'transcript' in e.payload:
                    print(f"    Transcript: {e.payload['transcript'][:100]}...")
                if 'is_final' in e.payload:
                    print(f"    Is final: {e.payload['is_final']}")
                if 'asr_turn_id' in e.payload:
                    print(f"    ASR turn ID: {e.payload['asr_turn_id']}")
        
        # 检查是否有ASR相关事件
        asr_events = [e for e in events if 'asr' in e.event_type.lower()]
        print(f"\n\nASR相关事件数: {len(asr_events)}")
        
        # 检查是否有rtc相关事件
        rtc_events = [e for e in events if 'rtc' in e.event_type.lower()]
        print(f"RTC相关事件数: {len(rtc_events)}")
        
    finally:
        session.close()


if __name__ == "__main__":
    check_interview_flow()
