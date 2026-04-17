<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { AgoraRTCGateway } from "../../agoraGateway";
import {
  bootstrapDemoSession,
  buildInterviewEventsWsUrl,
  createInterviewSession,
  finalizeInterviewTurn,
  finishInterviewSession,
  getInterviewSession,
  getTenRuntimeConfig,
  joinInterviewRTC,
  joinInterviewRTCPreflight,
  launchTenSession,
  loadReplayItems,
  startInterviewSession,
  type InterviewRealtimeEvent,
  type InterviewSession,
  type ReplayItem
} from "../../api";

interface TimelineItem {
  speaker: string;
  transcript: string;
  startSecond: number;
  endSecond: number;
}

const TRANSCRIPT_MERGE_WINDOW_SECONDS = 12;

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
const candidateVideoMount = ref<HTMLElement | null>(null);
const summaryScrollRef = ref<HTMLElement | null>(null);

const session = ref<InterviewSession | null>(null);
const sessionId = computed(() => session.value?.id || "");

const micStatus = ref("等待初始化");
const ttsStatus = ref("等待面试官接入");
const currentQuestion = ref("正在准备面试链路...");
const followupQuestion = ref("");
const transportStatus = ref("未连接");
const transcriptView = ref<TimelineItem[]>([]);
const candidateDraft = ref("");
const timelineBaseEpochMs = ref<number | null>(null);
const tenLaunchCommand = ref("");
const audioRecoveryHint = ref("");
const tenPendingHint = ref("");
const finalizing = ref(false);

let tickerTimer: number | null = null;
let eventsSocket: WebSocket | null = null;

const roleTitle = computed(() => "后端开发工程师面试");
const sessionLabel = computed(() => (loading.value ? "正在建立链路" : "实时技术面试"));
const networkTone = computed(() => {
  const status = transportStatus.value;
  if (status.includes("已连接")) {
    return { text: "网络优秀", state: "good" };
  }
  if (status.includes("连接中") || status.includes("重连中") || status.includes("接入")) {
    return { text: "连接中", state: "pending" };
  }
  if (status.includes("异常") || status.includes("断开") || status.includes("失败")) {
    return { text: "连接异常", state: "bad" };
  }
  return { text: "等待连接", state: "idle" };
});

const interviewerBannerText = computed(() => {
  if (interviewerSpeaking.value) {
    return "面试官正在发问";
  }
  if (ttsStatus.value.includes("播报")) {
    return "面试官正在发问";
  }
  if (ttsStatus.value.includes("等待") || ttsStatus.value.includes("就绪")) {
    return "面试官正在聆听";
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
      ttsStatus.value = "面试官正在发问";
    } else if (ttsStatus.value.includes("播报") || ttsStatus.value.includes("音频")) {
      ttsStatus.value = "面试官正在聆听";
    }
  },
  onConnectionStateChanged(state, reason) {
    transportStatus.value = formatTransportStatus(state, reason);
    if (state === "CONNECTED") {
      micStatus.value = micEnabled.value ? "候选人音频已接入" : "候选人已静音";
      errorText.value = "";
    }
  },
  onRemoteAudioPlaybackError(message) {
    ttsStatus.value = "面试官音频待浏览器放行";
    audioRecoveryHint.value = message || "浏览器阻止了自动播报，请点击“开启声音”后重试。";
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
  return reasonText ? `${stateText}（${reasonText}）` : stateText;
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
  if (!value) return "候选人";
  if (value.includes("assistant") || value.includes("agent") || value.includes("interviewer") || value.includes("面试官")) return "面试官";
  if (value.includes("system") || value.includes("系统")) return "系统";
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

function appendTranscript(transcript: string, speaker = "候选人", occurredAt?: string): void {
  const text = transcript.trim();
  if (!text) return;
  const normalizedSpeaker = normalizeSpeaker(speaker);
  const timelineSecond = resolveTimelineSecond(occurredAt);
  const lastItem = transcriptView.value[transcriptView.value.length - 1];
  if (lastItem && lastItem.speaker === normalizedSpeaker && timelineSecond - lastItem.endSecond <= TRANSCRIPT_MERGE_WINDOW_SECONDS) {
    if (!lastItem.transcript.includes(text)) {
      const mergedText = [lastItem.transcript, text].filter(Boolean).join("\n");
      transcriptView.value = [...transcriptView.value.slice(0, -1), { ...lastItem, transcript: mergedText, endSecond: Math.max(lastItem.endSecond, timelineSecond) }];
    }
    return;
  }
  transcriptView.value = [...transcriptView.value, { speaker: normalizedSpeaker, transcript: text, startSecond: timelineSecond, endSecond: timelineSecond }];
}

function hydrateReplay(items: ReplayItem[]): void {
  timelineBaseEpochMs.value = parseOccurredAtMs(items[0]?.occurred_at || "") ?? null;
  transcriptView.value = [];
  items.filter((item) => item.transcript).forEach((item) => appendTranscript(item.transcript!, item.speaker, item.occurred_at));
}

async function scrollTranscriptToLatest(): Promise<void> {
  await nextTick();
  if (summaryScrollRef.value) summaryScrollRef.value.scrollTop = summaryScrollRef.value.scrollHeight;
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
    const payload = parsed.payload || (parsed as any).data || {};
    if (eventType === "connected" || eventType === "ping") return;

    // --- TEN / Aliyun ASR transcript ---
    if (eventType === "asr.turn") {
        const isFinal = Boolean(payload.is_final);
        const text = String(payload.transcript || payload.text || "").trim();
        if (!isFinal) {
            // partial — show as draft
            if (text) candidateDraft.value = text;
        } else {
            // final — commit to transcript
            if (text) {
                appendTranscript(text, "候选人", String(payload.occurred_at || ""));
                candidateDraft.value = "";
            }
        }
        return;
    }

    // --- Interviewer question / followup published as session.event ---
    if (eventType === "session.event") {
        const transcript = String(payload.transcript || "").trim();
        const speaker = String(payload.speaker || "候选人");
        if (transcript) appendTranscript(transcript, speaker, String(payload.occurred_at || ""));
        const next = String(payload.followup_question || payload.question || "").trim();
        if (next) { followupQuestion.value = next; currentQuestion.value = next; }
        return;
    }

    if (eventType === "agent.state") {
        const state = String(payload.state || "").toLowerCase();
        if (state === "listening") ttsStatus.value = "面试官正在聆听";
        else if (state === "thinking") ttsStatus.value = "面试官正在思考";
        else if (state === "speaking") ttsStatus.value = "面试官正在发问";
        return;
    }
    if (eventType === "question.update" || eventType === "question.final") {
        const text = String(payload.text || payload.spoken_text || "");
        if (text) { followupQuestion.value = ""; currentQuestion.value = text; }
        return;
    }
    if (eventType === "candidate.partial") { candidateDraft.value = String(payload.text || ""); return; }
    if (eventType === "candidate.final") {
        const text = String(payload.text || payload.transcript || "");
        if (text) { appendTranscript(text, "候选人", String(payload.occurred_at || "")); candidateDraft.value = ""; }
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
    errorText.value = err?.message || "切换麦克风失败";
  }
}

async function toggleCamera(): Promise<void> {
  const next = !cameraEnabled.value;
  try {
    await rtcGateway.setCameraEnabled(next);
    cameraEnabled.value = next;
  } catch (err: any) {
    errorText.value = err?.message || "切换摄像头失败";
  }
}

async function handleFinalizeAnswer(): Promise<void> {
  if (finalizing.value || !sessionId.value) return;
  finalizing.value = true;
  try {
    await finalizeInterviewTurn(sessionId.value);
    // Visual feedback handled by ASR event clearing and AI thinking status
  } catch (err: any) {
    console.error("[InterviewRoom] Failed to finalize turn", err);
  } finally {
    finalizing.value = false;
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
    const rtc = await joinInterviewRTC(session.value!.id, session.value!.candidate_id);
    await rtcGateway.connect({ appId: rtc.app_id!, channel: rtc.channel_name, token: rtc.join_token, uid: Number(rtc.uid) });
    await ensureTenLaunchCommand(session.value!.id);
    if (candidateVideoMount.value) rtcGateway.playLocalVideo(candidateVideoMount.value);
    const replay = await loadReplayItems(session.value!.id);
    hydrateReplay(replay);
    await connectEventBus(session.value!.id);
    tickerTimer = window.setInterval(() => { elapsedSeconds.value += 1; const mins = Math.floor(elapsedSeconds.value / 60).toString().padStart(2, "0"); const secs = Math.floor(elapsedSeconds.value % 60).toString().padStart(2, "0"); meetingTimeText.value = `${mins}:${secs}`; }, 1000);
  } catch (err: any) {
    errorText.value = err.message;
  } finally {
    loading.value = false;
  }
}

onMounted(() => bootstrap());
onBeforeUnmount(() => { if (tickerTimer) clearInterval(tickerTimer); eventsSocket?.close(); rtcGateway.disconnect(); });
watch(() => transcriptView.value.length, () => scrollTranscriptToLatest());
</script>

<template>
  <div class="meeting-shell bg-slate-50 min-h-screen flex flex-col font-sans">
    <header class="h-16 bg-white border-b px-8 flex items-center justify-between shrink-0">
      <div class="flex items-center gap-4">
        <span class="font-bold text-slate-900">职位面试中</span>
        <div class="w-px h-4 bg-slate-200"></div>
        <span class="text-slate-500 text-sm">{{ roleTitle }}</span>
      </div>
      <div class="flex items-center gap-6">
        <div class="flex items-center gap-2 text-slate-500 text-sm">
          <span>◷</span>
          <span class="font-mono">{{ meetingTimeText }}</span>
        </div>
        <div class="flex items-center gap-2 px-3 py-1 bg-green-50 text-green-700 rounded-full text-xs font-medium">
          <span class="w-1.5 h-1.5 bg-green-500 rounded-full"></span>
          <span>网络优秀</span>
        </div>
        <button class="px-4 py-2 bg-red-50 text-red-600 rounded-lg text-sm font-bold hover:bg-red-100 transition-colors" @click="exiting = true">退出面试</button>
      </div>
    </header>

    <main class="flex-1 flex overflow-hidden">
      <section class="flex-1 p-8 overflow-hidden flex flex-col">
        <div class="flex-1 bg-slate-900 rounded-2xl relative overflow-hidden ring-1 ring-slate-800 shadow-2xl">
          <div ref="candidateVideoMount" class="w-full h-full object-cover"></div>
          <div v-if="loading" class="absolute inset-0 flex items-center justify-center bg-slate-900/90 text-white flex-col gap-4">
            <div class="w-10 h-10 border-4 border-blue-500 border-t-transparent rounded-full animate-spin"></div>
            <p class="text-sm font-medium">正在建立面试空间...</p>
          </div>
          <div v-if="!loading && !errorText" class="absolute top-6 left-6 flex items-center gap-2 bg-slate-900/40 backdrop-blur-md px-3 py-1.5 rounded-full border border-white/10">
            <span class="w-2 h-2 bg-red-500 rounded-full animate-pulse"></span>
            <span class="text-xs text-white font-medium">{{ interviewerBannerText }}</span>
          </div>
          <div class="absolute bottom-6 left-1/2 -translate-x-1/2 flex items-center gap-3">
            <button
              class="w-12 h-12 rounded-full border border-white/20 backdrop-blur-md text-white flex items-center justify-center transition"
              :class="micEnabled ? 'bg-black/40 hover:bg-black/55' : 'bg-red-600/85 hover:bg-red-600'"
              :disabled="loading"
              @click="toggleMic"
              :title="micEnabled ? '关闭麦克风' : '开启麦克风'"
            >
              <span class="text-[10px] font-bold">{{ micEnabled ? '麦克风' : '静音' }}</span>
            </button>
            <button
              class="w-12 h-12 rounded-full border border-white/20 backdrop-blur-md text-white flex items-center justify-center transition"
              :class="cameraEnabled ? 'bg-black/40 hover:bg-black/55' : 'bg-red-600/85 hover:bg-red-600'"
              :disabled="loading"
              @click="toggleCamera"
              :title="cameraEnabled ? '关闭视频' : '开启视频'"
            >
              <span class="text-[10px] font-bold">{{ cameraEnabled ? '视频' : '关闭' }}</span>
            </button>
            <div class="w-px h-6 bg-white/10 mx-1"></div>
            <button
              class="px-6 h-12 rounded-full bg-blue-600 hover:bg-blue-500 text-white font-bold text-sm shadow-lg shadow-blue-500/20 transition-all active:scale-95 disabled:opacity-50 flex items-center gap-2"
              @click="handleFinalizeAnswer"
              :disabled="loading || finalizing || interviewerSpeaking"
            >
              <span v-if="finalizing" class="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin"></span>
              <span>回答结束</span>
            </button>
          </div>
        </div>
      </section>

      <aside class="w-[400px] border-l bg-white flex flex-col shrink-0">
        <div class="p-6 border-b flex items-center justify-between">
          <h2 class="font-bold text-slate-900">会议纪要</h2>
          <div class="flex items-center gap-1.5 text-[10px] font-bold text-blue-600 bg-blue-50 px-2 py-0.5 rounded uppercase tracking-wider">
            <span class="w-1 h-1 bg-blue-500 rounded-full"></span>
            <span>{{ sessionLabel }}</span>
          </div>
        </div>

        <div ref="summaryScrollRef" class="flex-1 overflow-y-auto p-6 space-y-8">
          <div class="bg-blue-50/50 rounded-xl p-5 border border-blue-100/50">
             <div class="flex items-center gap-2 mb-3">
               <span class="text-blue-600 text-lg">?</span>
               <span class="text-xs font-bold text-blue-600 uppercase tracking-widest">当前问题</span>
             </div>
             <p class="text-sm font-medium text-slate-900 leading-relaxed">{{ currentQuestion }}</p>
          </div>

          <div class="space-y-6">
            <div class="flex items-center gap-2 text-slate-400">
               <span class="text-lg">◌</span>
               <span class="text-xs font-bold uppercase tracking-widest">实时记录</span>
            </div>
            
            <div class="space-y-6 pt-2">
              <article v-for="(item, idx) in transcriptView" :key="idx" class="space-y-1.5">
                <div class="flex items-center gap-2 text-[10px] font-medium text-slate-400 uppercase tracking-wider">
                  <span>{{ formatTimelineRange(item.startSecond, item.endSecond) }}</span>
                  <span>·</span>
                  <span>{{ item.speaker }}</span>
                </div>
                <p class="text-sm text-slate-700 leading-relaxed">{{ item.transcript }}</p>
              </article>
              <article v-if="candidateDraft" class="space-y-1.5 opacity-50">
                <div class="flex items-center gap-2 text-[10px] font-medium text-slate-400 uppercase tracking-wider">
                  <span>{{ meetingTimeText }}</span>
                  <span>·</span>
                  <span>候选人</span>
                </div>
                <p class="text-sm text-slate-700 leading-relaxed italic">{{ candidateDraft }}</p>
              </article>
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
