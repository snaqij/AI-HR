<template>
  <div class="mx-auto max-w-7xl space-y-6 pb-10">
    <section class="rounded-2xl border border-outline-variant/20 bg-surface-container-lowest px-6 py-6">
      <div class="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p class="text-xs font-semibold uppercase tracking-widest text-primary">AI-HR Console</p>
          <h1 class="mt-2 text-3xl font-bold text-on-surface">招聘控制台</h1>
          <p class="mt-2 text-sm text-on-surface-variant">总览当前工作区的关键招聘指标与流程转化情况。</p>
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
          <p class="text-xs font-semibold text-on-surface-variant">整体转化率</p>
          <p class="mt-2 text-2xl font-bold text-on-surface">{{ weeklyConversion }}</p>
        </article>
        <article class="rounded-xl border border-outline-variant/20 bg-surface px-4 py-4">
          <p class="text-xs font-semibold text-on-surface-variant">AI 处理总量</p>
          <p class="mt-2 text-2xl font-bold text-on-surface">{{ analytics?.total_synced ?? 0 }}</p>
        </article>
        <article class="rounded-xl border border-outline-variant/20 bg-surface px-4 py-4">
          <p class="text-xs font-semibold text-on-surface-variant">AI累计省时</p>
          <p class="mt-2 flex items-end gap-2 text-on-surface">
            <span class="text-2xl font-bold">{{ aiSavedTime.value }}</span>
            <span class="pb-1 text-sm text-on-surface-variant">{{ aiSavedTime.unit }}</span>
          </p>
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
              <p class="mt-1 text-xs text-on-surface-variant">当前工作区实时统计</p>
            </div>
            <span class="rounded-full bg-primary/10 px-3 py-1 text-xs font-semibold text-primary">实时指标</span>
          </div>

          <div class="grid grid-cols-2 gap-3 md:grid-cols-4">
            <article v-for="step in analytics.funnel" :key="step.label" class="rounded-xl border border-outline-variant/15 bg-surface px-3 py-3">
              <p class="text-xs font-semibold text-on-surface-variant">{{ step.label }}</p>
              <p class="mt-1 text-2xl font-bold text-on-surface">{{ step.value }}</p>
              <p class="mt-1 text-xs text-emerald-600">
                {{ step.conversion || `${step.growth}%` }}
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
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import {
  fetchDashboardAnalytics,
  type DashboardAnalytics,
} from "../../api";

const analytics = ref<DashboardAnalytics | null>(null);

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

const aiSavedTime = computed(() => {
  const targetMetric = (analytics.value?.efficiency || []).find((metric) => {
    const label = String(metric.label || "");
    return label.includes("省时") || label.includes("节省");
  });
  if (targetMetric) {
    return {
      value: targetMetric.value,
      unit: targetMetric.unit,
    };
  }
  return {
    value: "--",
    unit: "",
  };
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

async function loadData(silent = false) {
  if (silent) {
    isRefreshing.value = true;
  } else {
    isLoading.value = true;
    loadError.value = "";
  }

  try {
    const analyticsData = await fetchDashboardAnalytics();
    analytics.value = analyticsData;
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
