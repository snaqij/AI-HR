<template>
  <div class="admin-page">
    <section v-if="isLoading" class="admin-panel px-8 py-16 text-center">
      <div class="mx-auto h-10 w-10 animate-spin rounded-full border-4 border-primary/20 border-t-primary"></div>
      <p class="mt-4 text-sm text-on-surface-variant">正在加载首页数据...</p>
    </section>

    <section v-else-if="loadError" class="admin-panel px-8 py-12 text-center">
      <p class="text-sm font-semibold text-on-error-container">{{ loadError }}</p>
      <button class="admin-primary-btn mt-5" @click="loadData">重新加载</button>
    </section>

    <template v-else>
      <section class="px-1">
        <h2 class="text-[30px] font-semibold tracking-tight text-on-surface">
          你好，{{ displayName }}
          <span class="ml-1 inline-block">👋</span>
        </h2>
        <p class="mt-2 text-[13px] text-on-surface-variant">欢迎使用 AI-HR，今天是 {{ todayText }}</p>

        <div class="mt-5 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-5">
          <article
            v-for="card in statCards"
            :key="card.label"
            class="rounded-[12px] border border-[#e7edf7] bg-white px-5 py-5 shadow-[0_10px_24px_-28px_rgba(41,71,121,0.45)]"
          >
            <div class="flex items-start justify-between gap-3">
              <div>
                <p class="text-[12px] text-on-surface-variant">{{ card.label }}</p>
                <p class="mt-3 text-[31px] font-semibold tracking-tight text-on-surface">{{ card.value }}</p>
                <p class="mt-2 text-[12px] text-on-surface-variant">
                  较昨日
                  <span :class="card.deltaClass">{{ card.delta }}</span>
                </p>
              </div>
              <div class="flex h-10 w-10 items-center justify-center rounded-full" :class="card.iconWrapClass">
                <span class="material-symbols-outlined text-[18px]" :class="card.iconClass">{{ card.icon }}</span>
              </div>
            </div>
          </article>
        </div>
      </section>

      <section class="grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,1.7fr)_minmax(320px,1fr)]">
        <article class="admin-panel px-6 py-5">
          <div class="mb-5 flex items-center justify-between gap-4">
            <h3 class="admin-section-title">招聘漏斗</h3>
            <div class="flex items-center gap-2">
              <span class="admin-badge admin-badge-blue">全部职位</span>
              <span class="admin-badge bg-[#f4f7fc] text-[#708099]">本月</span>
            </div>
          </div>

          <div class="rounded-[12px] bg-[#f8fbff] px-4 py-4">
            <svg viewBox="0 0 560 236" class="w-full" aria-label="招聘漏斗">
              <g v-for="item in funnelItems" :key="item.label">
                <polygon :points="item.points" :fill="item.fill" />
                <g :transform="`translate(332 ${item.y})`">
                  <text x="0" y="0" fill="#7c889a" font-size="13" dominant-baseline="middle">{{ item.label }}</text>
                  <text x="104" y="0" fill="#1f2d3d" font-size="13" font-weight="700" dominant-baseline="middle">
                    {{ item.value }}
                  </text>
                  <text x="178" y="0" fill="#7c889a" font-size="12" dominant-baseline="middle">
                    {{ item.percent }}
                  </text>
                </g>
              </g>
            </svg>
          </div>
        </article>

        <article class="admin-panel px-6 py-5">
          <div class="flex items-center justify-between gap-3">
            <h3 class="admin-section-title">待办事项</h3>
            <span class="admin-badge admin-badge-red">{{ urgentTodoCount }} 项待处理</span>
          </div>

          <div class="mt-4 space-y-3">
            <div
              v-for="item in todoItems"
              :key="item.label"
              class="flex items-center justify-between gap-3 rounded-[12px] bg-[#f8fbff] px-4 py-3"
            >
              <div class="flex min-w-0 items-center gap-3">
                <div class="flex h-8 w-8 items-center justify-center rounded-full" :class="item.iconWrapClass">
                  <span class="material-symbols-outlined text-[16px]" :class="item.iconClass">{{ item.icon }}</span>
                </div>
                <span class="truncate text-[13px] text-on-surface">{{ item.label }}</span>
              </div>
              <span class="admin-badge" :class="item.badgeClass">{{ item.value }}</span>
            </div>
          </div>
        </article>
      </section>

      <section class="admin-panel bg-[#f7fbff] px-6 py-4">
        <div class="flex items-center gap-2">
          <span class="text-[13px] font-semibold text-primary">AI 助手建议</span>
        </div>
        <div class="mt-4 grid grid-cols-1 gap-3 xl:grid-cols-3">
          <article
            v-for="item in assistantCards"
            :key="item.title"
            class="rounded-[12px] border border-[#e5edfb] bg-white px-4 py-4"
          >
            <div class="flex items-start gap-3">
              <div class="flex h-9 w-9 items-center justify-center rounded-[10px] bg-[#eef4ff] text-primary">
                <span class="material-symbols-outlined text-[18px]">{{ item.icon }}</span>
              </div>
              <div class="min-w-0 flex-1">
                <p class="text-[13px] leading-6 text-on-surface">{{ item.title }}</p>
                <button class="mt-3 rounded-[8px] border border-[#dbe6fb] bg-[#f8fbff] px-3 py-1 text-[12px] font-semibold text-primary">
                  {{ item.action }}
                </button>
              </div>
            </div>
          </article>
        </div>
      </section>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import {
  fetchDashboardAnalytics,
  fetchHiringCenterOverview,
  fetchInterviewInvitationHistory,
  listJobs,
  type DashboardAnalytics,
  type HiringCenterOverviewResult,
  type InterviewInvitationHistoryItem,
  type Job,
} from "../../api";
import { useAuthStore } from "../../stores/auth";

type StatCard = {
  label: string;
  value: string;
  delta: string;
  deltaClass: string;
  icon: string;
  iconWrapClass: string;
  iconClass: string;
};

type TodoItem = {
  label: string;
  value: string;
  icon: string;
  iconWrapClass: string;
  iconClass: string;
  badgeClass: string;
};

type AssistantCard = {
  title: string;
  action: string;
  icon: string;
};

type FunnelLayer = {
  label: string;
  value: string;
  percent: string;
  fill: string;
  points: string;
  y: number;
};

const auth = useAuthStore();

const analytics = ref<DashboardAnalytics | null>(null);
const jobs = ref<Job[]>([]);
const hiringOverview = ref<HiringCenterOverviewResult | null>(null);
const invites = ref<InterviewInvitationHistoryItem[]>([]);

const isLoading = ref(true);
const loadError = ref("");

const displayName = computed(() => auth.displayName || auth.email || "张管理员");
const todayText = computed(() => {
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "numeric",
    day: "numeric",
    weekday: "long",
  }).format(new Date());
});

const totalJobs = computed(() => jobs.value.length);
const totalCandidates = computed(() => jobs.value.reduce((sum, job) => sum + Number(job.candidate_count || 0), 0));
const totalInterviews = computed(() => invites.value.length);
const totalOffers = computed(() => hiringOverview.value?.invited_count || 0);
const monthlyHiring = computed(() => hiringOverview.value?.recommended_count || 0);
const reviewCount = computed(() => hiringOverview.value?.review_count || 0);
const activeInviteCount = computed(() => invites.value.filter((item) => item.delivery_status !== "failed").length);
const dashboardDeltas = computed(() => analytics.value?.daily_deltas);

const funnelItems = computed<FunnelLayer[]>(() => {
  const raw = analytics.value?.funnel || [];
  const applied = Number(raw[0]?.value || totalCandidates.value || 0);
  const screened = Number(raw[1]?.value || Math.max(Math.round(applied * 0.52), totalInterviews.value));
  const interviewed = Number(raw[2]?.value || totalInterviews.value || 0);
  const offer = Number(raw[3]?.value || totalOffers.value || 0);
  const hired = Number(raw[4]?.value || monthlyHiring.value || 0);

  return [
    { label: "投递", value: formatNumber(applied), percent: "100%", fill: "#dceaff", points: "28,16 290,16 262,56 56,56", y: 36 },
    { label: "简历筛选", value: formatNumber(screened), percent: percentText(screened, applied), fill: "#c8ddff", points: "56,56 262,56 234,96 84,96", y: 76 },
    { label: "面试", value: formatNumber(interviewed), percent: percentText(interviewed, applied), fill: "#b3d4ff", points: "84,96 234,96 206,136 112,136", y: 116 },
    { label: "Offer", value: formatNumber(offer), percent: percentText(offer, applied), fill: "#9dc7f6", points: "112,136 206,136 188,176 130,176", y: 156 },
    { label: "已入职", value: formatNumber(hired), percent: percentText(hired, applied), fill: "#9bdfdf", points: "130,176 188,176 188,216 130,216", y: 196 },
  ];
});

const statCards = computed<StatCard[]>(() => [
  {
    label: "在招职位",
    value: formatNumber(totalJobs.value),
    delta: formatDelta(Number(dashboardDeltas.value?.open_jobs ?? 0)),
    deltaClass: deltaClass(Number(dashboardDeltas.value?.open_jobs ?? 0)),
    icon: "work_outline",
    iconWrapClass: "bg-[#eef4ff]",
    iconClass: "text-primary",
  },
  {
    label: "候选人总数",
    value: formatNumber(totalCandidates.value),
    delta: formatDelta(Number(dashboardDeltas.value?.total_candidates ?? 0)),
    deltaClass: deltaClass(Number(dashboardDeltas.value?.total_candidates ?? 0)),
    icon: "group",
    iconWrapClass: "bg-[#e9f8ef]",
    iconClass: "text-[#42bc7a]",
  },
  {
    label: "待面试",
    value: formatNumber(reviewCount.value),
    delta: formatDelta(Number(dashboardDeltas.value?.pending_interviews ?? 0)),
    deltaClass: deltaClass(Number(dashboardDeltas.value?.pending_interviews ?? 0)),
    icon: "calendar_month",
    iconWrapClass: "bg-[#fff4e8]",
    iconClass: "text-[#f5a24a]",
  },
  {
    label: "待处理邀约",
    value: formatNumber(totalInterviews.value),
    delta: formatDelta(Number(dashboardDeltas.value?.pending_invitations ?? 0)),
    deltaClass: deltaClass(Number(dashboardDeltas.value?.pending_invitations ?? 0)),
    icon: "mail",
    iconWrapClass: "bg-[#f2edff]",
    iconClass: "text-[#9b7af3]",
  },
  {
    label: "本月录用",
    value: formatNumber(monthlyHiring.value),
    delta: formatDelta(Number(dashboardDeltas.value?.monthly_hires ?? 0)),
    deltaClass: deltaClass(Number(dashboardDeltas.value?.monthly_hires ?? 0)),
    icon: "verified",
    iconWrapClass: "bg-[#e9f8ef]",
    iconClass: "text-[#42bc7a]",
  },
]);

const todoItems = computed<TodoItem[]>(() => [
  {
    label: "待确认候选人简历",
    value: formatNumber(reviewCount.value),
    icon: "description",
    iconWrapClass: "bg-[#eef4ff]",
    iconClass: "text-primary",
    badgeClass: "admin-badge-blue",
  },
  {
    label: "待安排面试",
    value: formatNumber(totalInterviews.value),
    icon: "calendar_today",
    iconWrapClass: "bg-[#fff4e8]",
    iconClass: "text-[#f5a24a]",
    badgeClass: "admin-badge-orange",
  },
  {
    label: "待发送邀约",
    value: formatNumber(Math.max(totalOffers.value - monthlyHiring.value, 0)),
    icon: "mark_email_read",
    iconWrapClass: "bg-[#e9f8ef]",
    iconClass: "text-[#42bc7a]",
    badgeClass: "admin-badge-green",
  },
  {
    label: "待处理面试反馈",
    value: formatNumber(activeInviteCount.value),
    icon: "rate_review",
    iconWrapClass: "bg-[#f2edff]",
    iconClass: "text-[#9b7af3]",
    badgeClass: "admin-badge-violet",
  },
  {
    label: "待完成录用审批",
    value: formatNumber(totalOffers.value),
    icon: "task_alt",
    iconWrapClass: "bg-[#f3f6fb]",
    iconClass: "text-[#708099]",
    badgeClass: "bg-[#f3f6fb] text-[#708099]",
  },
]);

const urgentTodoCount = computed(() => {
  return todoItems.value.filter((item) => Number(item.value.replace(/,/g, "")) > 0).length;
});

const assistantCards = computed<AssistantCard[]>(() => {
  const highMatchCount = Math.max(12, Math.min(totalCandidates.value, 48));
  return [
    {
      title: `有 ${highMatchCount} 位候选人与岗位高度匹配，建议优先安排面试。`,
      action: "立即跟进",
      icon: "diamond",
    },
    {
      title: "产品经理岗位的候选人转化率偏低，建议优化职位描述与筛选条件。",
      action: "查看分析",
      icon: "description",
    },
    {
      title: "本周面试安排较为密集，建议调整邀约节奏并及时收集反馈。",
      action: "立即启用",
      icon: "notifications",
    },
  ];
});

function formatNumber(value: number): string {
  return new Intl.NumberFormat("zh-CN").format(Number(value || 0));
}

function percentText(value: number, total: number): string {
  if (!total) return "0.0%";
  return `${((value / total) * 100).toFixed(1)}%`;
}

function formatDelta(value: number): string {
  if (value > 0) {
    return `+${value}`;
  }
  return String(value);
}

function deltaClass(value: number): string {
  if (value > 0) {
    return "text-[#42bc7a]";
  }
  if (value < 0) {
    return "text-[#8a95a8]";
  }
  return "text-[#708099]";
}

async function loadData(): Promise<void> {
  isLoading.value = true;
  loadError.value = "";
  try {
    const [analyticsData, jobsData, hiringData, inviteData] = await Promise.all([
      fetchDashboardAnalytics(),
      listJobs(100),
      fetchHiringCenterOverview({ top_n: 10, queue_limit: 20, max_scan: 3000 }),
      fetchInterviewInvitationHistory({ limit: 50 }),
    ]);
    analytics.value = analyticsData;
    jobs.value = jobsData;
    hiringOverview.value = hiringData;
    invites.value = inviteData.items || [];
  } catch (error) {
    console.error("Failed to load dashboard data", error);
    loadError.value = "加载首页数据失败，请稍后重试。";
  } finally {
    isLoading.value = false;
  }
}

onMounted(() => {
  loadData();
});
</script>
