<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { AgoraRTCGateway } from "./agoraGateway";
import {
  bootstrapDemoSession,
  buildInterviewEventsWsUrl,
  finishInterviewSession,
  getInterviewSession,
  getTenRuntimeConfig,
  joinInterviewRTC,
  launchTenSession,
  loadReplayItems,
  startInterviewSession,
  type InterviewRealtimeEvent,
  type InterviewSession,
  type ReplayItem
} from "./api";

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
const footerHint = computed(() => {
  if (errorText.value) {
    return "当前会话未建立成功，请检查后端服务与 Agora 配置。";
  }
  if (audioRecoveryHint.value) {
    return audioRecoveryHint.value;
  }
  if (tenPendingHint.value) {
    return tenPendingHint.value;
  }
  return "正在自动记录面试内容，请保持自然表达与稳定网络环境。";
});

function formatTenLaunchStatus(status?: string | null): string {
  switch (String(status || "").trim().toLowerCase()) {
    case "manual_ready":
      return "面试官服务待手动启动";
    case "launching":
      return "面试官服务启动中";
    case "launched":
      return "面试官服务已就绪";
    case "failed":
      return "面试官服务启动失败";
    case "disabled":
      return "面试官服务未启用";
    default:
      return status ? `面试官服务状态：${status}` : "面试官服务状态未知";
  }
}

function formatAgoraReason(reason?: string | null): string {
  const value = String(reason || "").trim();
  if (!value) {
    return "";
  }
  const normalized = value.toUpperCase();
  if (normalized === "JOIN_SUCCESS") {
    return "加入成功";
  }
  if (normalized === "INTERRUPTED") {
    return "网络中断";
  }
  if (normalized === "LEAVE_CHANNEL") {
    return "已离开频道";
  }
  if (normalized === "BANNED_BY_SERVER") {
    return "被服务端禁用";
  }
  if (normalized === "KEEP_ALIVE_TIMEOUT") {
    return "心跳超时";
  }
  return value;
}

function formatTransportStatus(state?: string | null, reason?: string | null): string {
  const normalized = String(state || "").trim().toUpperCase();
  const reasonText = formatAgoraReason(reason);
  let stateText = "等待连接";

  switch (normalized) {
    case "CONNECTED":
      stateText = "Agora 已连接";
      break;
    case "CONNECTING":
      stateText = "Agora 连接中";
      break;
    case "RECONNECTING":
      stateText = "Agora 重连中";
      break;
    case "DISCONNECTED":
      stateText = "Agora 已断开";
      break;
    case "DISCONNECTING":
      stateText = "Agora 断开中";
      break;
    case "FAILED":
      stateText = "Agora 连接失败";
      break;
    default:
      if (state) {
        stateText = `Agora 状态：${state}`;
      }
  }

  return reasonText ? `${stateText}（${reasonText}）` : stateText;
}

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

function formatOccurredAt(input?: string | null): string {
  if (!input) {
    return meetingTimeText.value;
  }
  const parsed = new Date(input);
  if (Number.isNaN(parsed.getTime())) {
    return meetingTimeText.value;
  }
  return parsed.toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit"
  });
}

function parseOccurredAtMs(input?: string | null): number | null {
  if (!input) {
    return null;
  }
  const parsed = new Date(input);
  if (Number.isNaN(parsed.getTime())) {
    return null;
  }
  return parsed.getTime();
}

function formatTimelineSecond(value: number): string {
  const safe = Math.max(0, Math.floor(value));
  const mins = Math.floor(safe / 60)
    .toString()
    .padStart(2, "0");
  const secs = Math.floor(safe % 60)
    .toString()
    .padStart(2, "0");
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
    if (timelineBaseEpochMs.value == null) {
      timelineBaseEpochMs.value = occurredAtMs;
    }
    return Math.max(0, Math.round((occurredAtMs - timelineBaseEpochMs.value) / 1000));
  }
  return elapsedSeconds.value;
}

function normalizeSpeaker(raw?: string | null): string {
  const value = String(raw || "").trim();
  if (!value) {
    return "候选人";
  }
  if (value.includes("assistant") || value.includes("agent") || value.includes("interviewer") || value.includes("面试官")) {
    return "面试官";
  }
  if (value.includes("system") || value.includes("系统")) {
    return "系统";
  }
  return "候选人";
}

function persistSessionSnapshot(value: InterviewSession | null): void {
  if (!value) {
    window.localStorage.removeItem(SESSION_STORAGE_KEY);
    return;
  }
  window.localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(value));
}

function loadSessionSnapshot(): InterviewSession | null {
  try {
    const raw = window.localStorage.getItem(SESSION_STORAGE_KEY);
    if (!raw) {
      return null;
    }
    return JSON.parse(raw) as InterviewSession;
  } catch {
    window.localStorage.removeItem(SESSION_STORAGE_KEY);
    return null;
  }
}

function clearSessionSnapshot(): void {
  window.localStorage.removeItem(SESSION_STORAGE_KEY);
}

function readPreferredSessionId(): string {
  const url = new URL(window.location.href);
  return String(url.searchParams.get("session_id") || "").trim();
}

function appendTranscript(transcript: string, speaker = "候选人", occurredAt?: string): void {
  const text = transcript.trim();
  if (!text) {
    return;
  }
  const normalizedSpeaker = normalizeSpeaker(speaker);
  const timelineSecond = resolveTimelineSecond(occurredAt);
  const lastItem = transcriptView.value[transcriptView.value.length - 1];
  if (
    lastItem &&
    lastItem.speaker === normalizedSpeaker &&
    timelineSecond - lastItem.endSecond <= TRANSCRIPT_MERGE_WINDOW_SECONDS
  ) {
    if (!lastItem.transcript.includes(text)) {
      const mergedText = [lastItem.transcript, text].filter(Boolean).join("\n");
      transcriptView.value = [
        ...transcriptView.value.slice(0, -1),
        {
          ...lastItem,
          transcript: mergedText,
          endSecond: Math.max(lastItem.endSecond, timelineSecond)
        }
      ];
    }
    return;
  }
  transcriptView.value = [
    ...transcriptView.value,
    {
      speaker: normalizedSpeaker,
      transcript: text,
      startSecond: timelineSecond,
      endSecond: timelineSecond
    }
  ];
}

function appendCandidateTranscript(transcript: string, occurredAt?: string): void {
  appendTranscript(transcript, "候选人", occurredAt);
  candidateDraft.value = "";
}

function hydrateReplay(items: ReplayItem[]): void {
  timelineBaseEpochMs.value = parseOccurredAtMs(items[0]?.occurred_at || "") ?? null;
  transcriptView.value = [];
  items
    .filter((item) => item.transcript)
    .forEach((item) => {
      appendTranscript(String(item.transcript || ""), item.speaker, item.occurred_at);
    });
}

async function scrollTranscriptToLatest(): Promise<void> {
  await nextTick();
  const container = summaryScrollRef.value;
  if (!container) {
    return;
  }
  container.scrollTop = container.scrollHeight;
}

async function connectEventBus(sessionIdValue: string): Promise<void> {
  eventsSocket?.close();
  const ws = new WebSocket(buildInterviewEventsWsUrl(sessionIdValue));
  eventsSocket = ws;

  ws.onmessage = (event) => {
    const parsed = JSON.parse(event.data) as InterviewRealtimeEvent;
    const payload = parsed.payload || {};
    if (parsed.event_type === "connected") {
      currentQuestion.value = "会话事件总线已连接";
      return;
    }
    if (parsed.event_type === "agent.state") {
      const state = String(payload.state || "").trim().toLowerCase();
      if (state === "listening") {
        ttsStatus.value = "面试官正在聆听";
      } else if (state === "thinking") {
        ttsStatus.value = "面试官正在思考";
      } else if (state === "speaking") {
        ttsStatus.value = "面试官正在发问";
      }
      return;
    }
    if (parsed.event_type === "question.update" || parsed.event_type === "question.final") {
      const questionText = String(payload.text || payload.spoken_text || "");
      if (questionText) {
        followupQuestion.value = "";
        currentQuestion.value = questionText;
      }
      return;
    }
    if (parsed.event_type === "candidate.partial") {
      candidateDraft.value = String(payload.text || "");
      return;
    }
    if (parsed.event_type === "candidate.final") {
      const transcript = String(payload.text || payload.transcript || "");
      const occurredAt = String(payload.occurred_at || "");
      if (transcript) {
        appendCandidateTranscript(transcript, occurredAt);
      }
      return;
    }
    if (parsed.event_type === "session.event") {
      const transcript = String(payload.transcript || "");
      const speaker = String(payload.speaker || "候选人");
      const occurredAt = String(payload.occurred_at || "");
      if (transcript) {
        appendTranscript(transcript, speaker, occurredAt);
      }
      const nextQuestion = String(payload.followup_question || "");
      if (nextQuestion) {
        followupQuestion.value = nextQuestion;
        currentQuestion.value = nextQuestion;
      }
    }
    if (parsed.event_type === "asr.turn") {
      const transcript = String(payload.transcript || "");
      const occurredAt = String(payload.occurred_at || "");
      if (transcript) {
        appendCandidateTranscript(transcript, occurredAt);
      }
      return;
    }
    if (parsed.event_type === "llm.sentence") {
      const sentence = String(payload.sentence || payload.text || payload.transcript || "");
      if (sentence) {
        currentQuestion.value = sentence;
      }
      return;
    }
    if (parsed.event_type === "tts.packet") {
      ttsStatus.value = "面试官正在发问";
    }
  };

  ws.onerror = () => {
    transportStatus.value = "事件总线连接异常";
  };

  ws.onclose = () => {
    if (!exiting.value) {
      transportStatus.value = "事件总线已断开";
    }
  };
}

async function ensureTenReady(sessionIdValue: string): Promise<void> {
  const runtime = await getTenRuntimeConfig(sessionIdValue);
  tenLaunchCommand.value = String(runtime.launch_command || "");
  if (!runtime.enabled) {
    ttsStatus.value = "面试官服务未启用，当前仅验证候选人 RTC 入会";
    return;
  }
  if (runtime.launch_status !== "launched") {
    ttsStatus.value = "正在启动面试官服务...";
    const launched = await launchTenSession(sessionIdValue);
    tenLaunchCommand.value = String(launched.launch_command || tenLaunchCommand.value || "");
    ttsStatus.value = formatTenLaunchStatus(launched.launch_status);
    if (launched.launch_status === "manual_ready") {
      tenPendingHint.value = "面试官服务已切到手动启动模式；如果你已经在 WSL 中启动成功，可以直接继续，页面会在音频接通后自动恢复正常状态。";
      currentQuestion.value = "正在等待面试官服务真正入会...";
    }
    return;
  }
  tenPendingHint.value = "";
  ttsStatus.value = formatTenLaunchStatus(runtime.launch_status);
}

async function bootstrap(): Promise<void> {
  loading.value = true;
  errorText.value = "";
  try {
    const preferredSessionId = readPreferredSessionId();
    const cached = loadSessionSnapshot();
    if (preferredSessionId) {
      session.value = await getInterviewSession(preferredSessionId);
      persistSessionSnapshot(session.value);
      currentQuestion.value = "已按指定会话接入，正在重新接入 Agora/TEN 链路";
    } else if (cached?.id && cached?.candidate_id) {
      session.value = cached;
      currentQuestion.value = "已恢复上一次会话，正在重新接入 Agora/TEN 链路";
    } else {
      const created = await bootstrapDemoSession();
      persistSessionSnapshot(created);
      session.value = await startInterviewSession(created.id);
      persistSessionSnapshot(session.value);
      currentQuestion.value = "会话已创建，正在准备 Agora/TEN 链路";
    }

    const rtc = await joinInterviewRTC(session.value.id, session.value.candidate_id);
    if (rtc.provider !== "agora") {
      throw new Error(`当前 RTC provider 为 ${rtc.provider}，前端 Agora 接入需要后端返回 agora`);
    }
    if (!rtc.app_id || !rtc.uid) {
      throw new Error("后端未返回完整的 Agora app_id/uid");
    }

    if (session.value) {
      session.value = {
        ...session.value,
        rtc: {
          ...session.value.rtc,
          provider: rtc.provider,
          transport: rtc.transport,
          room_id: rtc.room_id,
          channel_name: rtc.channel_name,
          token: rtc.join_token,
          app_id: rtc.app_id,
          uid: rtc.uid,
          expire_at: rtc.expire_at
        },
        rtc_room_id: rtc.room_id
      };
      persistSessionSnapshot(session.value);
    }

    await ensureTenReady(session.value.id);
    await connectEventBus(session.value.id);

    transportStatus.value = "正在接入 Agora";
    await rtcGateway.connect({
      appId: rtc.app_id,
      channel: rtc.channel_name,
      token: rtc.join_token,
      uid: Number(rtc.uid)
    });
    await nextTick();
    if (candidateVideoMount.value) {
      rtcGateway.playLocalVideo(candidateVideoMount.value);
    }

    const replayItems = await loadReplayItems(session.value.id);
    hydrateReplay(replayItems);
    micStatus.value = micEnabled.value ? "候选人音频已接入" : "候选人已静音";
    cameraEnabled.value = true;
    persistSessionSnapshot(session.value);

    tickerTimer = window.setInterval(() => {
      elapsedSeconds.value += 1;
      const mins = Math.floor(elapsedSeconds.value / 60)
        .toString()
        .padStart(2, "0");
      const secs = Math.floor(elapsedSeconds.value % 60)
        .toString()
        .padStart(2, "0");
      meetingTimeText.value = `${mins}:${secs}`;
    }, 1000);
  } catch (err) {
    errorText.value = err instanceof Error ? err.message : "页面初始化失败，无法建立 Agora/TEN 会话";
  } finally {
    loading.value = false;
  }
}

async function toggleMicrophone(): Promise<void> {
  micEnabled.value = !micEnabled.value;
  try {
    await rtcGateway.setMicrophoneEnabled(micEnabled.value);
    micStatus.value = micEnabled.value ? "候选人音频已接入" : "候选人已静音";
  } catch (err) {
    micEnabled.value = !micEnabled.value;
    micStatus.value = err instanceof Error ? err.message : "麦克风切换失败";
  }
}

async function toggleCamera(): Promise<void> {
  const nextEnabled = !cameraEnabled.value;
  cameraEnabled.value = nextEnabled;
  try {
    await rtcGateway.setCameraEnabled(nextEnabled);
  } catch {
    cameraEnabled.value = !nextEnabled;
  }
}

async function unlockAudioPlayback(): Promise<void> {
  audioRecoveryHint.value = "";
  try {
    await rtcGateway.resumeRemoteAudioPlayback();
    ttsStatus.value = "面试官音频重试中";
  } catch (err) {
    audioRecoveryHint.value = err instanceof Error ? err.message : "开启声音失败，请检查浏览器声音权限。";
  }
}

function toggleSettingsHint(): void {
  showSettingsHint.value = !showSettingsHint.value;
  window.setTimeout(() => {
    showSettingsHint.value = false;
  }, 1800);
}

async function exitMeeting(): Promise<void> {
  if (exiting.value) {
    return;
  }
  exiting.value = true;
  try {
    eventsSocket?.close();
    if (sessionId.value) {
      await finishInterviewSession(sessionId.value);
    }
    clearSessionSnapshot();
  } catch {
    // best effort
  } finally {
    await rtcGateway.disconnect();
    window.location.href = "/?left=1";
  }
}

onMounted(() => {
  void bootstrap();
});

watch(
  () => transcriptView.value.length,
  () => {
    void scrollTranscriptToLatest();
  }
);

watch(candidateDraft, () => {
  void scrollTranscriptToLatest();
});

onBeforeUnmount(() => {
  if (tickerTimer != null) {
    window.clearInterval(tickerTimer);
  }
  eventsSocket?.close();
  rtcGateway.stopLocalVideo();
  void rtcGateway.disconnect();
});
</script>

<template>
  <div class="meeting-shell">
    <header class="topbar">
      <div class="topbar-section topbar-brand">
        <span class="topbar-title">职位面试中</span>
        <span class="topbar-divider"></span>
        <span class="topbar-subtitle">{{ roleTitle }}</span>
      </div>

      <div class="topbar-section topbar-meta">
        <div class="topbar-time-group">
          <span class="meta-icon">◷</span>
          <span class="meeting-time">{{ meetingTimeText }}</span>
        </div>
        <div class="network-indicator" :data-state="networkTone.state">
          <span class="network-dot"></span>
          <span>{{ networkTone.text }}</span>
        </div>
      </div>

      <div class="topbar-section topbar-actions">
        <button class="exit-button" :disabled="exiting" @click="exitMeeting">
          {{ exiting ? "正在退出..." : "退出面试" }}
        </button>
      </div>
    </header>

    <main class="meeting-content">
      <section class="video-stage">
        <div class="video-stage-frame">
          <div class="candidate-video-surface">
            <div ref="candidateVideoMount" class="candidate-video-stream" :data-camera-enabled="cameraEnabled"></div>
            <div v-if="!cameraEnabled" class="candidate-video-backdrop"></div>
            <div class="interviewer-window">
              <div class="interviewer-window-label">面试官</div>
            </div>

            <div v-if="!loading && !errorText" class="stage-live-banner">
              <span class="stage-live-dot"></span>
              <span>{{ interviewerBannerText }}</span>
            </div>

            <div v-if="loading" class="stage-state-card">
              <p class="stage-state-title">正在接入面试空间</p>
              <p class="stage-state-text">正在建立 Agora、TEN 与实时事件链路...</p>
            </div>

            <div v-else-if="errorText" class="stage-state-card error">
              <p class="stage-state-title">会话建立失败</p>
              <p class="stage-state-text">{{ errorText }}</p>
            </div>

            <div class="candidate-floating-controls">
              <a href="javascript:void(0)" class="floating-link" @click="toggleMicrophone">{{ micEnabled ? '麦克风开启' : '麦克风关闭' }}</a>
              <a href="javascript:void(0)" class="floating-link" @click="toggleCamera">{{ cameraEnabled ? '视频占位开启' : '视频占位关闭' }}</a>
              <a href="javascript:void(0)" class="floating-link error-link" v-if="audioRecoveryHint" @click="unlockAudioPlayback">开启声音以继续</a>
            </div>
          </div>
        </div>
      </section>

      <aside class="summary-sidebar">
        <div class="summary-header">
          <h2>会议纪要</h2>
          <div class="summary-sync">
            <span class="summary-sync-dot"></span>
            <span>{{ sessionLabel }}</span>
          </div>
        </div>

        <div ref="summaryScrollRef" class="summary-scroll">
          <section class="question-card">
            <div class="question-label-row">
              <span class="question-icon">?</span>
              <span class="question-label">当前问题</span>
            </div>
            <p class="question-text">{{ currentQuestion }}</p>
            <p v-if="followupQuestion" class="followup-text">{{ followupQuestion }}</p>
          </section>

          <section class="transcript-section">
            <div class="transcript-header">
              <span class="transcript-icon">◌</span>
              <span class="transcript-label">实时记录</span>
            </div>

            <div class="transcript-list">
              <article
                v-for="(item, idx) in transcriptView"
                :key="`${idx}-${item.startSecond}-${item.endSecond}-${item.transcript}`"
                class="transcript-item"
              >
                <span class="transcript-time">{{ formatTimelineRange(item.startSecond, item.endSecond) }} · {{ item.speaker }}</span>
                <p class="transcript-text">{{ item.transcript }}</p>
              </article>

              <article v-if="candidateDraft" class="transcript-item">
                <span class="transcript-time">{{ meetingTimeText }} · 候选人</span>
                <p class="transcript-text">{{ candidateDraft }}</p>
              </article>

              <article v-if="transcriptView.length === 0" class="transcript-item empty">
                <span class="transcript-time">{{ meetingTimeText }} · 系统</span>
                <p class="transcript-text">面试开始后，候选人与面试官的关键发言会在这里实时沉淀。</p>
              </article>
            </div>
          </section>
        </div>
      </aside>
    </main>
  </div>
</template>
