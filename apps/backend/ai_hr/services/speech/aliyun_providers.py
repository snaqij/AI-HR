import logging
import threading
import time
import json
import dashscope
from dashscope.audio.asr import Recognition, RecognitionCallback, RecognitionResult
import nls # alibabacloud-nls-python-sdk
from ai_hr.services.speech.base import ASRProvider, ASRStreamResult

logger = logging.getLogger(__name__)

try:
    from ai_hr.services.orchestrator.event_bus import DEFAULT_INTERVIEW_EVENT_BUS
except ImportError:
    DEFAULT_INTERVIEW_EVENT_BUS = None

class AliyunNlsTokenManager:
    """Singleton manager for Aliyun NLS tokens."""
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super(AliyunNlsTokenManager, cls).__new__(cls)
                    cls._instance._token = None
                    cls._instance._expire_time = 0
        return cls._instance

    def get_token(self, ak_id: str, ak_secret: str) -> str:
        with self._lock:
            now = time.time()
            if self._token and now < self._expire_time - 600: # Refresh 10 minutes before expiration
                return self._token
            
            try:
                import json
                from aliyunsdkcore.client import AcsClient
                from aliyunsdkcore.request import CommonRequest
                
                logger.debug(f"Requesting Aliyun NLS token for AK ID: {ak_id}")
                client = AcsClient(ak_id, ak_secret, "cn-shanghai")
                request = CommonRequest()
                request.set_method('POST')
                request.set_domain('nls-meta.cn-shanghai.aliyuncs.com')
                request.set_version('2019-02-28')
                request.set_action_name('CreateToken')
                
                response = client.do_action_with_exception(request)
                response_json = json.loads(response)
                
                if 'Token' in response_json:
                    token_data = response_json['Token']
                    self._token = token_data.get("Id")
                    self._expire_time = token_data.get("ExpireTime", 0)
                    logger.info(f"Successfully generated Aliyun NLS token, expires at {self._expire_time}")
                    return self._token
                else:
                    logger.error(f"Aliyun NLS Token not in response: {response_json}")
                    raise ValueError(f"Aliyun NLS Token generation failed: {response_json}")
            except Exception as e:
                logger.error(f"Failed to generate Aliyun NLS token: {e}")
                raise

class AliyunNlsASRProvider(ASRProvider):
    """Production-grade ASR implementation backed by Aliyun NLS."""
    provider_name = "aliyun_nls"
    _KEEPALIVE_INTERVAL_SEC = 10.0
    _IDLE_RECONNECT_SEC = 28.0
    _SILENT_PCM_16K_MONO_20MS = b"\x00" * 640

    def __init__(
        self,
        *,
        appkey: str,
        access_key_id: str,
        access_key_secret: str,
        streaming_enabled: bool = True,
        vocabulary_id: str | None = None,
        customization_id: str | None = None,
    ):
        self._appkey = appkey
        self._ak_id = access_key_id
        self._ak_secret = access_key_secret
        self._streaming_enabled = streaming_enabled
        self._vocabulary_id = vocabulary_id
        self._customization_id = customization_id
        self._token_manager = AliyunNlsTokenManager()
        self._contexts: dict[str, _AliyunNlsContext] = {}
        self._backoff_until: dict[str, float] = {}
        self._lock = threading.Lock()
        self._connecting_sessions: set[str] = set() # To prevent concurrent start() calls for the same session

        # Diagnostic counters (thread-safe; all updates under self._lock)
        self._stat_connect_attempts: int = 0    # Total connection attempts
        self._stat_connect_success: int = 0     # Successful handshakes
        self._stat_connect_failed: int = 0      # Handshake failures (timeout/rate-limit/exception)
        self._stat_backoff_hits: int = 0        # Rejected by backoff count
        self._stat_concurrent_hits: int = 0     # Skipped due to ongoing concurrent connection attempts
        self._stat_audio_frames: int = 0        # Audio frames sent to NLS
        self._stat_audio_bytes: int = 0         # Audio bytes sent to NLS

    def _log_stats(self, label: str) -> None:
        """Log a diagnostic stats snapshot at INFO level."""
        logger.info(
            "[NLS-STATS] %s | "
            "connect_attempts=%d success=%d failed=%d "
            "backoff_hits=%d concurrent_hits=%d "
            "audio_frames=%d audio_bytes=%d "
            "active_sessions=%d",
            label,
            self._stat_connect_attempts,
            self._stat_connect_success,
            self._stat_connect_failed,
            self._stat_backoff_hits,
            self._stat_concurrent_hits,
            self._stat_audio_frames,
            self._stat_audio_bytes,
            len(self._contexts),
        )

    def warmup(self, *, session_id: str) -> None:
        """NLS warmup: pre-fetch token and pre-establish connection."""
        try:
            # Pre-fetch token
            self._token_manager.get_token(self._ak_id, self._ak_secret)
            # Pre-establish connection (outside lock)
            self._ensure_context(session_id)
            logger.info(f"NLS Warmup completed for session {session_id}")
        except Exception as e:
            logger.warning(f"NLS Warmup failed for session {session_id}: {e}")

    def transcribe_stream(
        self,
        *,
        session_id: str,
        seq: int,
        text_hint: str = "",
        audio_base64: str | None = None,
        audio_bytes: bytes | None = None,
        confidence: float,
        latency_ms: int,
        chunk_index: int = 1,
        chunk_total: int = 1,
        is_final: bool = True,
        voice_format: str | None = None,
    ) -> ASRStreamResult:
        if (not audio_base64 and not audio_bytes) or not self._streaming_enabled:
            return ASRStreamResult(
                transcript=text_hint.strip() if text_hint else "",
                confidence=confidence,
                latency_ms=latency_ms,
                provider=self.provider_name
            )

        call_start = time.perf_counter()
        stream_key = session_id

        try:
            if not audio_bytes and audio_base64:
                import base64
                if isinstance(audio_base64, str) and audio_base64.strip():
                    audio_bytes = base64.b64decode(audio_base64)
                else:
                    audio_bytes = b""
        except Exception as e:
            logger.error(f"Failed to decode audio for NLS: {e}")
            audio_bytes = b""

        logger.debug(f"NLS transcribe_stream session={session_id} seq={seq} final={is_final} len={len(audio_bytes)}")
        ctx = self._ensure_context(stream_key)
        if not ctx:
            # Important: return empty transcript if backoff is active to avoid triggering LLM
            return ASRStreamResult(
                transcript="",
                confidence=confidence,
                latency_ms=latency_ms,
                provider=f"{self.provider_name}_backoff"
            )
        if not ctx.is_active:
            # Fast self-heal after TaskFailed timeout: rebuild context on current call.
            # If it was a standard timeout, we clear backoff to allow immediate reconnection.
            is_timeout = getattr(ctx.callback, "is_timeout", False)
            if is_timeout:
                with self._lock:
                    self._backoff_until.pop(stream_key, None)
                logger.info(f"[NLS] session={session_id} applying fast self-heal for timeout error")

            self._close_context(stream_key)
            ctx = self._ensure_context(stream_key)
            if not ctx:
                return ASRStreamResult(
                    transcript="",
                    confidence=confidence,
                    latency_ms=latency_ms,
                    provider=f"{self.provider_name}_reconnect_backoff"
                )

        # Transport keepalive: when no user audio arrives for a while, send a short silent frame
        # to avoid NLS gateway idle timeout. This does not alter business transcript semantics.
        now = time.time()
        idle_since_audio = now - getattr(ctx, "last_audio_sent_at", 0.0)
        if idle_since_audio >= self._IDLE_RECONNECT_SEC:
            logger.info(
                "[NLS] session=%s idle_for=%.1fs exceeded reconnect threshold, rebuilding context",
                session_id,
                idle_since_audio,
            )
            self._close_context(stream_key)
            ctx = self._ensure_context(stream_key)
            if not ctx:
                return ASRStreamResult(
                    transcript="",
                    confidence=confidence,
                    latency_ms=latency_ms,
                    provider=f"{self.provider_name}_idle_reconnect_backoff"
                )

        now = time.time()
        idle_for_keepalive = now - getattr(ctx, "last_audio_sent_at", 0.0)
        keepalive_gap = now - getattr(ctx, "last_keepalive_at", 0.0)
        if idle_for_keepalive >= self._KEEPALIVE_INTERVAL_SEC and keepalive_gap >= self._KEEPALIVE_INTERVAL_SEC:
            try:
                ctx.callback.last_audio_sent_epoch = ctx.callback.epoch
                ctx.recognizer.send_audio(self._SILENT_PCM_16K_MONO_20MS)
                ctx.last_keepalive_at = now
                ctx.last_audio_sent_at = now
                with self._lock:
                    self._stat_audio_frames += 1
                    self._stat_audio_bytes += len(self._SILENT_PCM_16K_MONO_20MS)
                logger.debug("[NLS] session=%s keepalive sent", session_id)
            except Exception as keepalive_err:
                logger.warning(f"[NLS] session={session_id} keepalive failed, reconnecting: {keepalive_err}")
                self._close_context(stream_key)
                ctx = self._ensure_context(stream_key)
                if not ctx:
                    return ASRStreamResult(
                        transcript="",
                        confidence=confidence,
                        latency_ms=latency_ms,
                        provider=f"{self.provider_name}_keepalive_reconnect_backoff"
                    )
        
        try:
            # Always update current_seq regardless of audio_bytes presence, 
            # as long as we have a context, to ensure events have correct turn ID.
            ctx.callback.current_seq = seq

            if audio_bytes:
                # Mark current epoch before sending to SDK
                ctx.callback.last_audio_sent_epoch = ctx.callback.epoch
                ctx.recognizer.send_audio(audio_bytes)
                now = time.time()
                ctx.last_audio_sent_at = now
                ctx.last_keepalive_at = now
                with self._lock:
                    self._stat_audio_frames += 1
                    self._stat_audio_bytes += len(audio_bytes)
            
            if is_final:
                # Procedural finalization: immediately publish the best available transcript as Final
                # This mitigates delayed responses caused by server-side pause detection latency
                # Must be called before stop() to avoid SDK stop-path blocking
                final_now = ctx.callback.full_transcript
                if final_now.strip():
                    ctx.callback._publish_asr_turn(is_final=True, fragment=final_now)

                # Force stop to trigger server-side finalize logic
                try:
                    ctx.recognizer.stop()
                except Exception as stop_err:
                    logger.warning(f"NLS stop error: {stop_err}")

            # Remove synchronous blocking wait; read the best transcript directly from callback state.
            transcript = ctx.callback.full_transcript
            
            # Add latency tracing: record absolute timestamps produced by ASR
            metadata = {
                "is_final": is_final, 
                "sentence_completed": ctx.received_completed,
                "asr_final_ts": time.perf_counter(),
                "asr_sentence_start_ts": ctx.callback.sentence_start_ts,
                "asr_physical_stop_ts": getattr(ctx.callback, "asr_physical_stop_ts", 0.0),
            }
            
            return ASRStreamResult(
                transcript=transcript,
                confidence=0.98,
                latency_ms=max(1, int((time.perf_counter() - call_start) * 1000)),
                provider=self.provider_name,
                metadata=metadata,
                is_active_pushed=True,
            )
        except Exception as e:
            logger.error(f"Aliyun NLS processing error: {e}")
            self._close_context(stream_key) # This will now safely stop the recognizer outside the lock
            return ASRStreamResult(transcript="", confidence=confidence, latency_ms=latency_ms, provider=f"{self.provider_name}_fault")

    def flush(self, *, session_id: str) -> None:
        """Clear accumulated sentence state to prevent cross-turn transcript bleed."""
        with self._lock:
            ctx = self._contexts.get(session_id)
            if ctx:
                ctx.flush()

    def _ensure_context(self, stream_key: str) -> "_AliyunNlsContext | None":
        now = time.time()
        
        # First check under lock for existing context or backoff/connecting state
        with self._lock:
            if stream_key in self._backoff_until and now < self._backoff_until[stream_key]:
                self._stat_backoff_hits += 1
                remaining = self._backoff_until[stream_key] - now
                if self._stat_backoff_hits % 100 == 1: # Only log every 100 hits to avoid spamming
                    logger.warning(
                        "[NLS] session=%s in backoff, %.1fs remaining | total_hits=%d",
                        stream_key, remaining, self._stat_backoff_hits
                    )
                return None
            if stream_key in self._connecting_sessions:
                # Another thread is already trying to establish connection for this session
                self._stat_concurrent_hits += 1
                logger.debug(
                    "[NLS] session=%s already connecting (concurrent skip) | concurrent_hits=%d",
                    stream_key, self._stat_concurrent_hits
                )
                return None

            ctx = self._contexts.get(stream_key)
            if ctx and (not ctx.is_active or (now - ctx.last_active_at > 15.0)):
                idle_sec = now - ctx.last_active_at
                logger.info(
                    "[NLS] session=%s context invalid or idle (is_active=%s idle=%.1fs), closing and reconnecting",
                    stream_key, ctx.is_active, idle_sec
                )
                # Pop under lock, and prepare to stop it
                ctx_to_close = self._contexts.pop(stream_key, None)
                if ctx_to_close:
                    try:
                        # Attempt to stop outside lock if possible, but for simplicity here we just trigger it
                        ctx_to_close.recognizer.stop()
                    except Exception:
                        pass
                ctx = None
            
            if ctx: # Found an active, non-idle context
                ctx.last_active_at = now
                return ctx
            
            # No active context, need to create one. Mark as connecting.
            self._stat_connect_attempts += 1
            attempt_no = self._stat_connect_attempts
            self._connecting_sessions.add(stream_key)
        
        logger.info(
            "[NLS] session=%s initiating connection (attempt #%d)",
            stream_key, attempt_no
        )
        
        # --- Connection establishment outside the main lock ---
        recognizer = None
        callback = None
        try:
            token = self._token_manager.get_token(self._ak_id, self._ak_secret)
            
            # Use a threading.Event for backoff signaling from the callback
            backoff_event = threading.Event()
            callback = _AliyunNlsCallback(
                session_id=stream_key,
                on_error_trigger=lambda is_rate_limit: backoff_event.set()
            )
            
            recognizer = nls.NlsSpeechTranscriber(
                url="wss://nls-gateway.cn-shanghai.aliyuncs.com/ws/v1",
                token=token,
                appkey=self._appkey,
                on_start=callback.on_start,
                on_sentence_begin=callback.on_sentence_begin,
                on_sentence_end=callback.on_sentence_end,
                on_result_changed=callback.on_result_changed,
                on_completed=callback.on_completed,
                on_error=callback.on_error,
                on_close=callback.on_close,
                callback_args=[]
            )
            # Prepare extended parameters for the 'ex' dict argument
            ex_params = {}
            if self._vocabulary_id:
                ex_params["vocabulary_id"] = self._vocabulary_id
            if self._customization_id:
                ex_params["customization_id"] = self._customization_id

            try:
                # Based on SDK source, all extra params must go into the 'ex' dict
                recognizer.start(
                    aformat="pcm",
                    sample_rate=16000,
                    ch=1,
                    enable_intermediate_result=True,
                    enable_punctuation_prediction=True,
                    enable_inverse_text_normalization=True,
                    ex=ex_params if ex_params else None
                )
            except Exception as e:
                logger.error(f"Failed to start NLS with extended params: {e}. Retrying with defaults.")
                recognizer.start(aformat="pcm", sample_rate=16000, ch=1)
            
            # SDK BUG: start() returns as soon as __start_cond is notified.
            # On TaskFailed, the SDK notifies the cond FIRST, then calls on_error.
            # So start() can return "successfully" before on_error fires.
            # Fix: wait for definitive success (started_ok) or failure (error_event) signals.
            handshake_ok = callback.started_ok.wait(timeout=5.0) # Increased to 5s
            if not handshake_ok or callback.error_event.is_set():
                logger.error(f"Aliyun NLS handshake failed for {stream_key} (rate limited or timed out)")
                raise RuntimeError("NLS handshake failed.")

            ctx = _AliyunNlsContext(recognizer=recognizer, callback=callback)
            
            with self._lock:
                # Only add to contexts if another thread hasn't already established one
                if stream_key not in self._contexts:
                    self._contexts[stream_key] = ctx
                    self._backoff_until.pop(stream_key, None) # Clear backoff on success
                    self._stat_connect_success += 1
                    logger.info(
                        "[NLS] session=%s connection established (attempt #%d) | success=%d failed=%d",
                        stream_key, attempt_no, self._stat_connect_success, self._stat_connect_failed
                    )
                else:
                    # Race condition: another thread created context while we were starting.
                    # Close our newly created recognizer and use the existing one.
                    logger.info(
                        "[NLS] session=%s race-condition: another thread already connected, discarding ours",
                        stream_key
                    )
                    try:
                        recognizer.stop()
                    except Exception:
                        pass
                    ctx = self._contexts[stream_key] # Use the one already in the dict
                
                ctx.last_active_at = now
                self._log_stats(f"connect-ok session={stream_key}")
                return ctx
        except Exception as e:
            logger.error(f"Failed to initialize Aliyun NLS recognizer for {stream_key}: {e}")
            with self._lock:
                self._stat_connect_failed += 1
                # Read rate-limit flag from callback (set in on_error) rather than
                # parsing the re-raised RuntimeError string, which is always generic.
                is_rate_limit = callback.is_rate_limited if callback else False
                backoff_sec = 5.0 if is_rate_limit else 2.0
                self._backoff_until[stream_key] = now + backoff_sec
                logger.error(
                    "[NLS] session=%s connection FAILED (attempt #%d), rate_limited=%s backoff=%.1fs | success=%d failed=%d",
                    stream_key, attempt_no, is_rate_limit, backoff_sec,
                    self._stat_connect_success, self._stat_connect_failed
                )
                self._log_stats(f"connect-fail session={stream_key}")
            if recognizer:
                try:
                    recognizer.stop()
                except Exception:
                    pass
            return None
        finally:
            with self._lock:
                self._connecting_sessions.discard(stream_key) # Always remove from connecting set

    def _close_context_internal(self, stream_key: str) -> "_AliyunNlsContext | None":
        """Internal method to pop context from dict under lock, but doesn't stop recognizer."""
        with self._lock:
            return self._contexts.pop(stream_key, None)

    def _close_context(self, stream_key: str) -> None:
        """Safely closes a context, stopping the recognizer outside the lock."""
        ctx = self._close_context_internal(stream_key)
        if ctx:
            try:
                ctx.recognizer.stop()
            except Exception as e:
                logger.warning(f"Error stopping NLS recognizer for {stream_key}: {e}")

class _AliyunNlsCallback:
    def __init__(self, session_id: str, on_error_trigger=None):
        self.session_id = session_id
        self.sentences: list[str] = []
        self.current_sentence: str = ""
        self.received_completed = False
        self.is_active = False  # Only True after RecognitionStarted confirmed
        self.current_seq = 0    # Current turn sequence from service layer
        self.started_ok = threading.Event()   # Set when RecognitionStarted received
        self.error_event = threading.Event()  # Set on any on_error callback
        self.is_rate_limited = False          # Set when Gateway returns TOO_MANY_REQUESTS
        self.is_timeout = False               # Set when Request Timeout occurs
        self._on_error_trigger = on_error_trigger
        
        # Epoch tracking to prevent cross-turn transcript pollution
        self.epoch = 0
        self.last_audio_sent_epoch = -1
        self.current_sentence_epoch = -1
        self.completed_event = threading.Event()
        self.last_flush_at = 0.0
        self.sentence_start_ts = 0.0
        self.asr_physical_stop_ts = 0.0  # Set by on_sentence_end; 0.0 means not yet confirmed
        self._last_final_fragment = ""
        self._last_final_seq = -1
        self._last_final_epoch = -1
        self._last_final_publish_at = 0.0
        self._publish_counter = 0

    def on_start(self, message, *args):
        """Called when TranscriptionStarted is received (for Transcriber)."""
        # Debug hook reserved for raw start message tracing.
        logger.debug("Aliyun NLS Transcriber started")
        # Initialize sync epoch to prevent first sentence from being skipped by init order
        self.current_sentence_epoch = self.epoch
        self.is_active = True
        self.started_ok.set()

    def on_sentence_begin(self, message, *args):
        # Debug hook reserved for sentence begin tracing.
        try:
            # Record sentence processing start time for end-to-end first-segment latency
            if not getattr(self, "sentence_start_ts", 0):
                self.sentence_start_ts = time.perf_counter()
                
            self.current_sentence_epoch = self.epoch
            logger.debug(f"NLS Sentence Begin | Epoch: {self.current_sentence_epoch}")
        except Exception:
            pass
    def on_result_changed(self, message, *args):
        # Debug hook reserved for partial result tracing.
        try:
            data = json.loads(message)
            payload = data.get("payload", {})
            
            # Epoch check: ignore results from stale turns
            if self.current_sentence_epoch != self.epoch:
                if time.time() - self.last_flush_at < 0.150:
                    pass 
                elif not self.sentences and self.epoch == self.current_sentence_epoch + 1:
                    self.current_sentence_epoch = self.epoch 
                else:
                    return

            self.current_sentence = payload.get("result", "")
            # Debug hook reserved for ASR progress tracing.
            logger.debug(f"NLS Intermediate: {self.current_sentence}")
            # Incremental publish: emit only the current in-progress sentence fragment
            self._publish_asr_turn(is_final=False, fragment=self.current_sentence)
        except Exception:
            pass

    def on_sentence_end(self, message, *args):
        # Debug hook reserved for sentence end tracing.
        try:
            data = json.loads(message)
            payload = data.get("payload", {})
            
            # Epoch check: ignore stale sentence-end callbacks (with same 150ms soft tolerance)
            if self.current_sentence_epoch != self.epoch and (time.time() - self.last_flush_at > 0.150):
                return

            final_text = payload.get("result", "")
            if final_text:
                self.sentences.append(final_text)
            self.current_sentence = ""
            
            # Physical close-mouth moment: record ASR sentence-cut time for trigger-delay metrics
            self.asr_physical_stop_ts = time.perf_counter()
            self.received_completed = True
            self.completed_event.set()
            
            logger.debug("aliyun_nls.asr_final session_id=%s final_text=%s", self.session_id, final_text)
            logger.debug(f"NLS Sentence End: {final_text}")
            # Incremental publish: emit only the newly completed sentence
            self._publish_asr_turn(is_final=True, fragment=final_text)
        except Exception:
            pass

    def on_completed(self, message, *args):
        # Transcriber on_completed indicates whole-task completion (e.g., after stop()); usually no business logic here.
        logger.debug(f"Aliyun NLS Transcriber Task Completed: {message}")

    def on_error(self, message, *args):
        logger.error(f"Aliyun NLS error callback: {message}")
        self.is_active = False
        msg_str = str(message).lower()
        self.is_rate_limited = "too_many_requests" in msg_str or "rate" in msg_str
        self.is_timeout = (
            "request timeout" in msg_str
            or "idle_timeout" in msg_str
            or "websocket session is idle for too long time" in msg_str
        )
        
        if self.is_timeout:
            # Unblock final wait and avoid hanging on dead task.
            self.received_completed = True
            logger.warning(f"[NLS] session={self.session_id} detected timeout/idle-timeout, signaling fast self-heal")
            self.completed_event.set()
        
        self.error_event.set()  # Signal failure (lock-free)
        self.started_ok.set()   # Unblock any waiting handshake check
        if self._on_error_trigger:
            self._on_error_trigger(is_rate_limit=self.is_rate_limited)

    def on_close(self, *args):
        logger.debug("Aliyun NLS connection closed")
        self.is_active = False

    def flush(self):
        """Clear accumulated sentence state to prevent cross-turn transcript bleed."""
        self.epoch += 1
        self.last_flush_at = time.time()
        self.sentences = []
        self.current_sentence = ""
        self.received_completed = False
        self.sentence_start_ts = 0.0
        self.asr_physical_stop_ts = 0.0  # Reset to prevent stale ts leaking into next turn
        self.completed_event.clear()
        self._last_final_fragment = ""
        self._last_final_seq = -1
        self._last_final_epoch = -1
        self._last_final_publish_at = 0.0

    @property
    def full_transcript(self) -> str:
        return "".join(self.sentences) + self.current_sentence

    def _publish_asr_turn(self, is_final: bool = False, fragment: str = ""):
        """Publish an incremental ASR fragment to the event bus."""
        normalized_fragment = str(fragment or "").strip()
        if not normalized_fragment or not DEFAULT_INTERVIEW_EVENT_BUS:
            return

        # Deduplicate only exact repeated finals in a very short window.
        # Do not suppress different finals within the same epoch, otherwise long answers lose sentences.
        if is_final:
            now = time.time()
            compact = " ".join(normalized_fragment.split())
            is_immediate_duplicate = (
                compact == self._last_final_fragment
                and self.current_seq == self._last_final_seq
                and self.epoch == self._last_final_epoch
                and (now - self._last_final_publish_at) <= 0.8
            )
            if is_immediate_duplicate:
                logger.debug(
                    "aliyun_nls.skip_duplicate_final session_id=%s seq=%s epoch=%s fragment=%s",
                    self.session_id,
                    self.current_seq,
                    self.epoch,
                    compact[:60],
                )
                return
            self._last_final_fragment = compact
            self._last_final_seq = self.current_seq
            self._last_final_epoch = self.epoch
            self._last_final_publish_at = now
        self._publish_counter += 1

        try:
            if is_final:
                logger.debug("aliyun_nls.eventbus_publish_final session_id=%s fragment=%s", self.session_id, normalized_fragment[:60])
            
            DEFAULT_INTERVIEW_EVENT_BUS.publish(
                session_id=self.session_id,
                event_type="asr.turn",
                payload={
                    "event_id": f"nls-{self.session_id}-{self.epoch}-{self.current_seq}-{self._publish_counter}",
                    "turn_id": f"nls-turn-{self.session_id}-{self.epoch}-{self.current_seq}",
                    "seq": self.current_seq,
                    "speaker": "candidate" if is_final else "candidate_partial",
                    "transcript": normalized_fragment,
                    "latency_ms": 0,
                    "is_final": is_final,
                },
            )
        except Exception as e:
            logger.warning(f"Failed to publish active ASR turn: {e}")

class _AliyunNlsContext:
    def __init__(self, recognizer: nls.NlsSpeechTranscriber, callback: _AliyunNlsCallback):
        self.recognizer = recognizer
        self.callback = callback
        now = time.time()
        self.last_active_at = now
        self.last_audio_sent_at = now
        self.last_keepalive_at = now

    def flush(self):
        self.callback.flush()

    @property
    def last_transcript(self) -> str:
        return self.callback.full_transcript

    @property
    def received_completed(self) -> bool:
        return self.callback.received_completed

    @property
    def is_active(self) -> bool:
        return self.callback.is_active


class AliyunASRProvider(ASRProvider):
    provider_name = "aliyun"

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "paraformer-realtime-v1",
        streaming_enabled: bool = True,
    ):
        self._api_key = api_key
        self._model = model
        self._streaming_enabled = streaming_enabled
        self._contexts: dict[str, _AliyunASRContext] = {}
        self._backoff_until: dict[str, float] = {}
        self._lock = threading.Lock()
        
        # Set API key globally for dashscope or locally per request
        dashscope.api_key = api_key

    def warmup(self, *, session_id: str) -> None:
        """Optional warmup hook for Aliyun ASR."""
        return None

    def transcribe_stream(
        self,
        *,
        session_id: str,
        seq: int,
        text_hint: str,
        audio_base64: str | None = None,
        audio_bytes: bytes | None = None,
        confidence: float = 0.9,
        latency_ms: int = 500,
        chunk_index: int = 1,
        chunk_total: int = 1,
        is_final: bool = True,
        voice_format: str | None = None,
    ) -> ASRStreamResult:
        if not audio_base64:
            return ASRStreamResult(
                transcript=text_hint.strip() if text_hint else "",
                confidence=confidence,
                latency_ms=latency_ms,
                provider=self.provider_name
            )

        if not self._streaming_enabled or not self._api_key:
            logger.warning("Aliyun ASR streaming disabled or API key missing")
            return ASRStreamResult(
                transcript=text_hint,
                confidence=confidence,
                latency_ms=latency_ms,
                provider=f"{self.provider_name}_disabled"
            )

        call_start = time.perf_counter()
        stream_key = session_id # We reuse connection per session if possible
        try:
            if not audio_bytes and audio_base64: # Only attempt decoding if audio_base64 is provided
                import base64
                # Ensure audio_base64 is a string before decoding
                if isinstance(audio_base64, str) and audio_base64.strip():
                    audio_bytes = base64.b64decode(audio_base64)
                else:
                    audio_bytes = b""
        except Exception as e:
            logger.error(f"Failed to decode audio: {e}")
            audio_bytes = b""

        ctx = self._ensure_context(stream_key)
        if not ctx:
            return ASRStreamResult(
                transcript=text_hint,
                confidence=confidence,
                latency_ms=latency_ms,
                provider=f"{self.provider_name}_backoff"
            )
        
        try:
            if audio_bytes:
                ctx.recognition.send_audio_frame(audio_bytes)
            
            # If it is the last chunk of a sequence, we might want to wait a bit for results
            # But Paraformer-Realtime is very fast, callbacks are usually async.
            # We rely on the context to hold the latest transcript.
            
            # Wait a tiny bit if needed (Aliyun is usually sub-100ms)
            if is_final:
                # For final chunks, we can afford a bit more wait
                wait_deadline = time.perf_counter() + 0.5
                while time.perf_counter() < wait_deadline and not ctx.received_final:
                    time.sleep(0.02)
            
            transcript = ctx.last_transcript or text_hint
            
            # If this was the final chunk of the session/turn, we might want to reset?
            # Actually, AIInterviewService manages session life.
            
            return ASRStreamResult(
                transcript=transcript,
                confidence=0.95, # Aliyun doesn't provide per-sentence confidence easily in this SDK
                latency_ms=max(1, int((time.perf_counter() - call_start) * 1000)),
                provider=f"{self.provider_name}_paraformer",
                metadata={"is_final": ctx.received_final}
            )
        except Exception as e:
            logger.error(f"Aliyun ASR error: {e}")
            self._close_context(stream_key)
            return ASRStreamResult(
                transcript=text_hint,
                confidence=confidence,
                latency_ms=latency_ms,
                provider=f"{self.provider_name}_error"
            )

    def _ensure_context(self, stream_key: str) -> "_AliyunASRContext | None":
        with self._lock:
            now = time.time()
            if stream_key in self._backoff_until and now < self._backoff_until[stream_key]:
                return None

            ctx = self._contexts.get(stream_key)
            # Auto-reconnect if idle for > 20s to avoid Aliyun code=44 timeout
            is_idle = ctx is not None and (now - ctx.last_active_at > 20.0)
            
            if ctx is None or not ctx.is_active or is_idle:
                if ctx:
                    self._close_context(stream_key)
                
                # Create callback with a way to report backoff
                def _trigger_backoff(is_rate_limit: bool = False):
                    if is_rate_limit:
                        with self._lock:
                            self._backoff_until[stream_key] = time.time() + 5.0 # 5s backoff for rate limits

                callback = _AliyunCallback(on_error_trigger=_trigger_backoff)
                recognition = Recognition(
                    model=self._model,
                    format='pcm',
                    sample_rate=16000,
                    callback=callback
                )
                try:
                    recognition.start()
                    ctx = _AliyunASRContext(recognition=recognition, callback=callback)
                    self._contexts[stream_key] = ctx
                    # Clear backoff on success
                    self._backoff_until.pop(stream_key, None)
                except Exception as e:
                    logger.error(f"Failed to start Aliyun ASR: {e}")
                    self._backoff_until[stream_key] = now + 5.0 # Longer backoff on start failure
                    return None
            
            ctx.last_active_at = now
            return ctx

    def _close_context(self, stream_key: str) -> None:
        with self._lock:
            ctx = self._contexts.pop(stream_key, None)
            if ctx:
                try:
                    ctx.recognition.stop()
                except Exception:
                    pass

class _AliyunCallback(RecognitionCallback):
    def __init__(self, on_error_trigger=None):
        self.sentences: list[str] = []
        self.current_sentence: str = ""
        self.received_final = False
        self.is_active = True
        self._on_error_trigger = on_error_trigger

    def on_open(self) -> None:
        logger.debug("Aliyun ASR connection opened")

    def on_close(self) -> None:
        logger.debug("Aliyun ASR connection closed")
        self.is_active = False

    def on_event(self, result: RecognitionResult) -> None:
        sentence = result.get_sentence()
        if sentence:
            text = sentence.get('text', '')
            if sentence.get('is_final'):
                if text:
                    self.sentences.append(text)
                self.current_sentence = ""
            else:
                self.current_sentence = text
        logger.debug(f"Aliyun ASR event: {self.full_transcript}")

    def on_error(self, result: RecognitionResult) -> None:
        # dashscope.RecognitionResult (DashScopeResponse) uses dictionary-like access or getattr for message/status_code
        msg = getattr(result, 'message', 'unknown error').lower()
        code = getattr(result, 'status_code', 'unknown code')
        logger.error(f"Aliyun ASR error event: code={code}, message={msg}")
        self.is_active = False
        if self._on_error_trigger:
            # Only trigger backoff penalty for rate limits or other severe errors, not for timeouts
            is_rate_limit = "rate limit" in msg or "exceeded" in msg or "too many" in msg
            self._on_error_trigger(is_rate_limit=is_rate_limit)

    def on_complete(self) -> None:
        logger.debug("Aliyun ASR completion")
        self.received_final = True

    @property
    def full_transcript(self) -> str:
        return "".join(self.sentences) + self.current_sentence

class _AliyunASRContext:
    def __init__(self, recognition: Recognition, callback: _AliyunCallback):
        self.recognition = recognition
        self.callback = callback
        self.last_active_at = time.time()

    @property
    def last_transcript(self) -> str:
        return self.callback.full_transcript

    @property
    def received_final(self) -> bool:
        return self.callback.received_final

    @property
    def is_active(self) -> bool:
        return self.callback.is_active
