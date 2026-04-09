<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from "vue";
import { AgoraRTCGateway } from "./agoraGateway";
import {
  bootstrapDemoSession,
  buildInterviewEventsWsUrl,
  finishInterviewSession,
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
  occurredAt: string;
}

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

const session = ref<InterviewSession | null>(null);
const sessionId = computed(() => session.value?.id || "");

const micStatus = ref("等待初始化");
const ttsStatus = ref("等待 AI 接入");
const currentQuestion = ref("正在准备面试链路...");
const followupQuestion = ref("");
const transportStatus = ref("未连接");
const transcriptView = ref<TimelineItem[]>([]);

let tickerTimer: number | null = null;
let eventsSocket: WebSocket | null = null;

const roleTitle = computed(() => "后端开发工程师面试");
const sessionLabel = computed(() => (loading.value ? "正在建立链路" : "实时技术面试"));
const networkTone = computed(() => {
  const status = transportStatus.value.toUpperCase();
  if (status.includes("CONNECTED")) {
    return { text: "网络优秀", state: "good" };
  }
  if (status.includes("CONNECTING") || transportStatus.value.includes("接入")) {
    return { text: "连接中", state: "pending" };
  }
  if (transportStatus.value.includes("异常") || transportStatus.value.includes("断开")) {
    return { text: "连接异常", state: "bad" };
  }
  return { text: "等待连接", state: "idle" };
});
const candidateStageStatus = computed(() => {
  if (loading.value) {
    return "正在接入音频与面试服务";
  }
  if (errorText.value) {
    return "会话建立失败";
  }
  return micStatus.value;
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
  return "正在自动记录面试内容，请保持自然表达与稳定网络环境。";
});

const rtcGateway = new AgoraRTCGateway({
  onRemoteAudioSubscribed(uid) {
    ttsStatus.value = `AI 已入会并可播放音频 (${uid})`;
    interviewerSpeaking.value = true;
  },
  onRemoteAudioUnsubscribed() {
    ttsStatus.value = "AI 音频已暂停";
    interviewerSpeaking.value = false;
  },
  onConnectionStateChanged(state, reason) {
    transportStatus.value = reason ? `${state} (${reason})` : state;
    if (state === "CONNECTED") {
      micStatus.value = micEnabled.value ? "候选人音频已接入" : "候选人已静音";
    }
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

function appendTranscript(transcript: string, speaker = "候选人", occurredAt?: string): void {
  const text = transcript.trim();
  if (!text) {
    return;
  }
  transcriptView.value = [
    ...transcriptView.value,
    {
      speaker: normalizeSpeaker(speaker),
      transcript: text,
      occurredAt: formatOccurredAt(occurredAt)
    }
  ].slice(-8);
}

function hydrateReplay(items: ReplayItem[]): void {
  transcriptView.value = items
    .filter((item) => item.transcript)
    .map((item) => ({
      speaker: normalizeSpeaker(item.speaker),
      transcript: String(item.transcript || ""),
      occurredAt: formatOccurredAt(item.occurred_at)
    }))
    .slice(-8);
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
    if (parsed.event_type === "tts.packet") {
      ttsStatus.value = "AI 正在播报";
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
  if (!runtime.enabled) {
    ttsStatus.value = "TEN 未启用，当前仅验证候选人 RTC 入会";
    return;
  }
  if (runtime.launch_status !== "launched") {
    ttsStatus.value = "正在拉起 TEN 面试官...";
    const launched = await launchTenSession(sessionIdValue);
    ttsStatus.value =
      launched.launch_status === "launched"
        ? "TEN 已拉起，等待 AI 入会"
        : `TEN 状态: ${launched.launch_status}`;
    return;
  }
  ttsStatus.value = "TEN 已就绪";
}

async function bootstrap(): Promise<void> {
  loading.value = true;
  errorText.value = "";
  try {
    const created = await bootstrapDemoSession();
    session.value = await startInterviewSession(created.id);
    currentQuestion.value = "会话已创建，正在准备 Agora/TEN 链路";

    await ensureTenReady(session.value.id);
    await connectEventBus(session.value.id);

    const rtc = await joinInterviewRTC(session.value.id, session.value.candidate_id);
    if (rtc.provider !== "agora") {
      throw new Error(`当前 RTC provider 为 ${rtc.provider}，前端 Agora 接入需要后端返回 agora`);
    }
    if (!rtc.app_id || !rtc.uid) {
      throw new Error("后端未返回完整的 Agora app_id/uid");
    }

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
            <div class="candidate-video-backdrop"></div>
            <div class="candidate-focus-card">
              <div class="candidate-focus-avatar">候</div>
              <div class="candidate-focus-meta">
                <p class="candidate-focus-name">候选人</p>
                <p class="candidate-focus-status">{{ candidateStageStatus }}</p>
              </div>
            </div>

            <div class="interviewer-window">
              <div class="interviewer-window-avatar">AI</div>
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

        <div class="summary-scroll">
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
                :key="`${idx}-${item.occurredAt}-${item.transcript}`"
                class="transcript-item"
              >
                <span class="transcript-time">{{ item.occurredAt }} · {{ item.speaker }}</span>
                <p class="transcript-text">{{ item.transcript }}</p>
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

    <footer class="control-bar">
      <div class="control-status">
        <span class="control-status-dot"></span>
        <span>{{ footerHint }}</span>
      </div>

      <div class="control-actions">
        <button class="control-button" :data-active="micEnabled" @click="toggleMicrophone">
          <span class="control-button-icon">{{ micEnabled ? "🎤" : "🔇" }}</span>
          <span class="control-button-label">{{ micEnabled ? "麦克风开启" : "麦克风关闭" }}</span>
        </button>
        <button class="control-button" :data-active="cameraEnabled" @click="toggleCamera">
          <span class="control-button-icon">{{ cameraEnabled ? "📹" : "🚫" }}</span>
          <span class="control-button-label">{{ cameraEnabled ? "视频占位开启" : "视频占位关闭" }}</span>
        </button>
      </div>

      <div class="control-utils">
        <button class="utility-button" @click="toggleSettingsHint">设置</button>
        <span v-if="showSettingsHint" class="utility-hint">更多设备与偏好设置稍后接入</span>
      </div>
    </footer>
  </div>
</template>
