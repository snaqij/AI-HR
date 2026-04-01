<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
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
  type InterviewSession
} from "./api";

const loading = ref(true);
const errorText = ref("");
const exiting = ref(false);
const meetingTimeText = ref("00:00");
const elapsedSeconds = ref(0);

const session = ref<InterviewSession | null>(null);
const sessionId = computed(() => session.value?.id || "");

const micStatus = ref("等待初始化");
const ttsStatus = ref("等待 AI 接入");
const currentQuestion = ref("正在准备面试链路...");
const followupQuestion = ref("");
const transportStatus = ref("未连接");
const transcriptView = ref<string[]>([]);

let tickerTimer: number | null = null;
let eventsSocket: WebSocket | null = null;

const rtcGateway = new AgoraRTCGateway({
  onRemoteAudioSubscribed(uid) {
    ttsStatus.value = `AI 已入会并可播放音频 (${uid})`;
  },
  onRemoteAudioUnsubscribed() {
    ttsStatus.value = "AI 音频已暂停";
  },
  onConnectionStateChanged(state, reason) {
    transportStatus.value = reason ? `${state} (${reason})` : state;
    if (state === "CONNECTED") {
      micStatus.value = "麦克风已发布到 Agora";
    }
  }
});

function appendTranscript(line: string): void {
  if (!line.trim()) {
    return;
  }
  transcriptView.value = [...transcriptView.value, line].slice(-8);
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
      if (transcript) {
        appendTranscript(transcript);
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
    ttsStatus.value = launched.launch_status === "launched" ? "TEN 已拉起，等待 AI 入会" : `TEN 状态: ${launched.launch_status}`;
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

    const replayItems = await loadReplayItems(session.value.id);
    transcriptView.value = replayItems.map((item) => item.transcript || "").filter(Boolean).slice(-8);
    micStatus.value = "候选人音频已接入";

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
  void rtcGateway.disconnect();
});
</script>

<template>
  <div class="meeting-shell">
    <header class="meeting-topbar">
      <div class="topbar-left">
        <div class="brand">
          <span class="brand-mark"></span>
          <span class="brand-text">AI 面试会议 (Agora + TEN)</span>
        </div>
        <span class="meeting-time">{{ meetingTimeText }}</span>
      </div>
      <div class="topbar-right">
        <button class="exit-btn" :disabled="exiting" @click="exitMeeting">
          {{ exiting ? "正在退出..." : "退出面试" }}
        </button>
      </div>
    </header>

    <main class="meeting-main">
      <section v-if="loading" class="loading-view">正在建立 Agora/TEN 面试链路...</section>
      <section v-else-if="errorText" class="loading-view error">{{ errorText }}</section>
      <template v-else>
        <section class="stage-area">
          <div class="stage-overlay-card">
            <div class="avatar-ring"></div>
            <p class="candidate-name">候选人</p>
            <p class="candidate-status-line">设备状态: {{ micStatus }}</p>
            <p class="candidate-status-line">传输状态: {{ transportStatus }}</p>
          </div>
          <div class="interviewer-mini-card">
            <div class="interviewer-avatar"></div>
            <div>
              <p class="interviewer-title">TEN 面试官</p>
              <p class="interviewer-status">{{ ttsStatus }}</p>
            </div>
          </div>
        </section>

        <aside class="session-sidebar">
          <div class="sidebar-block">
            <div class="block-header-inline">
              <p class="block-title">当前追问</p>
            </div>
            <p class="question-text">{{ currentQuestion }}</p>
            <p v-if="followupQuestion" class="followup-text">最新问题: {{ followupQuestion }}</p>
          </div>

          <div class="sidebar-block transcript">
            <div class="block-header-inline">
              <p class="block-title">实时回答记录</p>
            </div>
            <ul class="transcript-list">
              <li v-for="(line, idx) in transcriptView" :key="`${idx}-${line}`">
                <span class="who">你</span>
                <span>{{ line }}</span>
              </li>
              <li v-if="transcriptView.length === 0">
                <span class="who">系统</span>
                <span>Agora 已接入后，候选人发言会在这里实时回显。</span>
              </li>
            </ul>
          </div>
        </aside>
      </template>
    </main>

    <footer class="meeting-footer">
      <div class="footer-tip">主链路: 前端采集 -> Agora RTC -> TEN -> ASR/LLM/TTS -> Agora 回放</div>
    </footer>
  </div>
</template>
