<template>
  <div class="mx-auto max-w-7xl space-y-6 pb-10">
    <section class="rounded-2xl border border-outline-variant/20 bg-surface-container-lowest px-6 py-6">
      <div class="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p class="text-xs font-semibold uppercase tracking-widest text-primary">AI-HR Console</p>
          <h1 class="mt-2 text-3xl font-bold text-on-surface">招聘控制台</h1>
          <p class="mt-2 text-sm text-on-surface-variant">总览关键招聘指标，并实时追踪 AI 智能体执行状态。</p>
        </div>
        <div class="text-right">
          <p class="text-xs text-on-surface-variant">最近同步</p>
          <p class="mt-1 text-sm font-semibold text-on-surface">{{ lastSyncedAt }}</p>
          <button
            class="mt-3 inline-flex h-10 items-center gap-2 rounded-lg border border-outline-variant/30 bg-surface-container-low px-4 text-sm font-semibold text-on-surface-variant transition-colors hover:bg-surface-container disabled:opacity-50"
            :disabled="isLoading || isRefreshing"
            @click="loadData()"
          >
            <span class="material-symbols-outlined text-base" :class="{ 'animate-spin': isLoading || isRefreshing }">refresh</span>
            刷新数据
          </button>
        </div>
      </div>

      <div class="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <article class="rounded-xl border border-outline-variant/20 bg-surface px-4 py-4">
          <p class="text-xs font-semibold text-on-surface-variant">候选人总数</p>
          <p class="mt-2 text-2xl font-bold text-on-surface">{{ totalCandidates }}</p>
        </article>
        <article class="rounded-xl border border-outline-variant/20 bg-surface px-4 py-4">
          <p class="text-xs font-semibold text-on-surface-variant">本周转化率</p>
          <p class="mt-2 text-2xl font-bold text-on-surface">{{ weeklyConversion }}</p>
        </article>
        <article class="rounded-xl border border-outline-variant/20 bg-surface px-4 py-4">
          <p class="text-xs font-semibold text-on-surface-variant">AI 处理总量</p>
          <p class="mt-2 text-2xl font-bold text-on-surface">{{ analytics?.total_synced ?? 0 }}</p>
        </article>
        <article class="rounded-xl border border-outline-variant/20 bg-surface px-4 py-4">
          <p class="text-xs font-semibold text-on-surface-variant">待人工处理</p>
          <p class="mt-2 text-2xl font-bold text-on-surface">{{ urgentTasks.length }}</p>
        </article>
      </div>
    </section>

    <section v-if="isLoading" class="rounded-2xl border border-outline-variant/20 bg-surface-container-lowest px-6 py-10 text-center">
      <div class="mx-auto mb-3 h-10 w-10 animate-spin rounded-full border-4 border-primary/20 border-t-primary"></div>
      <p class="text-sm text-on-surface-variant">正在加载控制台数据...</p>
    </section>

    <section v-else-if="loadError" class="rounded-2xl border border-error/20 bg-error-container/40 px-6 py-8">
      <p class="text-sm font-semibold text-on-error-container">{{ loadError }}</p>
      <button class="mt-3 h-10 rounded-lg bg-white px-4 text-sm font-semibold text-on-error-container" @click="loadData()">重试</button>
    </section>

    <template v-else-if="analytics">
      <div class="grid grid-cols-1 gap-6 lg:grid-cols-12">
        <section class="lg:col-span-8 rounded-2xl border border-outline-variant/20 bg-surface-container-lowest p-6">
          <div class="mb-5 flex items-center justify-between">
            <div>
              <h3 class="text-lg font-bold text-on-surface">招聘漏斗分析</h3>
              <p class="mt-1 text-xs text-on-surface-variant">最近 30 天</p>
            </div>
            <span class="rounded-full bg-primary/10 px-3 py-1 text-xs font-semibold text-primary">实时指标</span>
          </div>

          <div class="grid grid-cols-2 gap-3 md:grid-cols-4">
            <article v-for="step in analytics.funnel" :key="step.label" class="rounded-xl border border-outline-variant/15 bg-surface px-3 py-3">
              <p class="text-xs font-semibold text-on-surface-variant">{{ step.label }}</p>
              <p class="mt-1 text-2xl font-bold text-on-surface">{{ step.value }}</p>
              <p class="mt-1 text-xs" :class="step.growth >= 0 ? 'text-emerald-600' : 'text-rose-600'">
                {{ step.growth >= 0 ? '+' : '' }}{{ step.growth }}%
              </p>
            </article>
          </div>

          <div class="mt-5 flex h-56 items-end gap-3 rounded-xl border border-outline-variant/15 bg-surface p-4">
            <div v-for="step in analytics.funnel" :key="`${step.label}-bar`" class="flex h-full flex-1 flex-col items-center justify-end gap-2">
              <div class="w-full rounded-lg bg-primary" :style="{ height: step.height, opacity: step.opacity }"></div>
              <span class="text-[11px] text-on-surface-variant">{{ step.label }}</span>
            </div>
          </div>
        </section>

        <section class="lg:col-span-4 rounded-2xl border border-outline-variant/20 bg-surface-container-lowest p-6">
          <h3 class="text-lg font-bold text-on-surface">AI效率看板</h3>
          <p class="mt-1 text-xs text-on-surface-variant">流程自动化表现</p>
          <div class="mt-4 space-y-3">
            <article v-for="metric in analytics.efficiency" :key="metric.label" class="rounded-xl border border-outline-variant/15 bg-surface px-4 py-3">
              <p class="text-xs text-on-surface-variant">{{ metric.label }}</p>
              <div class="mt-1 flex items-end gap-2">
                <span class="text-3xl font-bold text-on-surface">{{ metric.value }}</span>
                <span class="pb-1 text-sm text-on-surface-variant">{{ metric.unit }}</span>
              </div>
              <div class="mt-2 h-2 rounded-full bg-surface-container-high">
                <div class="h-full rounded-full bg-primary" :style="{ width: `${metric.progress}%` }"></div>
              </div>
            </article>
          </div>
        </section>
      </div>

      <div class="grid grid-cols-1 gap-6 xl:grid-cols-12">
        <section class="xl:col-span-5 rounded-2xl border border-outline-variant/20 bg-surface-container-lowest p-6">
          <div class="mb-4 flex items-center justify-between">
            <h3 class="text-lg font-bold text-on-surface">待人工处理</h3>
            <span class="rounded-full bg-error-container/30 px-3 py-1 text-xs font-semibold text-error">{{ urgentTasks.length }} 项</span>
          </div>

          <div v-if="urgentTasks.length" class="space-y-3">
            <article v-for="task in urgentTasks" :key="task.id" class="rounded-xl border border-outline-variant/15 bg-surface px-4 py-3">
              <div class="flex items-start justify-between gap-2">
                <div>
                  <p class="text-sm font-semibold text-on-surface">{{ task.title }}</p>
                  <p class="mt-1 text-xs text-on-surface-variant">{{ task.desc }}</p>
                  <p class="mt-2 text-xs text-on-surface-variant">{{ task.timeText }}</p>
                </div>
                <button class="text-xs font-semibold text-primary hover:underline" @click="handleTaskAction(task)">处理</button>
              </div>
            </article>
          </div>
          <p v-else class="text-sm text-on-surface-variant">当前没有待人工处理任务。</p>
        </section>

        <section class="xl:col-span-7 rounded-2xl border border-outline-variant/20 bg-surface-container-lowest p-6">
          <div class="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div>
              <h3 class="text-lg font-bold text-on-surface">AI 智能体动态预览</h3>
              <p class="mt-1 text-xs text-on-surface-variant">展示最新执行事件，完整视图请进入运行中心。</p>
            </div>
            <div class="flex items-center gap-3">
              <span class="h-2.5 w-2.5 animate-pulse rounded-full bg-emerald-500"></span>
              <span class="text-xs font-semibold text-on-surface-variant">LIVE</span>
              <button class="h-9 rounded-lg bg-primary px-3 text-xs font-semibold text-white" @click="openAgentCenter">
                进入运行中心
              </button>
            </div>
          </div>

          <div v-if="recentAgentEvents.length" class="space-y-3">
            <article v-for="event in recentAgentEvents" :key="event.id" class="rounded-xl border border-outline-variant/15 bg-surface px-4 py-3">
              <div class="flex items-start justify-between gap-3">
                <div>
                  <div class="flex flex-wrap items-center gap-2">
                    <span class="rounded-full px-2 py-1 text-[11px] font-semibold" :class="statusClass(event.status)">{{ statusText(event.status) }}</span>
                    <span class="rounded-full bg-surface-container-low px-2 py-1 text-[11px] text-on-surface-variant">{{ agentTypeText(event.agentType) }}</span>
                    <span class="text-[11px] text-on-surface-variant">{{ event.timeText }}</span>
                  </div>
                  <p class="mt-2 text-sm font-semibold text-on-surface">{{ event.title }}</p>
                  <p class="mt-1 text-sm text-on-surface-variant">{{ event.desc }}</p>
                  <div class="mt-2 flex flex-wrap gap-2">
                    <span v-for="tag in event.tags" :key="tag" class="rounded-md border border-outline-variant/15 bg-surface-container-low px-2 py-1 text-[11px] text-on-surface-variant">
                      {{ tag }}
                    </span>
                  </div>
                </div>
                <button
                  v-if="event.action"
                  class="h-9 rounded-lg bg-primary px-3 text-xs font-semibold text-white"
                  @click="handleEventAction(event)"
                >
                  {{ event.actionLabel || '查看' }}
                </button>
              </div>
            </article>
          </div>
          <p v-else class="text-sm text-on-surface-variant">暂无智能体动态。</p>
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

let pollTimer: ReturnType<typeof setInterval> | null = null;

const lastSyncedAt = computed(() => {
  if (!lastSyncedMs.value) {
    return "--";
  }
  return formatDateTime(lastSyncedMs.value);
});

const totalCandidates = computed(() => {
  return analytics.value?.funnel?.[0]?.value ?? 0;
});

const weeklyConversion = computed(() => {
  const funnel = analytics.value?.funnel ?? [];
  if (funnel.length < 2) {
    return "--";
  }
  const first = funnel[0]?.value ?? 0;
  const last = funnel[funnel.length - 1]?.value ?? 0;
  if (!first) {
    return "--";
  }
  return `${Math.round((last / first) * 100)}%`;
});

const recentAgentEvents = computed(() => {
  return [...agentEvents.value].sort((a, b) => b.timeMs - a.timeMs).slice(0, 4);
});

const urgentTasks = computed<TaskItem[]>(() => {
  return agentEvents.value
    .filter((event) => event.status === "waiting_human" || event.status === "failed")
    .slice(0, 6)
    .map((event) => ({
      id: `task-${event.id}`,
      title: event.status === "failed" ? "AI任务失败待处理" : "AI任务待人工确认",
      desc: event.title,
      timeText: event.timeText,
      action: event.action,
    }));
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

function openAgentCenter() {
  router.push("/admin/agents");
}

function timeAgo(input?: string | null): { ms: number; text: string } {
  const now = Date.now();
  const ts = input ? new Date(input).getTime() : now;
  const ms = Number.isNaN(ts) ? now : ts;
  const diff = Math.max(0, now - ms);
  const min = Math.floor(diff / 60000);
  if (min < 1) {
    return { ms, text: "刚刚" };
  }
  if (min < 60) {
    return { ms, text: `${min} 分钟前` };
  }
  const hour = Math.floor(min / 60);
  if (hour < 24) {
    return { ms, text: `${hour} 小时前` };
  }
  const day = Math.floor(hour / 24);
  return { ms, text: `${day} 天前` };
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

function mapRecommendationToStatus(recommendation: string): AgentStatus {
  if (recommendation === "review") {
    return "waiting_human";
  }
  if (recommendation === "reject") {
    return "failed";
  }
  return "completed";
}

function buildAgentEvents(): AgentEvent[] {
  const events: AgentEvent[] = [];

  (hiringOverview.value?.top_items || []).forEach((item, index) => {
    const ago = timeAgo(item.updated_at || item.created_at);
    const status = item.invited_flag ? "running" : mapRecommendationToStatus(item.recommendation);
    events.push({
      id: `top-${item.job_id}-${item.candidate_id}-${index}`,
      status,
      agentType: "analytics",
      title: `候选人 ${item.candidate_name} 完成岗位匹配评估`,
      desc: `岗位 ${item.job_title}，当前建议：${item.recommendation}，评分 ${Number(item.final_score || 0).toFixed(1)}。`,
      tags: ["岗位匹配", `评分 ${Number(item.final_score || 0).toFixed(1)}`],
      timeMs: ago.ms,
      timeText: ago.text,
      action: { type: "candidate", jobId: item.job_id, candidateId: item.candidate_id },
      actionLabel: "查看候选人",
    });
  });

  (hiringOverview.value?.queue_items || []).slice(0, 8).forEach((item, index) => {
    const ago = timeAgo(item.updated_at || item.created_at);
    events.push({
      id: `queue-${item.job_id}-${item.candidate_id}-${index}`,
      status: "waiting_human",
      agentType: "screening",
      title: `候选人 ${item.candidate_name} 等待人工复核`,
      desc: `岗位 ${item.job_title}，AI 建议 ${item.recommendation}，请确认是否推进面试。`,
      tags: ["待复核", item.job_title],
      timeMs: ago.ms,
      timeText: ago.text,
      action: { type: "candidate", jobId: item.job_id, candidateId: item.candidate_id },
      actionLabel: "立即处理",
    });
  });

  inviteHistory.value.slice(0, 10).forEach((invite, index) => {
    const ago = timeAgo(invite.sent_at || invite.created_at);
    let status: AgentStatus = "running";
    if (invite.delivery_status === "failed") {
      status = "failed";
    } else if (["opened", "clicked", "delivered", "sent"].includes(invite.delivery_status)) {
      status = "completed";
    }

    events.push({
      id: `invite-${invite.id}-${index}`,
      status,
      agentType: "outreach",
      title: `已触发候选人 ${invite.candidate_name} 的面试邀约流程`,
      desc: `岗位 ${invite.job_title}，当前投递状态：${invite.delivery_status}。`,
      tags: ["邀约", invite.delivery_status],
      timeMs: ago.ms,
      timeText: ago.text,
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
    });
  });

  return events.sort((a, b) => b.timeMs - a.timeMs);
}

function handleEventAction(event: AgentEvent) {
  if (!event.action) {
    return;
  }

  if (event.action.type === "candidate" && event.action.jobId && event.action.candidateId) {
    router.push(`/admin/candidate-detail?jobId=${event.action.jobId}&candidateId=${event.action.candidateId}`);
  }

  if (event.action.type === "invite") {
    router.push("/admin/interview-history");
  }
}

function handleTaskAction(task: TaskItem) {
  const action = task.action;
  if (!action) {
    return;
  }

  if (action.type === "candidate" && action.jobId && action.candidateId) {
    router.push(`/admin/candidate-detail?jobId=${action.jobId}&candidateId=${action.candidateId}`);
    return;
  }

  if (action.type === "invite") {
    router.push("/admin/interview-history");
  }
}

async function loadData(silent = false) {
  if (silent) {
    isRefreshing.value = true;
  } else {
    isLoading.value = true;
    loadError.value = "";
  }

  try {
    const [analyticsData, hiringData, inviteData] = await Promise.all([
      fetchDashboardAnalytics(),
      fetchHiringCenterOverview({ top_n: 6, queue_limit: 20, max_scan: 3000 }),
      fetchInterviewInvitationHistory({ limit: 50 }),
    ]);

    analytics.value = analyticsData;
    hiringOverview.value = hiringData;
    inviteHistory.value = inviteData.items || [];
    agentEvents.value = buildAgentEvents();
    lastSyncedMs.value = Date.now();
  } catch (error) {
    console.error("Failed to fetch dashboard data", error);
    if (!analytics.value) {
      loadError.value = "加载控制台数据失败，请稍后重试。";
    }
  } finally {
    if (silent) {
      isRefreshing.value = false;
    } else {
      isLoading.value = false;
    }
  }
}

onMounted(async () => {
  await loadData();
  pollTimer = setInterval(() => {
    void loadData(true);
  }, 10000);
});

onUnmounted(() => {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
});
</script>
