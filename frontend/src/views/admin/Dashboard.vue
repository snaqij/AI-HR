<template>
  <div class="mx-auto max-w-7xl space-y-8">
    <section class="relative overflow-hidden rounded-3xl border border-outline-variant/20 bg-gradient-to-br from-surface-container-lowest via-surface-container-low to-surface-container-high p-6 md:p-8">
      <div class="pointer-events-none absolute -right-14 -top-14 h-56 w-56 rounded-full bg-primary/10 blur-3xl"></div>
      <div class="pointer-events-none absolute -bottom-20 left-1/3 h-72 w-72 rounded-full bg-tertiary/10 blur-3xl"></div>

      <div class="relative flex flex-col gap-5 md:flex-row md:items-end md:justify-between">
        <div>
          <p class="text-xs font-black uppercase tracking-[0.2em] text-primary">AI-HR Dashboard</p>
          <h1 class="mt-2 text-3xl font-black tracking-tight text-on-surface md:text-4xl">控制台总览</h1>
          <p class="mt-2 text-sm text-on-surface-variant">实时查看招聘漏斗、AI效率和待处理任务，快速推进关键招聘流程。</p>
        </div>
        <div class="flex flex-wrap items-center gap-3">
          <button class="rounded-xl bg-surface-container-high px-5 py-2.5 text-sm font-bold text-on-surface transition-colors hover:bg-outline-variant/30">
            下载报表
          </button>
          <button class="rounded-xl ai-gradient px-5 py-2.5 text-sm font-bold text-white shadow-lg transition-transform hover:scale-[1.02]">
            发布新职位
          </button>
        </div>
      </div>

      <div class="relative mt-6 grid grid-cols-1 gap-3 md:grid-cols-3">
        <article class="rounded-2xl border border-outline-variant/15 bg-surface/70 p-4 backdrop-blur">
          <p class="text-xs font-bold uppercase tracking-widest text-on-surface-variant">候选人总数</p>
          <p class="mt-2 text-3xl font-black text-on-surface">{{ totalCandidates }}</p>
        </article>
        <article class="rounded-2xl border border-outline-variant/15 bg-surface/70 p-4 backdrop-blur">
          <p class="text-xs font-bold uppercase tracking-widest text-on-surface-variant">本周转化率</p>
          <p class="mt-2 text-3xl font-black text-on-surface">{{ weeklyConversion }}</p>
        </article>
        <article class="rounded-2xl border border-outline-variant/15 bg-surface/70 p-4 backdrop-blur">
          <p class="text-xs font-bold uppercase tracking-widest text-on-surface-variant">AI处理总量</p>
          <p class="mt-2 text-3xl font-black text-on-surface">{{ analytics?.total_synced ?? 0 }}</p>
        </article>
      </div>
    </section>

    <div v-if="isLoading" class="grid grid-cols-1 gap-6 lg:grid-cols-12">
      <section class="lg:col-span-8 animate-pulse rounded-2xl border border-outline-variant/15 bg-surface-container-lowest p-6">
        <div class="mb-4 h-6 w-48 rounded bg-surface-container-high"></div>
        <div class="h-64 rounded-xl bg-surface-container-low"></div>
      </section>
      <section class="lg:col-span-4 animate-pulse rounded-2xl border border-outline-variant/15 bg-surface-container-lowest p-6">
        <div class="mb-4 h-6 w-40 rounded bg-surface-container-high"></div>
        <div class="space-y-4">
          <div class="h-20 rounded-xl bg-surface-container-low"></div>
          <div class="h-20 rounded-xl bg-surface-container-low"></div>
          <div class="h-20 rounded-xl bg-surface-container-low"></div>
        </div>
      </section>
    </div>

    <div v-else-if="analytics" class="grid grid-cols-1 gap-6 lg:grid-cols-12">
      <section class="lg:col-span-8 rounded-2xl border border-outline-variant/15 bg-surface-container-lowest p-6 shadow-sm">
        <div class="mb-6 flex items-start justify-between gap-4">
          <div>
            <h3 class="text-xl font-black text-on-surface">招聘漏斗分析</h3>
            <p class="mt-1 text-xs font-bold uppercase tracking-widest text-on-surface-variant">最近30天数据</p>
          </div>
          <span class="rounded-full border border-primary/20 bg-primary/5 px-3 py-1 text-xs font-bold text-primary">实时更新</span>
        </div>

        <div class="grid grid-cols-2 gap-3 md:grid-cols-4">
          <article
            v-for="step in analytics.funnel"
            :key="step.label"
            class="rounded-2xl border border-outline-variant/10 bg-surface-container-low p-3"
          >
            <p class="text-xs font-bold uppercase tracking-widest text-on-surface-variant">{{ step.label }}</p>
            <p class="mt-2 text-2xl font-black text-on-surface">{{ step.value }}</p>
            <p v-if="step.conversion" class="mt-1 text-xs font-bold text-primary">{{ step.conversion }} 转化</p>
            <div class="mt-3 flex items-center text-xs font-bold" :class="step.growth >= 0 ? 'text-green-600' : 'text-rose-600'">
              <span class="material-symbols-outlined text-sm">{{ step.growth >= 0 ? 'trending_up' : 'trending_down' }}</span>
              <span>{{ step.growth >= 0 ? '+' : '' }}{{ step.growth }}%</span>
            </div>
          </article>
        </div>

        <div class="mt-6 flex h-56 items-end gap-3 rounded-2xl border border-outline-variant/10 bg-surface p-4">
          <div v-for="step in analytics.funnel" :key="`${step.label}-bar`" class="flex h-full flex-1 flex-col items-center justify-end gap-2">
            <div class="w-full rounded-lg ai-gradient" :style="{ height: step.height, opacity: step.opacity }"></div>
            <span class="text-[11px] font-bold text-on-surface-variant">{{ step.label }}</span>
          </div>
        </div>
      </section>

      <section class="lg:col-span-4 rounded-2xl border border-outline-variant/15 bg-surface-container-lowest p-6 shadow-sm">
        <h3 class="text-xl font-black text-on-surface">AI效率看板</h3>
        <p class="mt-1 text-xs font-bold uppercase tracking-widest text-on-surface-variant">流程自动化表现</p>

        <div class="mt-5 space-y-4">
          <article v-for="metric in analytics.efficiency" :key="metric.label" class="rounded-2xl border border-outline-variant/10 bg-surface p-4">
            <p class="text-xs font-bold uppercase tracking-widest text-on-surface-variant">{{ metric.label }}</p>
            <div class="mt-2 flex items-end gap-2">
              <span class="text-4xl font-black text-tertiary">{{ metric.value }}</span>
              <span class="pb-1 text-sm font-bold text-on-surface-variant">{{ metric.unit }}</span>
            </div>
            <div class="mt-3 h-2 overflow-hidden rounded-full bg-surface-container-high">
              <div class="h-full rounded-full bg-tertiary" :style="{ width: `${metric.progress}%` }"></div>
            </div>
          </article>
        </div>
      </section>
    </div>

    <div class="grid grid-cols-1 gap-6 xl:grid-cols-12">
      <section class="xl:col-span-5 rounded-2xl border border-outline-variant/15 bg-surface-container-lowest p-6 shadow-sm">
        <div class="mb-5 flex items-center justify-between">
          <h3 class="text-xl font-black text-on-surface">待办任务</h3>
          <span class="rounded-full bg-error-container/30 px-3 py-1 text-xs font-bold text-error">5 项紧急</span>
        </div>

        <div class="space-y-3">
          <article
            v-for="task in tasks"
            :key="task.title"
            class="rounded-xl border border-outline-variant/10 bg-surface p-4 transition-colors hover:bg-surface-container-low"
          >
            <div class="flex items-start justify-between gap-3">
              <div>
                <p class="text-base font-bold text-on-surface">{{ task.title }}</p>
                <p class="mt-1 text-sm text-on-surface-variant">{{ task.desc }}</p>
                <p class="mt-2 text-xs font-bold text-on-surface-variant">{{ task.time }} · {{ task.category }}</p>
              </div>
              <button class="whitespace-nowrap text-xs font-bold text-primary hover:underline">立即处理</button>
            </div>
          </article>
        </div>
      </section>

      <section class="xl:col-span-7 rounded-2xl border border-outline-variant/15 bg-surface-container-lowest p-6 shadow-sm">
        <div class="mb-6 flex items-center justify-between">
          <h3 class="text-xl font-black text-on-surface">AI 智能体动态</h3>
          <div class="flex items-center gap-2">
            <span class="text-[11px] font-bold uppercase tracking-widest text-on-surface-variant">Live</span>
            <span class="h-2.5 w-2.5 animate-pulse rounded-full bg-green-500"></span>
          </div>
        </div>

        <div class="relative space-y-5 before:absolute before:left-[11px] before:top-2 before:bottom-2 before:w-px before:bg-outline-variant/30">
          <article v-for="(feed, idx) in activityFeed" :key="idx" class="relative pl-8">
            <span class="absolute left-0 top-1 flex h-6 w-6 items-center justify-center rounded-full text-[10px] font-black" :class="feed.stepColor">
              {{ feed.step }}
            </span>
            <p class="text-base font-bold text-on-surface">{{ feed.title }}</p>
            <p class="mt-1 text-sm leading-relaxed text-on-surface-variant">{{ feed.desc }}</p>
            <div v-if="feed.tags" class="mt-2 flex flex-wrap gap-2">
              <span
                v-for="tag in feed.tags"
                :key="tag"
                class="rounded-lg border border-outline-variant/10 bg-surface px-2.5 py-1 text-[11px] font-bold text-on-surface-variant"
              >
                {{ tag }}
              </span>
            </div>
            <p v-if="feed.highlight" class="mt-3 rounded-xl border-l-4 border-primary bg-primary/5 px-3 py-2 text-sm text-primary">
              {{ feed.highlight }}
            </p>
          </article>
        </div>

        <button class="mt-8 w-full rounded-xl bg-surface-container-high py-3 text-sm font-bold text-on-surface transition-colors hover:bg-primary hover:text-white">
          进入 Agent 监控室
        </button>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { fetchDashboardAnalytics, type DashboardAnalytics } from '../../api';

const analytics = ref<DashboardAnalytics | null>(null);
const isLoading = ref(true);

onMounted(async () => {
  try {
    analytics.value = await fetchDashboardAnalytics();
  } catch (e) {
    console.error('Failed to fetch analytics', e);
  } finally {
    isLoading.value = false;
  }
});

const totalCandidates = computed(() => {
  if (!analytics.value?.funnel?.length) {
    return 0;
  }
  return analytics.value.funnel[0]?.value ?? 0;
});

const weeklyConversion = computed(() => {
  const funnel = analytics.value?.funnel ?? [];
  if (funnel.length < 2) {
    return '--';
  }
  const first = funnel[0]?.value ?? 0;
  const last = funnel[funnel.length - 1]?.value ?? 0;
  if (!first) {
    return '--';
  }
  return `${Math.round((last / first) * 100)}%`;
});

const tasks = [
  {
    title: '高匹配候选人待评估',
    time: '10 分钟前',
    category: '待处理',
    desc: '职位: 高级产品经理（匹配度 96%）'
  },
  {
    title: '流量预警: 高级前端开发',
    time: '1 小时前',
    category: '系统生成',
    desc: '曝光量低于均值 40%，建议使用 AI 优化职位描述'
  },
  {
    title: '面试反馈待确认（3）',
    time: '2 小时前',
    category: '待决策',
    desc: 'AI 已生成初试报告，等待人工最终确认'
  }
];

const activityFeed = [
  {
    step: '03',
    stepColor: 'bg-primary-fixed text-primary',
    title: 'AI Agent #3 正在面试 张伟',
    desc: '当前阶段: 核心能力评估，实时分析候选人的表达与技术深度。',
    tags: ['实时语音流', '情绪监测: 稳定']
  },
  {
    step: '01',
    stepColor: 'bg-tertiary-fixed text-tertiary',
    title: '已生成 李明 的面试报告',
    desc: '综合匹配度 92%，建议进入终面流程。',
    highlight: '优势: 分布式架构经验扎实，技术决策逻辑清晰。'
  },
  {
    step: '02',
    stepColor: 'bg-primary-fixed text-primary',
    title: 'AI Agent #2 完成 45 份简历初筛',
    desc: '职位: 市场运营总监 | 推荐面试: 4 人'
  },
  {
    step: '04',
    stepColor: 'bg-surface-container-highest text-on-surface-variant',
    title: '正在自动发送面试邀约',
    desc: '目标: 8 位通过初筛的高级架构师候选人'
  }
];
</script>
