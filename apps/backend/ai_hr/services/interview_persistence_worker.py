"""Background persistence worker - asynchronously saves interview events to database."""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import Any


from ..core.config import get_settings
from ..db.session import SessionLocal
from ..repositories.ai_interviews import AIInterviewSessionRepository
from .orchestrator.event_bus import DEFAULT_INTERVIEW_EVENT_BUS, EventSubscription

logger = logging.getLogger(__name__)


class InterviewPersistenceWorker:
    """Background worker that listens to interview events and saves them to database asynchronously"""
    
    def __init__(self):
        self._running = False
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._active_sessions: dict[str, EventSubscription] = {}
        self._lock = threading.Lock()
        
    def start(self) -> None:
        """Start the background worker"""
        if self._running:
            logger.warning("Persistence worker already running")
            return
            
        self._running = True
        self._thread = threading.Thread(target=self._run_worker, daemon=True, name="interview-persistence")
        self._thread.start()
        logger.info("Interview persistence worker started")
    
    def stop(self) -> None:
        """Stop the background worker"""
        self._running = False
        if self._loop:
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("Interview persistence worker stopped")
    
    def _run_worker(self) -> None:
        """Main worker loop"""
        try:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            DEFAULT_INTERVIEW_EVENT_BUS.bind_loop(self._loop)
            
            self._loop.run_until_complete(self._worker_loop())
        except Exception as e:
            logger.error(f"Persistence worker crashed: {e}", exc_info=True)
        finally:
            if self._loop:
                self._loop.close()
    
    async def _worker_loop(self) -> None:
        """Main work loop"""
        logger.info("Persistence worker loop started")
        
        # Subscribe to all active sessions on startup
        await self._subscribe_active_sessions()
        
        # Periodically check for new sessions
        check_interval = 10  # Check every 10 seconds
        last_check = time.time()
        
        while self._running:
            try:
                # Periodically check for new active sessions
                if time.time() - last_check > check_interval:
                    await self._subscribe_active_sessions()
                    last_check = time.time()
                
                # Process all subscribed events
                await self._process_events()
                
                # Short sleep to avoid high CPU usage
                await asyncio.sleep(0.1)
                
            except Exception as e:
                logger.error(f"Error in worker loop: {e}", exc_info=True)
                await asyncio.sleep(1)
    
    async def _subscribe_active_sessions(self) -> None:
        """Subscribe to all active interview sessions"""
        try:
            db = SessionLocal()
            try:
                repo = AIInterviewSessionRepository(db)
                # Get active sessions from the last hour
                active_sessions = repo.list_sessions(window_minutes=60)
                
                for session in active_sessions:
                    # Only subscribe to in-progress sessions
                    if session.status in ("started", "created") and session.id not in self._active_sessions:
                        await self._subscribe_session(session.id)
                
                # Clean up subscriptions for completed sessions
                with self._lock:
                    for session_id in list(self._active_sessions.keys()):
                        session_entity = repo.get(session_id)
                        if session_entity.status in ("completed", "failed", "cancelled"):
                            await self._unsubscribe_session(session_id)
                            
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error subscribing active sessions: {e}", exc_info=True)
    
    async def _subscribe_session(self, session_id: str) -> None:
        """Subscribe to a single session's events"""
        try:
            subscription = DEFAULT_INTERVIEW_EVENT_BUS.subscribe(session_id=session_id)
            with self._lock:
                self._active_sessions[session_id] = subscription
            logger.info(f"Subscribed to session {session_id} for persistence")
        except Exception as e:
            logger.error(f"Error subscribing to session {session_id}: {e}", exc_info=True)
    
    async def _unsubscribe_session(self, session_id: str) -> None:
        """Unsubscribe from a session"""
        try:
            with self._lock:
                subscription = self._active_sessions.pop(session_id, None)
            if subscription:
                DEFAULT_INTERVIEW_EVENT_BUS.unsubscribe(subscription)
                logger.info(f"Unsubscribed from session {session_id}")
        except Exception as e:
            logger.error(f"Error unsubscribing from session {session_id}: {e}", exc_info=True)
    
    async def _process_events(self) -> None:
        """Process all subscribed events"""
        with self._lock:
            subscriptions = list(self._active_sessions.items())
        
        for session_id, subscription in subscriptions:
            try:
                # Non-blocking event retrieval
                while not subscription.queue.empty():
                    try:
                        event = subscription.queue.get_nowait()
                        await self._persist_event(session_id, event)
                    except asyncio.QueueEmpty:
                        break
            except Exception as e:
                logger.error(f"Error processing events for session {session_id}: {e}", exc_info=True)
    
    async def _persist_event(self, session_id: str, event: dict[str, Any]) -> None:
        """Persist a single event to database"""
        try:
            event_type = event.get("event_type", "")
            payload = event.get("payload", {})
            
            # Only process events that need persistence
            if event_type not in ("session.event", "asr.turn"):
                return
            
            # Extract key information
            transcript = str(payload.get("transcript", "")).strip()
            str(payload.get("speaker", ""))
            is_final = payload.get("is_final", True)
            
            # Only save final transcripts
            if not is_final or not transcript:
                return
            
            # Asynchronously save to database
            await asyncio.to_thread(self._save_to_database, session_id, event_type, payload)
            
        except Exception as e:
            logger.error(f"Error persisting event for session {session_id}: {e}", exc_info=True)
    
    def _save_to_database(self, session_id: str, event_type: str, payload: dict[str, Any]) -> None:
        """Synchronously save to database (executed in thread pool)"""
        db = SessionLocal()
        try:
            repo = AIInterviewSessionRepository(db)
            
            # Extract event information
            transcript = str(payload.get("transcript", "")).strip()
            speaker = str(payload.get("speaker", "candidate"))
            confidence = payload.get("confidence")
            occurred_at = payload.get("occurred_at")
            
            # Generate unique event_id (avoid conflicts with TEN Agent event_ids)
            event_id = f"persist-{session_id}-{int(time.time() * 1000000)}"
            
            # Directly call create_turn_event to save
            turn, deduplicated = repo.create_turn_event(
                session_id=session_id,
                event_id=event_id,
                speaker=speaker,
                transcript=transcript,
                audio_uri=None,
                confidence=confidence,
                latency_ms=None,
                question_attempt_id=None,
                question_id=None,
                question_seq=None,
                ingest_trace_id=None,
                policy_flags=["persistence_worker", event_type],
                payload={
                    "source": "persistence_worker",
                    "original_event_type": event_type,
                    "occurred_at": occurred_at,
                },
                transcript_ttl_days=180,
                audio_ttl_days=30,
            )
            
            if turn and not deduplicated:
                logger.debug(f"Persisted turn for session {session_id}, turn_id={turn.id}, turn_no={turn.turn_no}")
            
        except Exception as e:
            logger.error(f"Error saving to database for session {session_id}: {e}", exc_info=True)
            db.rollback()
        finally:
            db.close()


# Global singleton
_persistence_worker: InterviewPersistenceWorker | None = None


def get_persistence_worker() -> InterviewPersistenceWorker:
    """Get the persistence worker singleton"""
    global _persistence_worker
    if _persistence_worker is None:
        _persistence_worker = InterviewPersistenceWorker()
    return _persistence_worker


def start_persistence_worker() -> None:
    """Start the persistence worker"""
    settings = get_settings()
    if not settings.ai_interview_persistence_worker_enabled:
        logger.info("Interview persistence worker is disabled")
        return
    
    worker = get_persistence_worker()
    worker.start()


def stop_persistence_worker() -> None:
    """Stop the persistence worker"""
    worker = get_persistence_worker()
    worker.stop()
