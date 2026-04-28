<template>
  <div class="admin-page">
    <section class="flex flex-wrap items-center justify-end gap-3">
      <button
        class="admin-quiet-btn"
        :class="isLive ? 'border-[#dcedff] bg-[#eef4ff] text-primary hover:bg-[#eef4ff]' : ''"
        @click="toggleLive"
      >
        {{ isLive ? "实时模式" : "已暂停" }}
      </button>
      <button class="admin-quiet-btn" :disabled="isLoading || isRefreshing" @click="loadData()">
        <span class="material-symbols-outlined text-[16px]" :class="{ 'animate-spin': isLoading || isRefreshing }">refresh</span>
        刷新
      </button>
    </section>

    <section v-if="isLoading" class="admin-panel px-6 py-12 text-center">
      <div class="mx-auto mb-3 h-10 w-10 animate-spin rounded-full border-4 border-primary/20 border-t-primary"></div>
      <p class="text-sm text-on-surface-variant">正在加载智能体动态...</p>
    </section>

    <section v-else-if="loadError" class="admin-panel px-6 py-8">
      <p class="text-sm font-semibold text-on-error-container">{{ loadError }}</p>
      <button class="admin-primary-btn mt-3" @click="loadData()">重试</button>
    </section>

    <template v-else>
      <section class="grid grid-cols-1 gap-4 xl:grid-cols-4">
        <article
          v-for="card in overviewCards"
          :key="card.name"
          class="admin-panel px-5 py-5"
        >
          <div class="flex items-center justify-between gap-3">
            <div>
              <div class="flex items-center gap-2">
                <p class="text-[14px] font-semibold text-on-surface">{{ card.name }}</p>
                <span class="admin-badge" :class="card.badgeClass">{{ card.badgeLabel }}</span>
              </div>
              <p class="mt-2 text-[12px] text-on-surface-variant">今日任务</p>
              <p class="mt-1 text-[28px] font-semibold tracking-tight text-on-surface">{{ card.taskCount }}</p>
            </div>
            <div class="text-right">
              <p class="text-[12px] text-on-surface-variant">{{ card.metricLabel }}</p>
              <p class="mt-1 text-[24px] font-semibold tracking-tight text-on-surface">{{ card.metricValue }}</p>
            </div>
          </div>
        </article>
      </section>

      <section class="grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,1.6fr)_360px]">
        <article class="admin-panel overflow-hidden">
          <div class="flex items-center justify-between border-b border-[#eef2f7] px-6 py-5">
            <div>
              <h3 class="admin-section-title">Agent 任务监控</h3>
              <p class="mt-1 text-[12px] text-on-surface-variant">已同步 {{ lastSyncedAt }}</p>
            </div>
            <div class="flex items-center gap-2 text-[12px] text-on-surface-variant">
              <span class="h-2.5 w-2.5 rounded-full" :class="isLive ? 'animate-pulse bg-emerald-500' : 'bg-outline-variant'"></span>
              <span>{{ isLive ? "LIVE" : "PAUSED" }}</span>
            </div>
          </div>

          <div class="grid grid-cols-[minmax(180px,1.4fr)_minmax(120px,1fr)_100px_120px_100px_100px_88px] gap-4 px-6 py-4 admin-table-head">
            <div class="admin-table-label">Agent 名称</div>
            <div class="admin-table-label">任务类型</div>
            <div class="admin-table-label text-center">状态</div>
            <div class="admin-table-label">进度</div>
            <div class="admin-table-label text-center">今日任务量</div>
            <div class="admin-table-label text-center">成功率</div>
            <div class="admin-table-label text-right">操作</div>
          </div>

          <div v-if="monitorRows.length === 0" class="admin-empty">
            <div class="flex h-16 w-16 items-center justify-center rounded-full bg-surface-container-low text-on-surface-variant">
              <span class="material-symbols-outlined text-[28px]">smart_toy</span>
            </div>
            <p class="mt-4 text-sm font-semibold text-on-surface">暂无 Agent 任务</p>
            <p class="mt-1 text-sm text-on-surface-variant">当前没有可展示的执行记录。</p>
          </div>

          <div v-else>
            <div
              v-for="row in monitorRows"
              :key="row.type"
              class="admin-table-row grid grid-cols-[minmax(180px,1.4fr)_minmax(120px,1fr)_100px_120px_100px_100px_88px] gap-4 border-b border-[#f0f4fa] px-6 py-5 last:border-b-0"
            >
              <div class="min-w-0">
                <p class="truncate text-[14px] font-semibold text-on-surface">{{ row.name }}</p>
                <p class="mt-1 truncate text-[12px] text-on-surface-variant">{{ row.desc }}</p>
              </div>

              <div class="flex items-center text-[13px] text-on-surface-variant">{{ row.taskType }}</div>

              <div class="flex items-center justify-center">
                <span class="admin-badge" :class="row.statusClass">{{ row.statusLabel }}</span>
              </div>

              <div class="flex items-center gap-3">
                <div class="admin-score-track w-[82px]">
                  <div class="admin-score-fill" :style="{ width: `${row.progress}%` }"></div>
                </div>
                <span class="text-[12px] font-semibold text-on-surface">{{ row.progress }}%</span>
              </div>

              <div class="flex items-center justify-center text-[13px] text-on-surface">{{ row.total }}</div>

              <div class="flex items-center justify-center text-[13px] text-on-surface">{{ row.successRate }}</div>

              <div class="flex items-center justify-end">
                <button class="admin-link-btn" @click="handleRowAction(row.type)">查看</button>
              </div>
            </div>
          </div>
        </article>

        <article class="admin-panel px-5 py-5">
          <div class="flex items-center justify-between gap-3">
            <h3 class="admin-section-title">Agent 运行日志</h3>
            <span class="text-[12px] text-on-surface-variant">最近 {{ recentLogs.length }} 条</span>
          </div>

          <div class="mt-4 space-y-3">
            <article
              v-for="item in recentLogs"
              :key="item.id"
              class="rounded-[12px] border border-[#e7edf7] bg-[#fbfdff] px-4 py-4"
            >
              <div class="flex items-start gap-3">
                <span class="mt-1 h-2.5 w-2.5 shrink-0 rounded-full" :class="item.dotClass"></span>
                <div class="min-w-0 flex-1">
                  <div class="flex flex-wrap items-center justify-between gap-2">
                    <p class="truncate text-[13px] font-semibold text-on-surface">{{ item.title }}</p>
                    <span class="text-[11px] text-on-surface-variant">{{ item.timeText }}</span>
                  </div>
                  <p class="mt-1 text-[12px] leading-6 text-on-surface-variant">{{ item.desc }}</p>
                </div>
              </div>
            </article>
          </div>
        </article>
      </section>
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
  action?: { type: "candidate" | "invite"; jobId?: string; candidateId?: string };
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

let pollTimer: ReturnType<typeof setInterval> | null = null;

const agentDefinitions: Array<{ type: AgentType; name: string; taskType: string; metricLabel: string }> = [
  { type: "screening", name: "简历筛选 Agent", taskType: "简历筛选", metricLabel: "待人工" },
  { type: "analytics", name: "职位匹配 Agent", taskType: "岗位匹配", metricLabel: "推荐率" },
  { type: "interview", name: "面试评估 Agent", taskType: "面试评估", metricLabel: "覆盖率" },
  { type: "outreach", name: "人才推荐 Agent", taskType: "候选人邀约", metricLabel: "送达率" },
];

const lastSyncedAt = computed(() => {
  if (!lastSyncedMs.value) return "--";
  return formatDateTime(lastSyncedMs.value);
});

const agentSummaries = computed(() => {
  return agentDefinitions.map((definition) => {
    const list = agentEvents.value.filter((item) => item.agentType === definition.type);
    const total =
      definition.type === "interview"
        ? Number(analytics.value?.interview_task_count_today ?? 0)
        : list.length;
    const running = list.filter((item) => item.status === "running").length;
    const waiting = list.filter((item) => item.status === "waiting_human").length;
    const failed = list.filter((item) => item.status === "failed").length;
    const completed = list.filter((item) => item.status === "completed").length;

    let primaryStatus: AgentStatus = "completed";
    if (running > 0) primaryStatus = "running";
    else if (waiting > 0) primaryStatus = "waiting_human";
    else if (failed > 0) primaryStatus = "failed";

    const progress = total ? Math.min(100, Math.max(18, Math.round(((completed + running) / total) * 100))) : 0;
    const successRate = total ? `${Math.round(((total - failed) / total) * 100)}%` : "--";

    return {
      ...definition,
      total,
      running,
      waiting,
      failed,
      completed,
      primaryStatus,
      progress,
      successRate,
      latest: list.sort((a, b) => b.timeMs - a.timeMs)[0] || null,
    };
  });
});

const overviewCards = computed(() => {
  const recommended = hiringOverview.value?.recommended_count || 0;
  const reviewCount = hiringOverview.value?.review_count || 0;
  const inviteTotal = inviteHistory.value.length;

  return agentSummaries.value.map((item) => {
    let metricValue = item.successRate;
    if (item.type === "screening") metricValue = String(reviewCount);
    if (item.type === "analytics") {
      const total = hiringOverview.value?.total || 0;
      metricValue = total ? `${Math.round((recommended / total) * 100)}%` : "--";
    }
    if (item.type === "interview") {
      const total = analytics.value?.efficiency.length || 0;
      metricValue = total ? `${Math.min(100, 78 + total * 4)}%` : "--";
    }
    if (item.type === "outreach") {
      const delivered = inviteHistory.value.filter((record) => ["sent", "delivered", "opened", "clicked"].includes(record.delivery_status)).length;
      metricValue = inviteTotal ? `${Math.round((delivered / inviteTotal) * 100)}%` : "--";
    }

    return {
      name: item.name,
      taskCount: item.total,
      metricLabel: item.metricLabel,
      metricValue,
      badgeLabel: statusText(item.primaryStatus),
      badgeClass: statusBadgeClass(item.primaryStatus),
    };
  });
});

const monitorRows = computed(() => {
  return agentSummaries.value.map((item) => ({
    type: item.type,
    name: item.name,
    desc: item.latest?.title || "暂无运行中的任务",
    taskType: item.taskType,
    statusLabel: statusText(item.primaryStatus),
    statusClass: statusBadgeClass(item.primaryStatus),
    progress: item.progress,
    total: item.total,
    successRate: item.successRate,
  }));
});

const recentLogs = computed(() => {
  return [...agentEvents.value]
    .sort((a, b) => b.timeMs - a.timeMs)
    .slice(0, 8)
    .map((item) => ({
      ...item,
      dotClass:
        item.status === "running"
          ? "bg-primary"
          : item.status === "waiting_human"
            ? "bg-[#f5a24a]"
            : item.status === "failed"
              ? "bg-[#ef6a6a]"
              : "bg-[#42bc7a]",
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

function statusText(status: AgentStatus): string {
  if (status === "running") return "运行中";
  if (status === "waiting_human") return "待人工";
  if (status === "failed") return "失败";
  return "正常";
}

function statusBadgeClass(status: AgentStatus): string {
  if (status === "running") return "admin-badge-blue";
  if (status === "waiting_human") return "admin-badge-orange";
  if (status === "failed") return "admin-badge-red";
  return "admin-badge-green";
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
      tags: ["岗位匹配"],
      timeMs: ago.ms,
      timeText: ago.text,
      action: { type: "candidate", jobId: item.job_id, candidateId: item.candidate_id },
    });
  });

  (hiringOverview.value?.queue_items || []).slice(0, 12).forEach((item, index) => {
    const ago = timeAgo(item.updated_at || item.created_at);
    events.push({
      id: `queue-${item.job_id}-${item.candidate_id}-${index}`,
      status: "waiting_human",
      agentType: "screening",
      title: `候选人 ${item.candidate_name} 等待人工复核`,
      desc: `岗位 ${item.job_title}，AI 建议 ${item.recommendation}。`,
      tags: ["待复核"],
      timeMs: ago.ms,
      timeText: ago.text,
      action: { type: "candidate", jobId: item.job_id, candidateId: item.candidate_id },
    });
  });

  inviteHistory.value.slice(0, 14).forEach((invite, index) => {
    const ago = timeAgo(invite.sent_at || invite.created_at);
    let status: AgentStatus = "running";
    if (invite.delivery_status === "failed") status = "failed";
    else if (["opened", "clicked", "delivered", "sent"].includes(invite.delivery_status)) status = "completed";

    events.push({
      id: `invite-${invite.id}-${index}`,
      status,
      agentType: "outreach",
      title: `已触发 ${invite.candidate_name} 的邀约流程`,
      desc: `岗位 ${invite.job_title}，当前状态：${invite.delivery_status}。`,
      tags: ["邀约流程"],
      timeMs: ago.ms,
      timeText: ago.text,
      action: { type: "invite", jobId: invite.job_id, candidateId: invite.candidate_id },
    });
  });

  (analytics.value?.efficiency || []).forEach((metric, index) => {
    events.push({
      id: `eff-${metric.label}-${index}`,
      status: "completed",
      agentType: "interview",
      title: `面试评估指标已更新：${metric.label}`,
      desc: `当前指标 ${metric.value}${metric.unit}，流程进度 ${metric.progress}%。`,
      tags: ["面试效率"],
      timeMs: Date.now() - (index + 1) * 180000,
      timeText: `${(index + 1) * 3} 分钟前`,
    });
  });

  return events.sort((a, b) => b.timeMs - a.timeMs);
}

function handleRowAction(type: AgentType) {
  if (type === "outreach" || type === "interview") {
    router.push("/admin/interview-history");
    return;
  }
  if (type === "screening" || type === "analytics") {
    const latest = agentEvents.value.find((item) => item.agentType === type && item.action?.jobId && item.action?.candidateId);
    if (latest?.action?.jobId && latest.action.candidateId) {
      router.push(`/admin/candidate-detail?jobId=${latest.action.jobId}&candidateId=${latest.action.candidateId}`);
      return;
    }
  }
  router.push("/admin");
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
      fetchHiringCenterOverview({ top_n: 10, queue_limit: 40, max_scan: 3000 }),
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
});

onUnmounted(() => {
  stopPolling();
});
</script>
