<template>
  <div class="mx-auto max-w-7xl space-y-6 pb-10">
    <section class="rounded-2xl border border-outline-variant/20 bg-surface-container-lowest px-6 py-6">
      <div class="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p class="text-xs font-semibold uppercase tracking-widest text-primary">Agent Ops Center</p>
          <h1 class="mt-2 text-3xl font-bold text-on-surface">AI 智能体实时作战台</h1>
          <p class="mt-2 text-sm text-on-surface-variant">观察 AI 员工的实时思考与执行链路，并在关键节点进行人工接管。</p>
        </div>
        <div class="flex items-center gap-2">
          <button
            class="h-10 rounded-lg border border-outline-variant/30 px-4 text-sm font-semibold"
            :class="isLive ? 'bg-emerald-50 text-emerald-700' : 'bg-surface-container-low text-on-surface-variant'"
            @click="toggleLive"
          >
            {{ isLive ? '实时模式' : '已暂停' }}
          </button>
          <button
            class="inline-flex h-10 items-center gap-2 rounded-lg border border-outline-variant/30 bg-surface-container-low px-4 text-sm font-semibold text-on-surface-variant transition-colors hover:bg-surface-container disabled:opacity-50"
            :disabled="isLoading || isRefreshing"
            @click="loadData()"
          >
            <span class="material-symbols-outlined text-base" :class="{ 'animate-spin': isLoading || isRefreshing }">refresh</span>
            刷新
          </button>
        </div>
      </div>

      <div class="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <article class="rounded-xl border border-outline-variant/20 bg-surface px-4 py-4">
          <p class="text-xs text-on-surface-variant">执行中</p>
          <p class="mt-2 text-2xl font-bold text-on-surface">{{ stats.running }}</p>
        </article>
        <article class="rounded-xl border border-outline-variant/20 bg-surface px-4 py-4">
          <p class="text-xs text-on-surface-variant">待人工</p>
          <p class="mt-2 text-2xl font-bold text-on-surface">{{ stats.waiting_human }}</p>
        </article>
        <article class="rounded-xl border border-outline-variant/20 bg-surface px-4 py-4">
          <p class="text-xs text-on-surface-variant">失败</p>
          <p class="mt-2 text-2xl font-bold text-on-surface">{{ stats.failed }}</p>
        </article>
        <article class="rounded-xl border border-outline-variant/20 bg-surface px-4 py-4">
          <p class="text-xs text-on-surface-variant">最近同步</p>
          <p class="mt-2 text-sm font-semibold text-on-surface">{{ lastSyncedAt }}</p>
        </article>
      </div>
    </section>

    <section v-if="isLoading" class="rounded-2xl border border-outline-variant/20 bg-surface-container-lowest px-6 py-12 text-center">
      <div class="mx-auto mb-3 h-10 w-10 animate-spin rounded-full border-4 border-primary/20 border-t-primary"></div>
      <p class="text-sm text-on-surface-variant">正在加载智能体动态...</p>
    </section>

    <section v-else-if="loadError" class="rounded-2xl border border-error/20 bg-error-container/40 px-6 py-8">
      <p class="text-sm font-semibold text-on-error-container">{{ loadError }}</p>
      <button class="mt-3 h-10 rounded-lg bg-white px-4 text-sm font-semibold text-on-error-container" @click="loadData()">重试</button>
    </section>

    <template v-else>
      <div class="grid grid-cols-1 gap-6 xl:grid-cols-12">
        <section class="xl:col-span-3 rounded-2xl border border-outline-variant/20 bg-surface-container-lowest p-4">
          <div class="mb-4 flex items-center justify-between">
            <h3 class="text-base font-bold text-on-surface">Agent 状态墙</h3>
            <span class="text-xs text-on-surface-variant">并行执行</span>
          </div>

          <div class="space-y-3">
            <article v-for="agent in agentWallCards" :key="agent.type" class="rounded-xl border border-outline-variant/15 bg-surface px-3 py-3">
              <div class="flex items-center justify-between">
                <p class="text-sm font-semibold text-on-surface">{{ agent.name }}</p>
                <span class="rounded-full px-2 py-0.5 text-[11px] font-semibold" :class="statusClass(agent.primaryStatus)">
                  {{ statusText(agent.primaryStatus) }}
                </span>
              </div>
              <p class="mt-1 text-xs text-on-surface-variant">{{ agent.currentTitle }}</p>
              <div class="mt-2 grid grid-cols-3 gap-2 text-center text-[11px]">
                <div class="rounded-md bg-surface-container-low px-1 py-1">
                  <p class="text-on-surface">{{ agent.running }}</p>
                  <p class="text-on-surface-variant">执行</p>
                </div>
                <div class="rounded-md bg-surface-container-low px-1 py-1">
                  <p class="text-on-surface">{{ agent.waiting }}</p>
                  <p class="text-on-surface-variant">待人工</p>
                </div>
                <div class="rounded-md bg-surface-container-low px-1 py-1">
                  <p class="text-on-surface">{{ agent.failed }}</p>
                  <p class="text-on-surface-variant">失败</p>
                </div>
              </div>
            </article>
          </div>
        </section>

        <section class="xl:col-span-6 rounded-2xl border border-outline-variant/20 bg-surface-container-lowest p-4">
          <div class="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div>
              <h3 class="text-base font-bold text-on-surface">实时执行时间轴</h3>
              <p class="mt-1 text-xs text-on-surface-variant">从最新事件到历史事件，持续流式更新。</p>
            </div>
            <div class="flex items-center gap-2">
              <span class="h-2.5 w-2.5 rounded-full" :class="isLive ? 'animate-pulse bg-emerald-500' : 'bg-outline-variant'"></span>
              <span class="text-xs font-semibold text-on-surface-variant">{{ isLive ? 'LIVE' : 'PAUSED' }}</span>
            </div>
          </div>

          <div class="mb-4 grid grid-cols-1 gap-2 md:grid-cols-3">
            <select v-model="agentStatusFilter" class="h-9 rounded-lg border border-outline-variant/30 bg-white px-3 text-sm text-on-surface">
              <option value="all">全部状态</option>
              <option value="running">执行中</option>
              <option value="waiting_human">待人工</option>
              <option value="completed">已完成</option>
              <option value="failed">失败</option>
            </select>
            <select v-model="agentTypeFilter" class="h-9 rounded-lg border border-outline-variant/30 bg-white px-3 text-sm text-on-surface">
              <option value="all">全部智能体</option>
              <option value="screening">筛选智能体</option>
              <option value="interview">面试智能体</option>
              <option value="outreach">邀约智能体</option>
              <option value="analytics">分析智能体</option>
            </select>
            <input v-model.trim="agentKeyword" type="text" placeholder="搜索候选人/岗位" class="h-9 rounded-lg border border-outline-variant/30 bg-white px-3 text-sm text-on-surface" >
          </div>

          <div class="relative space-y-3 before:absolute before:left-3 before:top-2 before:bottom-2 before:w-px before:bg-outline-variant/30">
            <article v-for="event in filteredAgentEvents" :key="event.id" class="relative rounded-xl border border-outline-variant/15 bg-surface p-3 pl-8">
              <span class="absolute left-0 top-3 inline-flex h-6 w-6 items-center justify-center rounded-full text-[11px] font-semibold" :class="statusClass(event.status)">
                {{ event.agentShort }}
              </span>
              <div class="flex items-start justify-between gap-3">
                <div>
                  <div class="flex flex-wrap items-center gap-2">
                    <span class="rounded-full px-2 py-0.5 text-[11px] font-semibold" :class="statusClass(event.status)">{{ statusText(event.status) }}</span>
                    <span class="rounded-full bg-surface-container-low px-2 py-0.5 text-[11px] text-on-surface-variant">{{ agentTypeText(event.agentType) }}</span>
                    <span class="text-[11px] text-on-surface-variant">{{ event.timeText }} · 已运行 {{ elapsedText(event.timeMs) }}</span>
                  </div>
                  <p class="mt-2 text-sm font-semibold text-on-surface">{{ event.title }}</p>
                  <p class="mt-1 text-sm text-on-surface-variant">{{ event.desc }}</p>
                  <div class="mt-2 flex flex-wrap gap-2">
                    <span v-for="tag in event.tags" :key="tag" class="rounded-md border border-outline-variant/15 bg-surface-container-low px-2 py-1 text-[11px] text-on-surface-variant">{{ tag }}</span>
                  </div>
                </div>
                <button v-if="event.action" class="h-8 rounded-lg bg-primary px-3 text-xs font-semibold text-white" @click="handleEventAction(event)">
                  {{ event.actionLabel || '查看' }}
                </button>
              </div>
            </article>
          </div>
        </section>

        <section class="xl:col-span-3 rounded-2xl border border-outline-variant/20 bg-surface-container-lowest p-4">
          <h3 class="text-base font-bold text-on-surface">当前执行任务</h3>
          <p class="mt-1 text-xs text-on-surface-variant">AI 正在思考与执行的关键链路。</p>

          <div v-if="activeExecution" class="mt-4 space-y-4">
            <div class="rounded-xl border border-outline-variant/15 bg-surface p-3">
              <p class="text-sm font-semibold text-on-surface">{{ activeExecution.title }}</p>
              <p class="mt-1 text-xs text-on-surface-variant">{{ activeExecution.desc }}</p>
              <p class="mt-2 text-[11px] text-on-surface-variant">{{ activeExecution.timeText }} · 已运行 {{ elapsedText(activeExecution.timeMs) }}</p>
            </div>

            <div class="rounded-xl border border-outline-variant/15 bg-surface p-3">
              <p class="text-xs font-semibold text-on-surface-variant">执行阶段</p>
              <div class="mt-3 space-y-2">
                <div v-for="phase in activePhases" :key="phase.label" class="flex items-center gap-2">
                  <span class="h-2.5 w-2.5 rounded-full" :class="phase.status === 'completed' ? 'bg-emerald-500' : phase.status === 'active' ? 'bg-primary animate-pulse' : 'bg-outline-variant'"/>
                  <p class="text-sm" :class="phase.status === 'pending' ? 'text-on-surface-variant' : 'text-on-surface font-medium'">{{ phase.label }}</p>
                </div>
              </div>
            </div>

            <button v-if="activeExecution.action" class="h-9 w-full rounded-lg bg-primary px-3 text-xs font-semibold text-white" @click="handleEventAction(activeExecution)">
              {{ activeExecution.actionLabel || '查看任务' }}
            </button>
          </div>

          <div v-else class="mt-4 rounded-xl border border-dashed border-outline-variant/30 p-4 text-sm text-on-surface-variant">
            当前没有执行中的任务，系统处于稳定状态。
          </div>

          <div class="mt-5">
            <h4 class="text-sm font-semibold text-on-surface">待人工处理队列</h4>
            <div class="mt-2 space-y-2">
              <article v-for="task in urgentTasks.slice(0, 4)" :key="task.id" class="rounded-lg border border-outline-variant/15 bg-surface px-3 py-2">
                <p class="text-xs font-semibold text-on-surface">{{ task.title }}</p>
                <p class="mt-1 text-[11px] text-on-surface-variant">{{ task.timeText }}</p>
              </article>
            </div>
          </div>
        </section>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useRouter } from "vue-router";
import {
  fetchDashboardAnalytics,
  fetchHiringCenterOverview,
  fetchInterviewInvitationHistory,
  type DashboardAnalytics,
  type HiringCenterOverviewResult,
  type InterviewInvitationHistoryItem,
} from "../../api";

type AgentStatus = "running" | "waiting_human" | "completed" | "failed";
type AgentType = "screening" | "interview" | "outreach" | "analytics";

type AgentEvent = {
  id: string;
  status: AgentStatus;
  agentType: AgentType;
  title: string;
  desc: string;
  tags: string[];
  timeMs: number;
  timeText: string;
  agentShort: string;
  action?: { type: "candidate" | "invite"; jobId?: string; candidateId?: string; inviteId?: string };
  actionLabel?: string;
};

type TaskItem = {
  id: string;
  title: string;
  desc: string;
  timeText: string;
  action?: { type: "candidate" | "invite"; jobId?: string; candidateId?: string; inviteId?: string };
};

const router = useRouter();

const analytics = ref<DashboardAnalytics | null>(null);
const hiringOverview = ref<HiringCenterOverviewResult | null>(null);
const inviteHistory = ref<InterviewInvitationHistoryItem[]>([]);
const agentEvents = ref<AgentEvent[]>([]);

const isLoading = ref(true);
const isRefreshing = ref(false);
const loadError = ref("");
const lastSyncedMs = ref<number | null>(null);
const isLive = ref(true);
const nowMs = ref(Date.now());

const agentStatusFilter = ref<"all" | AgentStatus>("all");
const agentTypeFilter = ref<"all" | AgentType>("all");
const agentKeyword = ref("");

let pollTimer: ReturnType<typeof setInterval> | null = null;
let tickTimer: ReturnType<typeof setInterval> | null = null;

const lastSyncedAt = computed(() => {
  if (!lastSyncedMs.value) return "--";
  return formatDateTime(lastSyncedMs.value);
});

const filteredAgentEvents = computed(() => {
  let list = [...agentEvents.value];
  if (agentStatusFilter.value !== "all") list = list.filter((x) => x.status === agentStatusFilter.value);
  if (agentTypeFilter.value !== "all") list = list.filter((x) => x.agentType === agentTypeFilter.value);

  const keyword = agentKeyword.value.trim().toLowerCase();
  if (keyword) {
    list = list.filter((x) => `${x.title} ${x.desc} ${x.tags.join(" ")}`.toLowerCase().includes(keyword));
  }
  return list.sort((a, b) => b.timeMs - a.timeMs).slice(0, 18);
});

const urgentTasks = computed<TaskItem[]>(() => {
  return filteredAgentEvents.value
    .filter((x) => x.status === "waiting_human" || x.status === "failed")
    .slice(0, 8)
    .map((x) => ({
      id: `task-${x.id}`,
      title: x.status === "failed" ? "AI任务失败待处理" : "AI任务待人工确认",
      desc: x.title,
      timeText: x.timeText,
      action: x.action,
    }));
});

const stats = computed(() => {
  const acc = { running: 0, waiting_human: 0, completed: 0, failed: 0 };
  agentEvents.value.forEach((x) => {
    acc[x.status] += 1;
  });
  return acc;
});

const agentWallCards = computed(() => {
  const definitions: Array<{ type: AgentType; name: string }> = [
    { type: "screening", name: "筛选智能体" },
    { type: "analytics", name: "分析智能体" },
    { type: "outreach", name: "邀约智能体" },
    { type: "interview", name: "面试智能体" },
  ];

  return definitions.map((def) => {
    const list = agentEvents.value.filter((x) => x.agentType === def.type);
    const running = list.filter((x) => x.status === "running").length;
    const waiting = list.filter((x) => x.status === "waiting_human").length;
    const failed = list.filter((x) => x.status === "failed").length;
    const current = [...list].sort((a, b) => b.timeMs - a.timeMs)[0];

    let primaryStatus: AgentStatus = "completed";
    if (running > 0) primaryStatus = "running";
    else if (waiting > 0) primaryStatus = "waiting_human";
    else if (failed > 0) primaryStatus = "failed";

    return {
      type: def.type,
      name: def.name,
      running,
      waiting,
      failed,
      primaryStatus,
      currentTitle: current?.title || "暂无任务",
    };
  });
});

const activeExecution = computed(() => {
  const running = filteredAgentEvents.value.find((x) => x.status === "running");
  if (running) return running;
  return filteredAgentEvents.value.find((x) => x.status === "waiting_human") || null;
});

const activePhases = computed(() => {
  const stages = ["观察", "规划", "执行", "校验"];
  const event = activeExecution.value;
  if (!event) {
    return stages.map((label) => ({ label, status: "pending" as const }));
  }

  let activeIndex = 1;
  if (event.status === "running") activeIndex = 2;
  if (event.status === "waiting_human") activeIndex = 3;
  if (event.status === "completed") activeIndex = 3;
  if (event.status === "failed") activeIndex = 2;

  return stages.map((label, index) => {
    if (index < activeIndex) return { label, status: "completed" as const };
    if (index === activeIndex) return { label, status: "active" as const };
    return { label, status: "pending" as const };
  });
});

function formatDateTime(ms: number): string {
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(new Date(ms));
}

function timeAgo(input?: string | null): { ms: number; text: string } {
  const now = Date.now();
  const ts = input ? new Date(input).getTime() : now;
  const ms = Number.isNaN(ts) ? now : ts;
  const diff = Math.max(0, now - ms);
  const min = Math.floor(diff / 60000);
  if (min < 1) return { ms, text: "刚刚" };
  if (min < 60) return { ms, text: `${min} 分钟前` };
  const hour = Math.floor(min / 60);
  if (hour < 24) return { ms, text: `${hour} 小时前` };
  return { ms, text: `${Math.floor(hour / 24)} 天前` };
}

function elapsedText(ms: number): string {
  const diff = Math.max(0, nowMs.value - ms);
  const sec = Math.floor(diff / 1000);
  if (sec < 60) return `${sec} 秒`;
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min} 分 ${sec % 60} 秒`;
  const hour = Math.floor(min / 60);
  return `${hour} 小时 ${min % 60} 分`;
}

function statusText(status: AgentStatus): string {
  if (status === "running") return "执行中";
  if (status === "waiting_human") return "待人工";
  if (status === "failed") return "失败";
  return "已完成";
}

function statusClass(status: AgentStatus): string {
  if (status === "running") return "bg-primary/10 text-primary";
  if (status === "waiting_human") return "bg-amber-100 text-amber-700";
  if (status === "failed") return "bg-rose-100 text-rose-700";
  return "bg-emerald-100 text-emerald-700";
}

function agentTypeText(type: AgentType): string {
  if (type === "screening") return "筛选智能体";
  if (type === "interview") return "面试智能体";
  if (type === "outreach") return "邀约智能体";
  return "分析智能体";
}

function agentShort(type: AgentType): string {
  if (type === "screening") return "筛";
  if (type === "interview") return "面";
  if (type === "outreach") return "邀";
  return "析";
}

function mapRecommendationToStatus(recommendation: string): AgentStatus {
  if (recommendation === "review") return "waiting_human";
  if (recommendation === "reject") return "failed";
  return "completed";
}

function buildAgentEvents(): AgentEvent[] {
  const events: AgentEvent[] = [];

  (hiringOverview.value?.top_items || []).forEach((item, index) => {
    const ago = timeAgo(item.updated_at || item.created_at);
    events.push({
      id: `top-${item.job_id}-${item.candidate_id}-${index}`,
      status: item.invited_flag ? "running" : mapRecommendationToStatus(item.recommendation),
      agentType: "analytics",
      title: `候选人 ${item.candidate_name} 完成岗位匹配评估`,
      desc: `岗位 ${item.job_title}，建议 ${item.recommendation}，评分 ${Number(item.final_score || 0).toFixed(1)}。`,
      tags: ["岗位匹配", `评分 ${Number(item.final_score || 0).toFixed(1)}`],
      timeMs: ago.ms,
      timeText: ago.text,
      agentShort: agentShort("analytics"),
      action: { type: "candidate", jobId: item.job_id, candidateId: item.candidate_id },
      actionLabel: "查看候选人",
    });
  });

  (hiringOverview.value?.queue_items || []).slice(0, 10).forEach((item, index) => {
    const ago = timeAgo(item.updated_at || item.created_at);
    events.push({
      id: `queue-${item.job_id}-${item.candidate_id}-${index}`,
      status: "waiting_human",
      agentType: "screening",
      title: `候选人 ${item.candidate_name} 等待人工复核`,
      desc: `岗位 ${item.job_title}，AI建议 ${item.recommendation}，请确认是否推进。`,
      tags: ["待复核", item.job_title],
      timeMs: ago.ms,
      timeText: ago.text,
      agentShort: agentShort("screening"),
      action: { type: "candidate", jobId: item.job_id, candidateId: item.candidate_id },
      actionLabel: "立即处理",
    });
  });

  inviteHistory.value.slice(0, 12).forEach((invite, index) => {
    const ago = timeAgo(invite.sent_at || invite.created_at);
    let status: AgentStatus = "running";
    if (invite.delivery_status === "failed") status = "failed";
    else if (["opened", "clicked", "delivered", "sent"].includes(invite.delivery_status)) status = "completed";

    events.push({
      id: `invite-${invite.id}-${index}`,
      status,
      agentType: "outreach",
      title: `已触发候选人 ${invite.candidate_name} 的面试邀约流程`,
      desc: `岗位 ${invite.job_title}，当前状态：${invite.delivery_status}。`,
      tags: ["邀约", invite.delivery_status],
      timeMs: ago.ms,
      timeText: ago.text,
      agentShort: agentShort("outreach"),
      action: { type: "invite", inviteId: invite.id, jobId: invite.job_id, candidateId: invite.candidate_id },
      actionLabel: "查看记录",
    });
  });

  (analytics.value?.efficiency || []).forEach((metric, index) => {
    events.push({
      id: `eff-${metric.label}-${index}`,
      status: "completed",
      agentType: "interview",
      title: `智能体效率更新：${metric.label}`,
      desc: `当前指标 ${metric.value}${metric.unit}，流程进度 ${metric.progress}%。`,
      tags: ["效率指标", `${metric.progress}%`],
      timeMs: Date.now() - (index + 1) * 180000,
      timeText: `${(index + 1) * 3} 分钟前`,
      agentShort: agentShort("interview"),
    });
  });

  return events.sort((a, b) => b.timeMs - a.timeMs);
}

function handleEventAction(event: AgentEvent) {
  if (!event.action) return;
  if (event.action.type === "candidate" && event.action.jobId && event.action.candidateId) {
    router.push(`/admin/candidate-detail?jobId=${event.action.jobId}&candidateId=${event.action.candidateId}`);
    return;
  }
  if (event.action.type === "invite") {
    router.push("/admin/interview-history");
  }
}

function handleTaskAction(task: TaskItem) {
  const action = task.action;
  if (!action) return;
  if (action.type === "candidate" && action.jobId && action.candidateId) {
    router.push(`/admin/candidate-detail?jobId=${action.jobId}&candidateId=${action.candidateId}`);
    return;
  }
  if (action.type === "invite") {
    router.push("/admin/interview-history");
  }
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

function startPolling() {
  stopPolling();
  pollTimer = setInterval(() => {
    if (isLive.value) {
      void loadData(true);
    }
  }, 10000);
}

function toggleLive() {
  isLive.value = !isLive.value;
}

async function loadData(silent = false) {
  if (silent) isRefreshing.value = true;
  else {
    isLoading.value = true;
    loadError.value = "";
  }

  try {
    const [analyticsData, hiringData, inviteData] = await Promise.all([
      fetchDashboardAnalytics(),
      fetchHiringCenterOverview({ top_n: 8, queue_limit: 30, max_scan: 3000 }),
      fetchInterviewInvitationHistory({ limit: 80 }),
    ]);

    analytics.value = analyticsData;
    hiringOverview.value = hiringData;
    inviteHistory.value = inviteData.items || [];
    agentEvents.value = buildAgentEvents();
    lastSyncedMs.value = Date.now();
  } catch (error) {
    console.error("Failed to fetch agent center data", error);
    if (!analytics.value) {
      loadError.value = "加载智能体动态失败，请稍后重试。";
    }
  } finally {
    if (silent) isRefreshing.value = false;
    else isLoading.value = false;
  }
}

onMounted(async () => {
  await loadData();
  startPolling();
  tickTimer = setInterval(() => {
    nowMs.value = Date.now();
  }, 5000);
});

onUnmounted(() => {
  stopPolling();
  if (tickTimer) {
    clearInterval(tickTimer);
    tickTimer = null;
  }
});
</script>
