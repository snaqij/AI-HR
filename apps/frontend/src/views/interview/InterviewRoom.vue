<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { AgoraRTCGateway } from "../../agoraGateway";
import {
  bootstrapDemoSession,
  buildInterviewEventsWsUrl,
  createInterviewSession,
  finishInterviewSession,
  getInterviewSession,
  getTenRuntimeConfig,
  joinInterviewRTC,
  joinInterviewRTCPreflight,
  launchTenSession,
  loadReplayItems,
  renewInterviewRTCToken,
  startInterviewSession,
  type InterviewRTCJoinInfo,
  type InterviewRealtimeEvent,
  type InterviewSession,
  type ReplayItem
} from "../../api";

interface TimelineItem {
  speaker: string;
  transcript: string;
  startSecond: number;
  endSecond: number;
  kind?: "confirmed" | "draft_fallback";
}

interface AppendTranscriptOptions {
  forceSeparate?: boolean;
}

const TRANSCRIPT_MERGE_WINDOW_SECONDS = 8;
const CANDIDATE_DRAFT_FALLBACK_MS = 1800;
const RTC_CLIENT_ID = "web";

const SESSION_STORAGE_KEY = "ai_hr_active_session";

const loading = ref(true);
const errorText = ref("");
const exiting = ref(false);
const meetingTimeText = ref("00:00");
const elapsedSeconds = ref(0);
const micEnabled = ref(true);
const cameraEnabled = ref(true);
const showSettingsHint = ref(false);
const interviewerSpeaking = ref(false);
const interviewEnded = ref(false);
const candidateVideoMount = ref<HTMLElement | null>(null);
const transcriptScrollRef = ref<HTMLElement | null>(null);
const canScrollTranscriptUp = ref(false);
const isTranscriptPinnedToLatest = ref(true);

const session = ref<InterviewSession | null>(null);
const sessionId = computed(() => session.value?.id || "");

const micStatus = ref("等待麦克风连接...");
const ttsStatus = ref("等待面试官语音...");
const currentQuestion = ref("正在准备面试链路...");
const followupQuestion = ref("");
const transportStatus = ref("未连接");
const transcriptView = ref<TimelineItem[]>([]);
const seenReplayTurnIds = new Set<string>();
const seenRealtimeEventIds = new Set<string>();
const recentAsrFinalMap = new Map<string, number>();
const candidateDraft = ref("");
const candidateDraftOccurredAt = ref("");
const timelineBaseEpochMs = ref<number | null>(null);
const tenLaunchCommand = ref("");
const audioRecoveryHint = ref("");
const tenPendingHint = ref("");
const rtcRecoveryInFlight = ref(false);
const rtcFailureRecoverAttempts = ref(0);

let tickerTimer: number | null = null;
let candidateDraftFallbackTimer: number | null = null;
let eventsSocket: WebSocket | null = null;

const roleTitle = computed(() => "后端工程师面试");
const sessionLabel = computed(() => {
  if (loading.value) return "连接中";
  if (exiting.value) return "结束中";
  if (interviewEnded.value) return "已结束";
  return "实时面试";
});
const networkTone = computed(() => {
  const status = transportStatus.value;
  if (status.includes("Connected")) {
    return { text: "网络优秀", state: "good" };
  }
  if (status.includes("connecting") || status.includes("reconnecting") || status.includes("connected") || status.includes("??")) {
    return { text: "连接中", state: "pending" };
  }
  if (status.includes("failed") || status.includes("disconnected") || status.includes("abnormal")) {
    return { text: "连接异常", state: "bad" };
  }
  return { text: "等待连接", state: "idle" };
});

const interviewerBannerText = computed(() => {
  if (interviewerSpeaking.value) {
    return "面试官正在发言";
  }
  if (ttsStatus.value.includes("speaking") || ttsStatus.value.includes("playing")) {
    return "面试官正在发言";
  }
  if (ttsStatus.value.includes("waiting") || ttsStatus.value.includes("ready") || ttsStatus.value.includes("listening")) {
    return "面试官正在倾听";
  }
  return ttsStatus.value;
});

const rtcGateway = new AgoraRTCGateway({
  onRemoteAudioSubscribed(uid) {
    ttsStatus.value = `面试官已接入 (${uid})`;
    interviewerSpeaking.value = false;
    audioRecoveryHint.value = "";
    tenPendingHint.value = "";
    errorText.value = "";
  },
  onRemoteAudioUnsubscribed() {
    ttsStatus.value = "面试官音频已暂停";
    interviewerSpeaking.value = false;
  },
  onRemoteAudioSpeakingChanged(speaking) {
    interviewerSpeaking.value = speaking;
    if (speaking) {
      ttsStatus.value = "面试官正在发言";
    } else if (ttsStatus.value.includes("speaking") || ttsStatus.value.includes("audio")) {
      ttsStatus.value = "面试官正在倾听";
    }
  },
  onConnectionStateChanged(state, reason) {
    transportStatus.value = formatTransportStatus(state, reason);
    const normalized = String(state || "").trim().toUpperCase();
    if (state === "CONNECTED") {
      micStatus.value = micEnabled.value ? "候选人音频已接入" : "候选人已静音";
      rtcFailureRecoverAttempts.value = 0;
      errorText.value = "";
      return;
    }
    if (normalized === "FAILED" || normalized === "DISCONNECTED") {
      void recoverRtcConnection({
        trigger: "connection-state-change",
        forceReconnect: true,
        expectedTokenIssue: isLikelyTokenIssueReason(reason),
      });
    }
  },
  onTokenWillExpire() {
    void recoverRtcConnection({
      trigger: "token-will-expire",
      forceReconnect: false,
      expectedTokenIssue: true,
    });
  },
  onTokenDidExpire() {
    void recoverRtcConnection({
      trigger: "token-did-expire",
      forceReconnect: true,
      expectedTokenIssue: true,
    });
  },
  onRemoteAudioPlaybackError(message) {
    ttsStatus.value = "远端音频需要用户交互";
    audioRecoveryHint.value = message || "浏览器阻止了自动播放，请点击启用音频后重试。";
  }
});

function formatAgoraReason(reason?: string | null): string {
  const value = String(reason || "").trim();
  if (!value) return "";
  const normalized = value.toUpperCase();
  if (normalized === "JOIN_SUCCESS") return "加入成功";
  if (normalized === "INTERRUPTED") return "网络中断";
  if (normalized === "LEAVE_CHANNEL") return "已离开频道";
  if (normalized === "BANNED_BY_SERVER") return "被服务端禁用";
  if (normalized === "KEEP_ALIVE_TIMEOUT") return "心跳超时";
  return value;
}

function formatTransportStatus(state?: string | null, reason?: string | null): string {
  const normalized = String(state || "").trim().toUpperCase();
  const reasonText = formatAgoraReason(reason);
  let stateText = "等待连接";
  switch (normalized) {
    case "CONNECTED": stateText = "Agora 已连接"; break;
    case "CONNECTING": stateText = "Agora 连接中"; break;
    case "RECONNECTING": stateText = "Agora 重连中"; break;
    case "DISCONNECTED": stateText = "Agora 已断开"; break;
    case "DISCONNECTING": stateText = "Agora 断开中"; break;
    case "FAILED": stateText = "Agora 连接失败"; break;
    default: if (state) stateText = `Agora 状态：${state}`;
  }
  return reasonText ? `${stateText} (${reasonText})` : stateText;
}

function isLikelyTokenIssueReason(reason?: string | null): boolean {
  const normalized = String(reason || "").trim().toUpperCase();
  if (!normalized) return false;
  return normalized.includes("TOKEN") || normalized.includes("EXPIRE") || normalized === "9";
}

async function fetchLatestRtcJoinInfo(): Promise<InterviewRTCJoinInfo> {
  if (!session.value) throw new Error("Session not ready");
  return renewInterviewRTCToken(session.value.id, session.value.candidate_id, RTC_CLIENT_ID);
}

async function restoreLocalMediaState(): Promise<void> {
  try {
    await rtcGateway.setMicrophoneEnabled(micEnabled.value);
  } catch (err) {
    console.warn("[RTC] failed to restore microphone state", err);
  }
  try {
    await rtcGateway.setCameraEnabled(cameraEnabled.value);
  } catch (err) {
    console.warn("[RTC] failed to restore camera state", err);
  }
  if (candidateVideoMount.value) rtcGateway.playLocalVideo(candidateVideoMount.value);
}

async function recoverRtcConnection(options: { trigger: string; forceReconnect: boolean; expectedTokenIssue: boolean }): Promise<void> {
  if (loading.value || !session.value || rtcRecoveryInFlight.value) return;
  if (rtcFailureRecoverAttempts.value >= 3 && options.trigger === "connection-state-change") return;
  rtcRecoveryInFlight.value = true;
  try {
    const latest = await fetchLatestRtcJoinInfo();
    if (!latest.join_token) throw new Error("empty join token");
    const uid = Number(latest.uid);
    if (Number.isNaN(uid)) throw new Error("invalid rtc uid");
    const joinParams = {
      appId: String(latest.app_id || ""),
      channel: latest.channel_name,
      token: latest.join_token,
      uid,
    };
    const canRenewInPlace = !options.forceReconnect && Boolean(joinParams.appId && joinParams.channel);
    if (canRenewInPlace) {
      await rtcGateway.renewToken(joinParams.token);
    } else {
      await rtcGateway.disconnect();
      await rtcGateway.connect(joinParams);
      await restoreLocalMediaState();
    }
    rtcFailureRecoverAttempts.value = 0;
    errorText.value = "";
    transportStatus.value = canRenewInPlace ? "Agora Token 已自动续期" : "Agora 已自动重连";
    console.info("[RTC] recovery succeeded", { trigger: options.trigger, mode: canRenewInPlace ? "renew" : "reconnect" });
  } catch (err: any) {
    const message = err?.message || "RTC token refresh failed";
    errorText.value = `RTC 自动恢复失败（${rtcFailureRecoverAttempts.value}）：${message}`;
    console.error("[RTC] recovery failed", { trigger: options.trigger, expectedTokenIssue: options.expectedTokenIssue, err });
  } finally {
    rtcRecoveryInFlight.value = false;
  }
}

function parseOccurredAtMs(input?: string | null): number | null {
  if (!input) return null;
  const parsed = new Date(input);
  return Number.isNaN(parsed.getTime()) ? null : parsed.getTime();
}

function formatTimelineSecond(value: number): string {
  const safe = Math.max(0, Math.floor(value));
  const mins = Math.floor(safe / 60).toString().padStart(2, "0");
  const secs = Math.floor(safe % 60).toString().padStart(2, "0");
  return `${mins}:${secs}`;
}

function formatTimelineRange(startSecond: number, endSecond: number): string {
  const start = formatTimelineSecond(startSecond);
  const end = formatTimelineSecond(endSecond);
  return start === end ? start : `${start}-${end}`;
}

function resolveTimelineSecond(input?: string | null): number {
  const occurredAtMs = parseOccurredAtMs(input);
  if (occurredAtMs != null) {
    if (timelineBaseEpochMs.value == null) timelineBaseEpochMs.value = occurredAtMs;
    return Math.max(0, Math.round((occurredAtMs - timelineBaseEpochMs.value) / 1000));
  }
  return elapsedSeconds.value;
}

function normalizeSpeaker(raw?: string | null): string {
  const value = String(raw || "").trim();
  const lower = value.toLowerCase();
  if (!value) return "候选人";
  if (
    lower === "ai" ||
    lower.includes("assistant") ||
    lower.includes("bot") ||
    lower.includes("agent") ||
    lower.includes("interviewer") ||
    value.includes("面试官")
  ) return "面试官";
  if (lower.includes("system") || value.includes("系统")) return "系统";
  if (value.includes("候选人")) return "候选人";
  return "候选人";
}

function persistSessionSnapshot(value: InterviewSession | null): void {
  if (!value) {
    window.localStorage.removeItem(SESSION_STORAGE_KEY);
  } else {
    window.localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(value));
  }
}

function loadSessionSnapshot(): InterviewSession | null {
  try {
    const raw = window.localStorage.getItem(SESSION_STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    window.localStorage.removeItem(SESSION_STORAGE_KEY);
    return null;
  }
}

function readPreferredSessionId(): string {
  const url = new URL(window.location.href);
  const fromQuery = String(url.searchParams.get("session_id") || "").trim();
  if (fromQuery) return fromQuery;
  const pathParts = url.pathname.split("/");
  const interviewIdx = pathParts.indexOf("interview");
  if (interviewIdx !== -1 && pathParts[interviewIdx + 1] && pathParts[interviewIdx + 1] !== "invitation") {
    return pathParts[interviewIdx + 1].trim();
  }
  const sessionIdx = pathParts.indexOf("session");
  if (sessionIdx !== -1 && pathParts[sessionIdx + 1]) return pathParts[sessionIdx + 1].trim();
  return "";
}

function isTranscriptOverlap(left: string, right: string): boolean {
  const a = left.trim();
  const b = right.trim();
  return Boolean(a && b && (a === b || a.includes(b) || b.includes(a)));
}

function mergeTranscriptFragment(baseText: string, incomingText: string): string {
  const base = String(baseText || "").trim();
  const incoming = String(incomingText || "").trim();
  if (!base) return incoming;
  if (!incoming) return base;
  if (base === incoming || base.includes(incoming)) return base;
  if (incoming.includes(base)) return incoming;

  const overlapMax = Math.min(base.length, incoming.length);
  for (let size = overlapMax; size >= 2; size -= 1) {
    if (base.slice(-size) === incoming.slice(0, size)) {
      return `${base}${incoming.slice(size)}`;
    }
  }

  return `${base} ${incoming}`.trim();
}

function appendCandidateDraftFragment(fragment: string, occurredAt = ""): void {
  const text = String(fragment || "").trim();
  if (!text) return;
  candidateDraft.value = mergeTranscriptFragment(candidateDraft.value, text);
  if (!candidateDraftOccurredAt.value && occurredAt) {
    candidateDraftOccurredAt.value = occurredAt;
  }
}

function rememberRealtimeEvent(eventType: string, payload: Record<string, any>, event: InterviewRealtimeEvent): boolean {
  // TEMP: disable dedup to diagnose missing transcript fragments.
  // return false means "do not filter this event as duplicate".
  return false;

  /*
  // 1. 优先使用明确的 event_id（最可靠的去重依据）
  const explicitId = String(payload.event_id || (event as any).event_id || "").trim();
  if (explicitId) {
    if (seenRealtimeEventIds.has(explicitId)) return true;
    seenRealtimeEventIds.add(explicitId);
    _boundSeenEventIds();
    return false;
  }
  
  // 2. 对于 ASR 转写事件，使用结构化 ID 去重（避免使用文本内容）
  if (eventType === "asr.turn" || eventType === "candidate.final" || eventType === "candidate.partial") {
    const turnId = String(payload.turn_id || "").trim();
    const seq = String(payload.seq || "").trim();
    const ts = String((event as any).ts || payload.ts || "").trim();
    const isFinal = Boolean(payload.is_final);
    
    // 使用 turn_id 作为主要去重键
    if (turnId) {
      const key = `${eventType}|turn|${turnId}|${isFinal ? "final" : "partial"}`;
      if (seenRealtimeEventIds.has(key)) return true;
      seenRealtimeEventIds.add(key);
      _boundSeenEventIds();
      return false;
    }
    
    // 使用 seq + ts 作为备用去重键
    if (seq && ts) {
      const key = `${eventType}|seq|${seq}|${ts}|${isFinal ? "final" : "partial"}`;
      if (seenRealtimeEventIds.has(key)) return true;
      seenRealtimeEventIds.add(key);
      _boundSeenEventIds();
      return false;
    }
    
    // 如果没有结构化 ID，不去重（宁可重复显示也不要丢失内容）
    console.warn(`[Dedupe] ASR event without structured ID, allowing through:`, eventType, payload);
    return false;
  }
  
  // 3. 对于问题更新事件，使用 trace_id 或 question_id
  if (eventType === "question.update" || eventType === "question.final") {
    const traceId = String(payload.trace_id || "").trim();
    const questionId = String(payload.question_id || "").trim();
    const ts = String((event as any).ts || payload.ts || "").trim();
    
    if (traceId && ts) {
      const key = `${eventType}|trace|${traceId}|${ts}`;
      if (seenRealtimeEventIds.has(key)) return true;
      seenRealtimeEventIds.add(key);
      _boundSeenEventIds();
      return false;
    }
    
    if (questionId && ts) {
      const key = `${eventType}|question|${questionId}|${ts}`;
      if (seenRealtimeEventIds.has(key)) return true;
      seenRealtimeEventIds.add(key);
      _boundSeenEventIds();
      return false;
    }
    
    return false;
  }
  
  // 4. 对于状态事件，使用 state + ts
  if (eventType === "agent.state") {
    const state = String(payload.state || "").trim();
    const ts = String((event as any).ts || payload.ts || "").trim();
    
    if (state && ts) {
      const key = `${eventType}|${state}|${ts}`;
      if (seenRealtimeEventIds.has(key)) return true;
      seenRealtimeEventIds.add(key);
      _boundSeenEventIds();
      return false;
    }
    
    return false;
  }
  
  // 5. 对于 session.event，使用 occurred_at + speaker + transcript 的组合
  if (eventType === "session.event") {
    const occurredAt = String(payload.occurred_at || "").trim();
    const speaker = String(payload.speaker || "").trim();
    const transcript = String(payload.transcript || "").trim();
    
    if (occurredAt && speaker && transcript) {
      // 使用 transcript 的前 50 个字符作为指纹（避免完整文本）
      const textFingerprint = transcript.substring(0, 50);
      const key = `${eventType}|${occurredAt}|${speaker}|${textFingerprint}`;
      if (seenRealtimeEventIds.has(key)) return true;
      seenRealtimeEventIds.add(key);
      _boundSeenEventIds();
      return false;
    }
    
    return false;
  }
  
  // 6. 其他事件类型：使用通用的 ts + 任意可用 ID
  const ts = String((event as any).ts || payload.ts || "").trim();
  const anyId = String(
    payload.trace_id || 
    payload.chunk_index || 
    payload.question_id || 
    ""
  ).trim();
  
  if (ts && anyId) {
    const key = `${eventType}|${ts}|${anyId}`;
    if (seenRealtimeEventIds.has(key)) return true;
    seenRealtimeEventIds.add(key);
    _boundSeenEventIds();
    return false;
  }
  
  // 没有足够的信息去重，让事件通过
  return false;
  */
}

function _boundSeenEventIds(): void {
  // Keep memory bounded for long sessions.
  if (seenRealtimeEventIds.size > 4000) {
    const first = seenRealtimeEventIds.values().next().value as string | undefined;
    if (first) seenRealtimeEventIds.delete(first);
  }
}

function normalizeTranscriptFingerprint(input: string): string {
  return String(input || "")
    .trim()
    .replace(/[，。！？、,.!?\s]+/g, "")
    .toLowerCase();
}

function rememberAsrFinalForDedup(text: string): void {
  const fp = normalizeTranscriptFingerprint(text);
  if (!fp) return;
  const now = Date.now();
  recentAsrFinalMap.set(fp, now);
  if (recentAsrFinalMap.size > 256) {
    const cutoff = now - 8000;
    for (const [key, ts] of recentAsrFinalMap.entries()) {
      if (ts < cutoff) recentAsrFinalMap.delete(key);
    }
  }
}

function shouldSkipCandidateFinalAsDuplicate(text: string): boolean {
  const fp = normalizeTranscriptFingerprint(text);
  if (!fp) return false;
  const seenAt = recentAsrFinalMap.get(fp);
  if (!seenAt) return false;
  return Date.now() - seenAt <= 8000;
}

function clearCandidateDraftFallbackTimer(): void {
  if (candidateDraftFallbackTimer != null) {
    window.clearTimeout(candidateDraftFallbackTimer);
    candidateDraftFallbackTimer = null;
  }
}

function appendTranscript(
  transcript: string,
  speaker = "候选人",
  occurredAt?: string | null,
  kind: TimelineItem["kind"] = "confirmed",
  options: AppendTranscriptOptions = {}
): void {
  const text = transcript.trim();
  if (!text) return;
  const forceSeparate = Boolean(options.forceSeparate);
  const normalizedSpeaker = normalizeSpeaker(speaker);
  const timelineSecond = resolveTimelineSecond(occurredAt);
  const lastItem = transcriptView.value[transcriptView.value.length - 1];
  if (
    lastItem &&
    lastItem.speaker === normalizedSpeaker &&
    lastItem.kind === "draft_fallback" &&
    timelineSecond - lastItem.endSecond <= TRANSCRIPT_MERGE_WINDOW_SECONDS &&
    isTranscriptOverlap(lastItem.transcript, text)
  ) {
    transcriptView.value = [
      ...transcriptView.value.slice(0, -1),
      { ...lastItem, transcript: text, endSecond: Math.max(lastItem.endSecond, timelineSecond), kind },
    ];
    return;
  }
  if (!forceSeparate && lastItem && lastItem.speaker === normalizedSpeaker && timelineSecond - lastItem.endSecond <= TRANSCRIPT_MERGE_WINDOW_SECONDS) {
    const isExactDuplicate = lastItem.transcript.trim() === text;
    if (isExactDuplicate) return;
    const mergedText = [lastItem.transcript, text]
      .map((item) => String(item || "").trim())
      .filter(Boolean)
      .join("，");
    transcriptView.value = [...transcriptView.value.slice(0, -1), { ...lastItem, transcript: mergedText, endSecond: Math.max(lastItem.endSecond, timelineSecond), kind }];
    return;
  }
  transcriptView.value = [...transcriptView.value, { speaker: normalizedSpeaker, transcript: text, startSecond: timelineSecond, endSecond: timelineSecond, kind }];
}

function commitCandidateDraftToTranscript(kind: TimelineItem["kind"] = "draft_fallback"): void {
  const text = candidateDraft.value.trim();
  if (!text) return;
  appendTranscript(text, "候选人", candidateDraftOccurredAt.value, kind);
  candidateDraft.value = "";
  candidateDraftOccurredAt.value = "";
  clearCandidateDraftFallbackTimer();
}

function scheduleCandidateDraftFallback(): void {
  clearCandidateDraftFallbackTimer();
  if (!candidateDraft.value.trim()) return;
  candidateDraftFallbackTimer = window.setTimeout(() => {
    commitCandidateDraftToTranscript("draft_fallback");
  }, CANDIDATE_DRAFT_FALLBACK_MS);
}

function hydrateReplay(items: ReplayItem[]): void {
  timelineBaseEpochMs.value = parseOccurredAtMs(items[0]?.occurred_at || "") ?? null;
  transcriptView.value = [];
  seenReplayTurnIds.clear();
  seenRealtimeEventIds.clear();
  items.filter((item) => item.transcript).forEach((item) => {
    if (item.turn_id) seenReplayTurnIds.add(item.turn_id);
    appendTranscript(item.transcript!, item.speaker, item.occurred_at);
  });
}

function mergeReplay(items: ReplayItem[]): void {
  for (const item of items) {
    if (!item.transcript) continue;
    const turnId = String(item.turn_id || "").trim();
    if (turnId && seenReplayTurnIds.has(turnId)) continue;
    if (turnId) seenReplayTurnIds.add(turnId);
    appendTranscript(item.transcript, item.speaker, item.occurred_at);
  }
}

async function scrollTranscriptToLatest(): Promise<void> {
  await nextTick();
  if (!transcriptScrollRef.value || !isTranscriptPinnedToLatest.value) return;
  transcriptScrollRef.value.scrollTop = transcriptScrollRef.value.scrollHeight;
  updateTranscriptScrollState();
}

function updateTranscriptScrollState(): void {
  const container = transcriptScrollRef.value;
  if (!container) return;
  canScrollTranscriptUp.value = container.scrollTop > 8;
  const distanceToBottom = container.scrollHeight - container.clientHeight - container.scrollTop;
  isTranscriptPinnedToLatest.value = distanceToBottom <= 24;
}

function handleTranscriptScroll(): void {
  updateTranscriptScrollState();
}

function revealPreviousTranscriptChunk(): void {
  const container = transcriptScrollRef.value;
  if (!container) return;
  container.scrollBy({ top: -Math.max(container.clientHeight * 0.72, 220), behavior: "smooth" });
}

function jumpTranscriptToLatest(): void {
  const container = transcriptScrollRef.value;
  if (!container) return;
  isTranscriptPinnedToLatest.value = true;
  container.scrollTo({ top: container.scrollHeight, behavior: "smooth" });
}

async function connectEventBus(sessionIdValue: string): Promise<void> {
  eventsSocket?.close();
  const ws = new WebSocket(buildInterviewEventsWsUrl(sessionIdValue));
  eventsSocket = ws;
  ws.onmessage = (event) => {
    const parsed = JSON.parse(event.data) as InterviewRealtimeEvent;
    // Events from the simple /events/ws bus come with top-level event_type
    // Events bridged from TEN duplex bus wrap the payload under a nested key
    const eventType = parsed.event_type;
    const rawPayload = parsed.payload || (parsed as any).data || {};
    const payload = (rawPayload && typeof rawPayload === "object" ? rawPayload : {}) as Record<string, any>;
    if (eventType === "connected" || eventType === "ping") return;
    if (rememberRealtimeEvent(eventType, payload, parsed)) return;

    // --- TEN / Aliyun ASR transcript ---
    if (eventType === "asr.turn") {
        const isFinal = Boolean(payload.is_final);
        const text = String(payload.transcript || payload.text || "").trim();
        if (!isFinal) {
            // partial - show as draft
            if (text) {
                appendCandidateDraftFragment(text, String(payload.occurred_at || ""));
                scheduleCandidateDraftFallback();
            }
        } else {
            // final - commit to transcript
            if (text) {
                clearCandidateDraftFallbackTimer();
                const mergedFinal = mergeTranscriptFragment(candidateDraft.value, text);
                appendTranscript(mergedFinal, "候选人", String(payload.occurred_at || ""), "confirmed", { forceSeparate: true });
                rememberAsrFinalForDedup(mergedFinal);
                candidateDraft.value = "";
                candidateDraftOccurredAt.value = "";
            }
        }
        return;
    }

    // --- Interviewer question / followup published as session.event ---
    if (eventType === "session.event") {
        if (normalizeSpeaker(String(payload.speaker || "")) !== "候选人") commitCandidateDraftToTranscript("draft_fallback");
        const transcript = String(payload.transcript || "").trim();
        const speaker = String(payload.speaker || "候选人");
        if (transcript) appendTranscript(transcript, speaker, String(payload.occurred_at || ""));
        const next = String(payload.followup_question || payload.question || "").trim();
        if (next) { followupQuestion.value = next; currentQuestion.value = next; }
        return;
    }

    if (eventType === "agent.state") {
        const state = String(payload.state || "").toLowerCase();
        if (state === "thinking" || state === "speaking") commitCandidateDraftToTranscript("draft_fallback");
        if (state === "listening") ttsStatus.value = "面试官正在倾听";
        else if (state === "thinking") ttsStatus.value = "面试官正在思考";
        else if (state === "speaking") ttsStatus.value = "面试官正在发言";
        return;
    }
    if (eventType === "question.update" || eventType === "question.final") {
        commitCandidateDraftToTranscript("draft_fallback");
        const text = String(payload.text || payload.spoken_text || "");
        if (text) { followupQuestion.value = ""; currentQuestion.value = text; }
        return;
    }
    if (eventType === "candidate.partial") {
        appendCandidateDraftFragment(String(payload.text || ""), String(payload.occurred_at || ""));
        scheduleCandidateDraftFallback();
        return;
    }
    if (eventType === "candidate.final") {
        const text = String(payload.text || payload.transcript || "");
        if (text) {
            if (shouldSkipCandidateFinalAsDuplicate(text)) {
                candidateDraft.value = "";
                candidateDraftOccurredAt.value = "";
                return;
            }
            clearCandidateDraftFallbackTimer();
            const mergedFinal = mergeTranscriptFragment(candidateDraft.value, text);
            appendTranscript(mergedFinal, "候选人", String(payload.occurred_at || ""), "confirmed", { forceSeparate: true });
            candidateDraft.value = "";
            candidateDraftOccurredAt.value = "";
        }
        return;
    }
  };
}

async function ensureTenLaunchCommand(sessionIdValue: string): Promise<void> {
  const publishCommand = (command: string, source: string): void => {
    tenLaunchCommand.value = command;
    (window as any).__TEN_LAUNCH_COMMAND__ = command;
    (window as any).__TEN_LAUNCH_COMMAND_SOURCE__ = source;
    console.warn(`[TEN] launch command (${source}) for session ${sessionIdValue}:`);
    console.warn(command);
  };
  try {
    const runtime = await getTenRuntimeConfig(sessionIdValue);
    if (runtime.launch_command) {
      publishCommand(runtime.launch_command, "runtime-config");
      return;
    }
    if (!runtime.enabled) return;

    const launched = await launchTenSession(sessionIdValue);
    if (launched.launch_command) {
      publishCommand(launched.launch_command, "launch-session");
    }
  } catch (err) {
    console.warn(`[TEN] failed to fetch launch command for session ${sessionIdValue}`, err);
  }
}

async function toggleMic(): Promise<void> {
  const next = !micEnabled.value;
  try {
    await rtcGateway.setMicrophoneEnabled(next);
    micEnabled.value = next;
    micStatus.value = next ? "候选人音频已接入" : "候选人已静音";
  } catch (err: any) {
    errorText.value = err?.message || "Failed to toggle microphone";
  }
}

async function toggleCamera(): Promise<void> {
  const next = !cameraEnabled.value;
  try {
    await rtcGateway.setCameraEnabled(next);
    cameraEnabled.value = next;
  } catch (err: any) {
    errorText.value = err?.message || "Failed to toggle camera";
  }
}

async function bootstrap(): Promise<void> {
  loading.value = true;
  try {
    const preferredId = readPreferredSessionId();
    if (preferredId) {
        session.value = await getInterviewSession(preferredId);
    } else {
        session.value = await bootstrapDemoSession();
    }
    
    // Check session status
    if (session.value!.status === "completed" || session.value!.status === "failed" || session.value!.status === "cancelled") {
        errorText.value = "此面试已结束，无法重新加入。请联系管理员获取新的面试邀请。";
        interviewEnded.value = true;
        loading.value = false;
        
        // Still load history for viewing
        try {
            const replay = await loadReplayItems(session.value!.id);
            hydrateReplay(replay);
        } catch (err) {
            console.warn("Failed to load replay items:", err);
        }
        return;
    }
    
    const rtc = await joinInterviewRTC(session.value!.id, session.value!.candidate_id, RTC_CLIENT_ID);
    await rtcGateway.connect({ appId: rtc.app_id!, channel: rtc.channel_name, token: rtc.join_token, uid: Number(rtc.uid) });
    await ensureTenLaunchCommand(session.value!.id);
    if (candidateVideoMount.value) rtcGateway.playLocalVideo(candidateVideoMount.value);
    const replay = await loadReplayItems(session.value!.id);
    hydrateReplay(replay);
    isTranscriptPinnedToLatest.value = true;
    await connectEventBus(session.value!.id);
    // Close replay->WS subscription race window.
    const replayAfterWs = await loadReplayItems(session.value!.id);
    mergeReplay(replayAfterWs);
    tickerTimer = window.setInterval(() => { elapsedSeconds.value += 1; const mins = Math.floor(elapsedSeconds.value / 60).toString().padStart(2, "0"); const secs = Math.floor(elapsedSeconds.value % 60).toString().padStart(2, "0"); meetingTimeText.value = `${mins}:${secs}`; }, 1000);
  } catch (err: any) {
    errorText.value = err.message;
  } finally {
    loading.value = false;
  }
}

function teardownRealtimeConnections(): void {
  if (tickerTimer) {
    clearInterval(tickerTimer);
    tickerTimer = null;
  }
  clearCandidateDraftFallbackTimer();
  eventsSocket?.close();
  eventsSocket = null;
  rtcGateway.disconnect();
}

async function handleEndInterview(): Promise<void> {
  if (exiting.value || interviewEnded.value) return;
  if (!session.value?.id) {
    teardownRealtimeConnections();
    interviewEnded.value = true;
    return;
  }
  exiting.value = true;
  errorText.value = "";
  try {
    const latest = await finishInterviewSession(session.value.id, { result_status: "completed" });
    session.value = latest;
    interviewEnded.value = true;
    transportStatus.value = "面试已结束";
    ttsStatus.value = "面试官已离线";
    micStatus.value = "会话已关闭";
    persistSessionSnapshot(null);
    teardownRealtimeConnections();
  } catch (err: any) {
    errorText.value = err?.message || "结束面试失败，请稍后重试";
  } finally {
    exiting.value = false;
  }
}

onMounted(() => bootstrap());
onBeforeUnmount(() => { teardownRealtimeConnections(); });
watch([() => transcriptView.value.length, () => candidateDraft.value], () => scrollTranscriptToLatest());
</script>

<template>
  <div class="meeting-shell bg-slate-50 h-screen overflow-hidden flex flex-col font-sans">
    <header class="h-16 bg-white border-b px-8 flex items-center justify-between shrink-0">
      <div class="flex items-center gap-4">
        <span class="font-bold text-slate-900">AI 智能面试</span>
        <div class="w-px h-4 bg-slate-200"></div>
        <span class="text-slate-500 text-sm">{{ roleTitle }}</span>
      </div>
      <div class="flex items-center gap-6">
        <div class="flex items-center gap-2 text-slate-500 text-sm">
          <span>⏱</span>
          <span class="font-mono">{{ meetingTimeText }}</span>
        </div>
        <div class="flex items-center gap-2 px-3 py-1 bg-green-50 text-green-700 rounded-full text-xs font-medium">
          <span class="w-1.5 h-1.5 bg-green-500 rounded-full"></span>
          <span>{{ networkTone.text }}</span>
        </div>
        <button class="px-4 py-2 bg-red-50 text-red-600 rounded-lg text-sm font-bold hover:bg-red-100 transition-colors disabled:cursor-not-allowed disabled:opacity-60" :disabled="loading || exiting || interviewEnded" @click="handleEndInterview">
          {{ exiting ? "结束中..." : interviewEnded ? "已结束" : "结束面试" }}
        </button>
      </div>
    </header>

    <main class="flex-1 min-h-0 flex overflow-hidden">
      <section class="flex-1 min-h-0 p-8 overflow-hidden flex flex-col">
        <div class="flex-1 bg-slate-900 rounded-2xl relative overflow-hidden ring-1 ring-slate-800 shadow-2xl">
          <div ref="candidateVideoMount" class="w-full h-full object-cover"></div>
          <div v-if="loading" class="absolute inset-0 flex items-center justify-center bg-slate-900/90 text-white flex-col gap-4">
            <div class="w-10 h-10 border-4 border-blue-500 border-t-transparent rounded-full animate-spin"></div>
            <p class="text-sm font-medium">正在建立面试空间...</p>
          </div>
          <div v-if="!loading && !errorText" class="absolute top-6 left-6 flex items-center gap-2 bg-slate-900/40 backdrop-blur-md px-3 py-1.5 rounded-full border border-white/10">
            <span class="w-2 h-2 bg-red-500 rounded-full animate-pulse"></span>
            <span class="text-sm text-white font-medium">{{ interviewerBannerText }}</span>
          </div>
          <div class="absolute bottom-6 left-1/2 -translate-x-1/2 flex items-center gap-3">
            <button
              class="w-14 h-14 rounded-full border border-white/20 backdrop-blur-md text-white flex items-center justify-center transition"
              :class="micEnabled ? 'bg-black/40 hover:bg-black/55' : 'bg-red-600/85 hover:bg-red-600'"
              :disabled="loading"
              @click="toggleMic"
              :title="micEnabled ? 'Mute microphone' : 'Unmute microphone'"
            >
              <span class="text-xs font-bold">{{ micEnabled ? '麦克风' : '静音' }}</span>
            </button>
            <button
              class="w-14 h-14 rounded-full border border-white/20 backdrop-blur-md text-white flex items-center justify-center transition"
              :class="cameraEnabled ? 'bg-black/40 hover:bg-black/55' : 'bg-red-600/85 hover:bg-red-600'"
              :disabled="loading"
              @click="toggleCamera"
              :title="cameraEnabled ? 'Turn off camera' : 'Turn on camera'"
            >
              <span class="text-xs font-bold">{{ cameraEnabled ? '摄像头' : '隐藏视频' }}</span>
            </button>
          </div>
        </div>
      </section>

      <aside class="w-[400px] min-h-0 border-l bg-white flex flex-col shrink-0 overflow-hidden">
        <div class="p-6 border-b flex items-center justify-between">
          <h2 class="font-bold text-slate-900">会话纪要</h2>
          <div class="flex items-center gap-1.5 text-[10px] font-bold text-blue-600 bg-blue-50 px-2 py-0.5 rounded uppercase tracking-wider">
            <span class="w-1 h-1 bg-blue-500 rounded-full"></span>
            <span>{{ sessionLabel }}</span>
          </div>
        </div>

        <div class="flex-1 min-h-0 overflow-hidden p-6 flex flex-col gap-8">
          <div class="bg-blue-50/50 rounded-xl p-5 border border-blue-100/50">
             <div class="flex items-center gap-2 mb-3">
               <span class="text-sm font-bold text-blue-600 uppercase tracking-widest">当前问题</span>
             </div>
             <p class="text-base font-medium text-slate-900 leading-8">{{ currentQuestion }}</p>
          </div>

          <div class="flex-1 min-h-0 overflow-hidden flex flex-col">
            <div class="flex items-center gap-2 text-slate-400">
               <span class="text-sm font-bold uppercase tracking-widest">实时记录</span>
            </div>
            
            <div ref="transcriptScrollRef" class="flex-1 min-h-0 overflow-y-auto pt-2 pr-1" @scroll="handleTranscriptScroll">
              <div
                v-if="canScrollTranscriptUp"
                class="sticky top-0 z-10 -mx-1 mb-3 px-1 pt-1 pb-2 bg-gradient-to-b from-white via-white to-white/0"
              >
                <button
                  type="button"
                  class="w-full rounded-xl border border-slate-200 bg-white/95 px-3 py-2.5 text-sm font-semibold text-slate-600 shadow-sm transition hover:border-slate-300 hover:text-slate-900"
                  @click="revealPreviousTranscriptChunk"
                >
                  查看更早记录
                </button>
              </div>

              <div class="space-y-6">
                <article v-for="(item, idx) in transcriptView" :key="idx" class="space-y-1.5">
                <div class="flex items-center gap-2 text-xs font-medium text-slate-400 uppercase tracking-wider">
                  <span>{{ formatTimelineRange(item.startSecond, item.endSecond) }}</span>
                  <span>路</span>
                  <span>{{ item.speaker }}</span>
                </div>
                <p class="text-base text-slate-700 leading-8 whitespace-pre-wrap break-words">{{ item.transcript }}</p>
              </article>
                <article v-if="candidateDraft" class="space-y-1.5 opacity-50">
                <div class="flex items-center gap-2 text-xs font-medium text-slate-400 uppercase tracking-wider">
                  <span>{{ meetingTimeText }}</span>
                  <span>路</span>
                  <span>候选人</span>
                </div>
                <p class="text-base text-slate-700 leading-8 italic whitespace-pre-wrap break-words">{{ candidateDraft }}</p>
                </article>
              </div>

              <div
                v-if="!isTranscriptPinnedToLatest"
                class="sticky bottom-0 z-10 -mx-1 mt-3 px-1 pt-2 pb-1 bg-gradient-to-t from-white via-white to-white/0"
              >
                <button
                  type="button"
                  class="w-full rounded-xl border border-blue-200 bg-blue-50/95 px-3 py-2.5 text-sm font-semibold text-blue-700 shadow-sm transition hover:border-blue-300 hover:bg-blue-100"
                  @click="jumpTranscriptToLatest"
                >
                  回到最新记录
                </button>
              </div>
            </div>
          </div>
        </div>
      </aside>
    </main>
  </div>
</template>

<style scoped>
/* Simplified layout styles, Tailwind handles most */
</style>




