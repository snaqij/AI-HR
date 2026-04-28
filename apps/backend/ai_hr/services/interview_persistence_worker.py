"""Background persistence worker - asynchronously saves interview events to database."""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import Any


from ..core.config import get_settings
from ..core.exceptions import ResourceNotFoundError
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
        self._active_question_context: dict[str, dict[str, str]] = {}
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
                    # Subscribe to sessions that can still emit realtime answer events.
                    if session.status in ("created", "started", "in_progress") and session.id not in self._active_sessions:
                        await self._subscribe_session(session.id)
                
                # Clean up subscriptions for completed sessions
                with self._lock:
                    for session_id in list(self._active_sessions.keys()):
                        try:
                            session_entity = repo.get(session_id)
                        except ResourceNotFoundError:
                            logger.warning(
                                "Persistence worker found stale active session subscription; removing session_id=%s",
                                session_id,
                            )
                            await self._unsubscribe_session(session_id)
                            continue
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
                self._active_question_context.pop(session_id, None)
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

            # Process canonical realtime events and TEN bridge finals.
            if event_type not in ("session.event", "asr.turn", "candidate.final", "question.final", "question.update"):
                return

            transcript = str(
                payload.get("transcript")
                or payload.get("text")
                or payload.get("spoken_text")
                or ""
            ).strip()

            raw_question_id = str(payload.get("question_id") or "").strip()
            raw_question_seq_value = payload.get("question_seq")
            try:
                raw_question_seq = int(raw_question_seq_value) if raw_question_seq_value is not None else None
            except (TypeError, ValueError):
                raw_question_seq = None
            raw_topic_name = str(payload.get("topic_name") or "").strip()
            raw_trace_id = str(payload.get("trace_id") or "").strip()
            raw_phase = str(payload.get("phase") or "").strip().lower()
            raw_topic_id = str(payload.get("topic_id") or "").strip()
            raw_parent_topic_id = str(payload.get("parent_topic_id") or "").strip()
            raw_is_followup = bool(payload.get("is_followup", False))
            if event_type in ("question.update", "question.final"):
                with self._lock:
                    prev_ctx = dict(self._active_question_context.get(session_id, {}) or {})
                    self._active_question_context[session_id] = {
                        "question_id": raw_question_id or str(prev_ctx.get("question_id") or "").strip(),
                        "question_seq": raw_question_seq if raw_question_seq is not None else prev_ctx.get("question_seq"),
                        "topic_name": raw_topic_name or str(prev_ctx.get("topic_name") or "").strip(),
                        "trace_id": raw_trace_id or str(prev_ctx.get("trace_id") or "").strip(),
                        "phase": raw_phase or str(prev_ctx.get("phase") or "").strip(),
                        "topic_id": raw_topic_id or str(prev_ctx.get("topic_id") or "").strip(),
                        "parent_topic_id": raw_parent_topic_id or str(prev_ctx.get("parent_topic_id") or "").strip(),
                        "is_followup": raw_is_followup if "is_followup" in payload else bool(prev_ctx.get("is_followup", False)),
                    }

            inferred_speaker = str(payload.get("speaker") or "").strip().lower()
            if not inferred_speaker:
                if event_type == "question.final":
                    inferred_speaker = "ai"
                else:
                    inferred_speaker = "candidate"

            resolved_question_id = raw_question_id
            resolved_question_seq = raw_question_seq
            resolved_topic_name = raw_topic_name
            resolved_trace_id = raw_trace_id
            resolved_phase = raw_phase
            resolved_topic_id = raw_topic_id
            resolved_parent_topic_id = raw_parent_topic_id
            resolved_is_followup = raw_is_followup
            if event_type == "candidate.final":
                with self._lock:
                    ctx = dict(self._active_question_context.get(session_id, {}) or {})
                resolved_question_id = resolved_question_id or str(ctx.get("question_id") or "").strip()
                if resolved_question_seq is None:
                    ctx_seq = ctx.get("question_seq")
                    try:
                        resolved_question_seq = int(ctx_seq) if ctx_seq is not None else None
                    except (TypeError, ValueError):
                        resolved_question_seq = None
                resolved_topic_name = resolved_topic_name or str(ctx.get("topic_name") or "").strip()
                resolved_trace_id = resolved_trace_id or str(ctx.get("trace_id") or "").strip()
                resolved_phase = resolved_phase or str(ctx.get("phase") or "").strip()
                resolved_topic_id = resolved_topic_id or str(ctx.get("topic_id") or "").strip()
                resolved_parent_topic_id = resolved_parent_topic_id or str(ctx.get("parent_topic_id") or "").strip()
                if "is_followup" not in payload:
                    resolved_is_followup = bool(ctx.get("is_followup", False))

            # Bridge final events are authoritative finals.
            default_is_final = event_type in ("candidate.final", "question.final")
            is_final = bool(payload.get("is_final", default_is_final))

            if not is_final or not transcript:
                return

            await asyncio.to_thread(
                self._save_to_database,
                session_id,
                event_type,
                payload,
                inferred_speaker,
                transcript,
                resolved_question_id,
                resolved_question_seq,
                resolved_topic_name,
                resolved_trace_id,
                resolved_phase,
                resolved_topic_id,
                resolved_parent_topic_id,
                resolved_is_followup,
            )

        except Exception as e:
            logger.error(f"Error persisting event for session {session_id}: {e}", exc_info=True)

    def _save_to_database(
        self,
        session_id: str,
        event_type: str,
        payload: dict[str, Any],
        speaker: str,
        transcript: str,
        question_id: str,
        question_seq: int | None,
        topic_name: str,
        trace_id: str,
        phase: str,
        topic_id: str,
        parent_topic_id: str,
        is_followup: bool,
    ) -> None:
        """Synchronously save to database (executed in thread pool)"""
        db = SessionLocal()
        try:
            repo = AIInterviewSessionRepository(db)

            confidence = payload.get("confidence")
            occurred_at = payload.get("occurred_at")
            question_id_value = question_id.strip() or None
            question_seq_value = int(question_seq) if isinstance(question_seq, int) else None
            
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
                question_id=question_id_value,
                question_seq=question_seq_value,
                ingest_trace_id=None,
                policy_flags=["persistence_worker", event_type],
                payload={
                    "source": "persistence_worker",
                    "original_event_type": event_type,
                    "occurred_at": occurred_at,
                    "question_id": question_id_value,
                    "question_seq": question_seq_value,
                    "topic_name": topic_name.strip() or None,
                    "trace_id": trace_id.strip() or None,
                    "phase": phase.strip() or None,
                    "topic_id": topic_id.strip() or None,
                    "parent_topic_id": parent_topic_id.strip() or None,
                    "is_followup": bool(is_followup),
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
