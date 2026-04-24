"""Test persistence worker"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from sqlalchemy import select

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from ai_hr.db.models import AIInterviewSession, AIInterviewTurn
from ai_hr.db.session import SessionLocal
from ai_hr.services.interview_persistence_worker import get_persistence_worker
from ai_hr.services.orchestrator.event_bus import DEFAULT_INTERVIEW_EVENT_BUS


def test_persistence_worker():
    """Test the persistence worker"""
    print("=" * 80)
    print("Testing Persistence Worker")
    print("=" * 80)
    
    # Get the most recent interview session
    db = SessionLocal()
    try:
        session = db.execute(
            select(AIInterviewSession)
            .order_by(AIInterviewSession.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        
        if not session:
            print("❌ No interview session found")
            return
        
        session_id = session.id
        print(f"\nTest session: {session_id}")
        print(f"Status: {session.status}")
        
        # Check current turn count
        turn_count_before = db.execute(
            select(AIInterviewTurn)
            .where(AIInterviewTurn.session_id == session_id)
        ).scalars().all()
        print(f"Current turn count: {len(turn_count_before)}")
        
    finally:
        db.close()
    
    # Start persistence worker
    print("\nStarting persistence worker...")
    worker = get_persistence_worker()
    worker.start()
    
    # Wait for worker to start
    time.sleep(2)
    
    # Simulate sending events
    print("\nSimulating interview events...")
    for i in range(3):
        DEFAULT_INTERVIEW_EVENT_BUS.publish(
            session_id=session_id,
            event_type="session.event",
            payload={
                "transcript": f"This is test message #{i+1}",
                "speaker": "candidate",
                "is_final": True,
                "confidence": 0.95,
                "occurred_at": f"2026-04-23T{15+i}:00:00",
            }
        )
        print(f"  Sent event #{i+1}")
        time.sleep(0.5)
    
    # Wait for processing
    print("\nWaiting for event processing...")
    time.sleep(5)
    
    # Check results
    db = SessionLocal()
    try:
        turns = db.execute(
            select(AIInterviewTurn)
            .where(AIInterviewTurn.session_id == session_id)
            .order_by(AIInterviewTurn.turn_no)
        ).scalars().all()
        
        print(f"\nTurn count after processing: {len(turns)}")
        print(f"New turns added: {len(turns) - len(turn_count_before)}")
        
        if len(turns) > len(turn_count_before):
            print("\n✅ Persistence worker test successful!")
            print("\nLatest turns:")
            for turn in turns[-3:]:
                print(f"  Turn #{turn.turn_no}: {turn.transcript[:50]}...")
        else:
            print("\n❌ Persistence worker failed to save data")
            
    finally:
        db.close()
    
    # Stop worker
    print("\nStopping persistence worker...")
    worker.stop()
    print("Test complete")


if __name__ == "__main__":
    test_persistence_worker()
