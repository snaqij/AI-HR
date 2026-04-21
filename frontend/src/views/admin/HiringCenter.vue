<template>
  <div class="mx-auto flex w-full max-w-7xl flex-col gap-6 pb-10">
    <header class="rounded-2xl border border-outline-variant/15 bg-surface-container-lowest px-6 py-5">
      <div class="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 class="text-2xl font-bold text-on-surface">录用决策中心</h1>
          <p class="mt-1 text-sm text-on-surface-variant">聚焦待处理候选人，快速完成复核、推进与邀约决策。</p>
        </div>
        <button
          class="inline-flex h-10 items-center gap-2 rounded-lg border border-outline-variant/30 bg-surface-container-low px-4 text-sm font-semibold text-on-surface-variant transition-colors hover:bg-surface-container disabled:opacity-50"
          :disabled="isLoading"
          @click="loadData"
        >
          <span class="material-symbols-outlined text-base" :class="{ 'animate-spin': isLoading }">refresh</span>
          刷新数据
        </button>
      </div>
    </header>

    <section class="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <button
        v-for="stat in summaryStats"
        :key="stat.label"
        class="rounded-xl border px-4 py-4 text-left transition-colors"
        :class="[
          stat.clickable
            ? activeMetric === stat.metric
              ? 'border-primary/40 bg-primary/5'
              : 'border-outline-variant/20 bg-surface-container-lowest hover:bg-surface-container-low'
            : 'border-outline-variant/20 bg-surface-container-lowest'
        ]"
        :disabled="!stat.clickable"
        @click="stat.clickable && (activeMetric = stat.metric)"
      >
        <p class="text-xs font-semibold text-on-surface-variant">{{ stat.label }}</p>
        <p class="mt-2 text-2xl font-bold text-on-surface">{{ stat.value }}</p>
        <p class="mt-1 text-xs" :class="stat.subValueColor">{{ stat.subValue }}</p>
      </button>
    </section>

    <section v-if="isLoading" class="rounded-2xl border border-outline-variant/15 bg-surface-container-lowest px-6 py-12 text-center">
      <div class="mx-auto mb-3 h-10 w-10 animate-spin rounded-full border-4 border-primary/20 border-t-primary"></div>
      <p class="text-sm font-medium text-on-surface-variant">正在加载录用决策数据...</p>
    </section>

    <section v-else-if="loadError" class="rounded-2xl border border-error/20 bg-error-container/40 px-6 py-8">
      <p class="text-sm font-semibold text-on-error-container">{{ loadError }}</p>
      <button
        class="mt-4 h-10 rounded-lg border border-on-error-container/20 bg-white px-4 text-sm font-semibold text-on-error-container"
        @click="loadData"
      >
        重试
      </button>
    </section>

    <template v-else>
      <section class="rounded-2xl border border-outline-variant/15 bg-surface-container-lowest px-6 py-5">
        <div class="mb-4 flex flex-wrap items-center justify-between gap-3">
          <h2 class="text-base font-semibold text-on-surface">高优先级候选人</h2>
          <p class="text-xs text-on-surface-variant">当前展示 {{ visibleDecisionCards.length }} 人</p>
        </div>

        <div v-if="visibleDecisionCards.length" class="grid grid-cols-1 gap-4 xl:grid-cols-3">
          <article
            v-for="card in visibleDecisionCards"
            :key="card.key"
            class="rounded-xl border border-outline-variant/20 bg-surface px-4 py-4"
          >
            <div class="flex items-start justify-between gap-3">
              <div class="min-w-0">
                <p class="truncate text-base font-semibold text-on-surface">{{ card.name }}</p>
                <p class="truncate text-sm text-on-surface-variant">{{ card.title }}</p>
              </div>
              <span class="rounded-full px-2 py-1 text-xs font-semibold" :class="card.tagClass">{{ card.tagLabel }}</span>
            </div>

            <div class="mt-4 flex items-end justify-between gap-3">
              <div>
                <p class="text-xs text-on-surface-variant">AI 评分</p>
                <p class="text-3xl font-bold text-on-surface">{{ card.score }}</p>
              </div>
              <div class="text-right">
                <p class="text-xs text-on-surface-variant">更新时间</p>
                <p class="text-sm font-medium text-on-surface">{{ card.date }}</p>
              </div>
            </div>

            <p class="summary-clamp mt-4 text-sm leading-6 text-on-surface-variant">{{ card.aiInsight }}</p>

            <div class="mt-4 grid grid-cols-2 gap-2">
              <button
                class="h-10 rounded-lg bg-primary px-3 text-sm font-semibold text-white"
                @click="openCandidate(card.jobId, card.candidateId)"
              >
                进入详情决策
              </button>
              <button
                class="h-10 rounded-lg border border-outline-variant/30 bg-surface-container-low px-3 text-sm font-semibold text-on-surface-variant"
                @click="focusQueue(card.name)"
              >
                定位队列
              </button>
            </div>
          </article>
        </div>

        <div v-else class="rounded-lg border border-dashed border-outline-variant/35 px-4 py-8 text-center text-sm text-on-surface-variant">
          当前筛选条件下暂无高优先级候选人。
        </div>
      </section>

      <section id="decision-queue" class="rounded-2xl border border-outline-variant/15 bg-surface-container-lowest px-6 py-5">
        <div class="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 class="text-base font-semibold text-on-surface">待处理决策队列</h2>
            <p class="mt-1 text-xs text-on-surface-variant">按优先级处理待复核与待推进候选人。</p>
          </div>
          <p class="text-xs text-on-surface-variant">共 {{ filteredQueue.length }} 条</p>
        </div>

        <div class="mb-4 grid grid-cols-1 gap-3 lg:grid-cols-4">
          <div class="lg:col-span-2">
            <input
              v-model.trim="keyword"
              type="text"
              placeholder="搜索候选人/岗位"
              class="h-10 w-full rounded-lg border border-outline-variant/30 bg-white px-3 text-sm text-on-surface focus:border-primary focus:outline-none"
            >
          </div>
          <select
            v-model="recommendationFilter"
            class="h-10 rounded-lg border border-outline-variant/30 bg-white px-3 text-sm text-on-surface focus:border-primary focus:outline-none"
          >
            <option value="all">全部推荐状态</option>
            <option value="strong_recommend">强烈推荐</option>
            <option value="recommend">推荐</option>
            <option value="review">待复核</option>
            <option value="reject">不推荐</option>
          </select>
          <select
            v-model="sortBy"
            class="h-10 rounded-lg border border-outline-variant/30 bg-white px-3 text-sm text-on-surface focus:border-primary focus:outline-none"
          >
            <option value="score_desc">评分从高到低</option>
            <option value="score_asc">评分从低到高</option>
            <option value="updated_desc">最近更新优先</option>
            <option value="updated_asc">最早更新优先</option>
          </select>
        </div>

        <div class="overflow-x-auto rounded-xl border border-outline-variant/20">
          <table class="min-w-full text-left">
            <thead class="bg-surface-container-low">
              <tr>
                <th class="px-4 py-3 text-xs font-semibold text-on-surface-variant">候选人</th>
                <th class="px-4 py-3 text-xs font-semibold text-on-surface-variant">岗位</th>
                <th class="px-4 py-3 text-xs font-semibold text-on-surface-variant">推荐结论</th>
                <th class="px-4 py-3 text-xs font-semibold text-on-surface-variant">评分</th>
                <th class="px-4 py-3 text-xs font-semibold text-on-surface-variant">更新时间</th>
                <th class="px-4 py-3 text-xs font-semibold text-on-surface-variant text-right">操作</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-outline-variant/15 bg-white">
              <tr v-for="item in filteredQueue" :key="item.key" class="hover:bg-surface-container-low/40">
                <td class="px-4 py-3">
                  <div class="flex items-center gap-3">
                    <div class="flex h-9 w-9 items-center justify-center rounded-lg bg-surface-container-low text-xs font-semibold text-on-surface-variant">
                      {{ item.initials }}
                    </div>
                    <div>
                      <p class="text-sm font-semibold text-on-surface">{{ item.name }}</p>
                      <p class="text-xs text-on-surface-variant">{{ item.salary }}</p>
                    </div>
                  </div>
                </td>
                <td class="px-4 py-3 text-sm text-on-surface-variant">{{ item.job }}</td>
                <td class="px-4 py-3">
                  <span class="rounded-full px-2 py-1 text-xs font-semibold" :class="item.recommendationClass">{{ item.analysis }}</span>
                </td>
                <td class="px-4 py-3 text-sm font-semibold text-on-surface">{{ item.scoreText }}</td>
                <td class="px-4 py-3 text-sm text-on-surface-variant">{{ item.updatedAtText }}</td>
                <td class="px-4 py-3 text-right">
                  <button class="h-9 rounded-lg bg-primary px-3 text-xs font-semibold text-white" @click="openCandidate(item.jobId, item.candidateId)">
                    立即处理
                  </button>
                </td>
              </tr>
              <tr v-if="!filteredQueue.length">
                <td colspan="6" class="px-4 py-10 text-center text-sm text-on-surface-variant">当前条件下没有待处理决策。</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import {
  fetchHiringCenterOverview,
  type HiringCenterEvaluationItem,
  type HiringCenterOverviewResult,
} from "../../api";

type MetricFilter = "all" | "review" | "recommended" | "invited";

type DecisionCard = {
  key: string;
  candidateId: string;
  jobId: string;
  name: string;
  title: string;
  aiInsight: string;
  score: string;
  date: string;
  tagLabel: string;
  tagClass: string;
  recommendation: string;
  invited: boolean;
};

type QueueItem = {
  key: string;
  candidateId: string;
  jobId: string;
  initials: string;
  name: string;
  job: string;
  salary: string;
  score: number;
  scoreText: string;
  analysis: string;
  recommendation: string;
  recommendationClass: string;
  updatedAt: number;
  updatedAtText: string;
  invited: boolean;
};

const router = useRouter();

const isLoading = ref(false);
const loadError = ref("");
const overview = ref<HiringCenterOverviewResult | null>(null);
const rawDecisionCards = ref<DecisionCard[]>([]);
const rawQueue = ref<QueueItem[]>([]);

const activeMetric = ref<MetricFilter>("review");
const keyword = ref("");
const recommendationFilter = ref("all");
const sortBy = ref("score_desc");

const summaryStats = computed(() => {
  const snapshot = overview.value;
  const total = snapshot?.total || 0;
  const reviewCount = snapshot?.review_count || 0;
  const invitedCount = snapshot?.invited_count || 0;
  const recommendedCount = snapshot?.recommended_count || 0;
  const conversion = String(snapshot?.conversion_rate ?? 0);

  return [
    {
      label: "待处理决策",
      value: String(reviewCount).padStart(2, "0"),
      subValue: `总计 ${total}`,
      subValueColor: "text-primary",
      metric: "review" as MetricFilter,
      clickable: true,
    },
    {
      label: "已发面试邀约",
      value: String(invitedCount).padStart(2, "0"),
      subValue: `${recommendedCount} 人推荐`,
      subValueColor: "text-emerald-600",
      metric: "invited" as MetricFilter,
      clickable: true,
    },
    {
      label: "高优先级候选人",
      value: String(recommendedCount).padStart(2, "0"),
      subValue: "来自评估结果",
      subValueColor: "text-on-surface-variant",
      metric: "recommended" as MetricFilter,
      clickable: true,
    },
    {
      label: "邀约转化率",
      value: `${conversion}%`,
      subValue: "基于数据库数据",
      subValueColor: "text-emerald-600",
      metric: "all" as MetricFilter,
      clickable: false,
    },
  ];
});

const filteredQueue = computed(() => {
  let list = [...rawQueue.value];

  list = list.filter((item) => matchMetric(item.recommendation, item.invited));

  const kw = keyword.value.trim().toLowerCase();
  if (kw) {
    list = list.filter((item) => {
      return item.name.toLowerCase().includes(kw) || item.job.toLowerCase().includes(kw);
    });
  }

  if (recommendationFilter.value !== "all") {
    list = list.filter((item) => item.recommendation === recommendationFilter.value);
  }

  switch (sortBy.value) {
    case "score_asc":
      list.sort((a, b) => a.score - b.score);
      break;
    case "updated_desc":
      list.sort((a, b) => b.updatedAt - a.updatedAt);
      break;
    case "updated_asc":
      list.sort((a, b) => a.updatedAt - b.updatedAt);
      break;
    case "score_desc":
    default:
      list.sort((a, b) => b.score - a.score);
      break;
  }

  return list;
});

const visibleDecisionCards = computed(() => {
  let list = [...rawDecisionCards.value].filter((item) => matchMetric(item.recommendation, item.invited));

  const kw = keyword.value.trim().toLowerCase();
  if (kw) {
    list = list.filter((item) => item.name.toLowerCase().includes(kw) || item.title.toLowerCase().includes(kw));
  }

  if (recommendationFilter.value !== "all") {
    list = list.filter((item) => item.recommendation === recommendationFilter.value);
  }

  return list.slice(0, 3);
});

function matchMetric(recommendation: string, invited: boolean) {
  if (activeMetric.value === "review") {
    return recommendation === "review";
  }
  if (activeMetric.value === "recommended") {
    return recommendation === "recommend" || recommendation === "strong_recommend";
  }
  if (activeMetric.value === "invited") {
    return invited;
  }
  return true;
}

function toInitials(name: string): string {
  const raw = (name || "").trim();
  if (!raw) {
    return "NA";
  }
  if (/^[\u4e00-\u9fa5]+$/.test(raw)) {
    return raw.slice(0, 2);
  }
  const parts = raw.split(/\s+/).filter(Boolean);
  if (!parts.length) {
    return raw.slice(0, 2).toUpperCase();
  }
  return parts.slice(0, 2).map((s) => s.slice(0, 1).toUpperCase()).join("");
}

function formatSalary(value?: string | null): string {
  const text = (value || "").trim();
  return text || "待沟通";
}

function toTimestamp(value?: string | null): number {
  const d = new Date(value || "");
  const ts = d.getTime();
  return Number.isNaN(ts) ? 0 : ts;
}

function formatDateTime(value?: string | null): string {
  if (!value) {
    return "--";
  }
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) {
    return "--";
  }
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(d);
}

function recommendationMeta(recommendation: string): { label: string; cardClass: string; queueClass: string } {
  if (recommendation === "strong_recommend") {
    return { label: "强烈推荐", cardClass: "bg-emerald-100 text-emerald-700", queueClass: "bg-emerald-50 text-emerald-700" };
  }
  if (recommendation === "recommend") {
    return { label: "推荐", cardClass: "bg-blue-100 text-blue-700", queueClass: "bg-blue-50 text-blue-700" };
  }
  if (recommendation === "reject") {
    return { label: "不推荐", cardClass: "bg-rose-100 text-rose-700", queueClass: "bg-rose-50 text-rose-700" };
  }
  return { label: "待复核", cardClass: "bg-amber-100 text-amber-700", queueClass: "bg-amber-50 text-amber-700" };
}

function toCard(item: HiringCenterEvaluationItem): DecisionCard {
  const meta = recommendationMeta(item.recommendation);
  return {
    key: `${item.job_id}-${item.candidate_id}`,
    candidateId: item.candidate_id,
    jobId: item.job_id,
    name: item.candidate_name,
    title: item.job_title,
    aiInsight: item.summary || item.candidate_score_explanation || "暂无评估摘要，建议人工查看关键维度后决策。",
    score: Number(item.final_score || 0).toFixed(1),
    date: formatDateTime(item.updated_at || item.created_at),
    tagLabel: meta.label,
    tagClass: meta.cardClass,
    recommendation: item.recommendation,
    invited: Boolean(item.invited_flag),
  };
}

function toQueueItem(item: HiringCenterEvaluationItem): QueueItem {
  const score = Number(item.final_score || 0);
  const meta = recommendationMeta(item.recommendation);
  const updated = item.updated_at || item.created_at;

  return {
    key: `${item.job_id}-${item.candidate_id}`,
    candidateId: item.candidate_id,
    jobId: item.job_id,
    initials: toInitials(item.candidate_name),
    name: item.candidate_name,
    job: item.job_title,
    salary: formatSalary(item.candidate_expected_salary || item.job_salary_range),
    score,
    scoreText: score.toFixed(1),
    analysis: meta.label,
    recommendation: item.recommendation,
    recommendationClass: meta.queueClass,
    updatedAt: toTimestamp(updated),
    updatedAtText: formatDateTime(updated),
    invited: Boolean(item.invited_flag),
  };
}

function focusQueue(keywordValue: string) {
  keyword.value = keywordValue;
  const el = document.getElementById("decision-queue");
  if (el) {
    el.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

function openCandidate(jobId: string, candidateId: string) {
  router.push(`/admin/candidate-detail?jobId=${jobId}&candidateId=${candidateId}`);
}

async function loadData() {
  isLoading.value = true;
  loadError.value = "";
  try {
    const result = await fetchHiringCenterOverview({ top_n: 6, queue_limit: 50, max_scan: 3000 });
    overview.value = result;
    rawDecisionCards.value = (result.top_items || []).map(toCard);
    rawQueue.value = (result.queue_items || []).map(toQueueItem);
  } catch (error) {
    console.error("Failed to load hiring center data", error);
    loadError.value = "加载录用决策数据失败，请稍后重试。";
    overview.value = null;
    rawDecisionCards.value = [];
    rawQueue.value = [];
  } finally {
    isLoading.value = false;
  }
}

onMounted(loadData);
</script>

<style scoped>
.summary-clamp {
  display: -webkit-box;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
}
</style>
