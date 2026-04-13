<template>
  <div class="max-w-7xl mx-auto">
    <div class="flex justify-between items-end mb-10">
      <div>
        <span class="text-xs font-bold tracking-[0.2em] text-primary uppercase">Console Overview</span>
        <h1 class="text-4xl font-black tracking-tighter mt-1 text-on-surface">控制台 <span class="text-primary-container">/</span> 实时概览</h1>
      </div>
      <div class="flex gap-3">
        <button class="px-6 py-2.5 rounded-xl bg-surface-container-highest text-on-surface text-sm font-bold hover:bg-outline-variant transition-colors shadow-sm">
          下载报表
        </button>
        <button class="px-6 py-2.5 rounded-xl ai-gradient text-white text-sm font-bold shadow-lg hover-lift">
          发布新职位
        </button>
      </div>
    </div>

    <div class="grid grid-cols-12 gap-8" v-if="analytics">
      <!-- Recruitment Funnel Widget (8 cols) -->
      <section class="col-span-12 lg:col-span-8 bg-surface-container-lowest rounded-xl p-8 flex flex-col gap-8 shadow-sm border border-outline-variant/5">
        <div class="flex justify-between items-start">
          <h3 class="text-xl font-bold">招聘漏斗分析</h3>
          <div class="flex gap-2">
            <span class="px-3 py-1 bg-surface-container-low rounded-full text-xs font-bold text-on-surface-variant">最近 30 天</span>
          </div>
        </div>

        <!-- Funnel Visualization -->
        <div class="flex items-end justify-around h-64 gap-4 px-4">
          <div v-for="step in analytics.funnel" :key="step.label" class="flex flex-col items-center flex-1">
            <div 
              class="w-full ai-gradient rounded-t-xl transition-all duration-1000 hover:brightness-110 cursor-pointer relative group"
              :style="{ height: step.height, opacity: step.opacity }"
            ></div>
            <div class="text-center">
              <p class="text-3xl font-black">{{ step.value }}</p>
              <p class="text-xs font-bold text-on-surface-variant uppercase tracking-widest mt-1.5">{{ step.label }}</p>
              <span v-if="step.conversion" class="text-xs text-primary font-bold">{{ step.conversion }} 转化</span>
            </div>
          </div>
        </div>

        <!-- Weekly Comparison Row -->
        <div class="grid grid-cols-4 gap-4 mt-1">
          <div v-for="step in analytics.funnel" :key="step.label + 'wow'" class="flex flex-col items-center bg-surface-container-low/30 py-3 rounded-lg">
            <p class="text-xs text-on-surface-variant mb-1">周同比</p>
            <div class="flex items-center font-bold text-sm" :class="step.growth >= 0 ? 'text-green-600' : 'text-red-500'">
              <span class="material-symbols-outlined text-xs">{{ step.growth >= 0 ? 'trending_up' : 'trending_down' }}</span>
              <span>{{ step.growth >= 0 ? '+' : '' }}{{ step.growth }}%</span>
            </div>
          </div>
        </div>
      </section>

      <!-- AI Efficiency Card (4 cols) -->
      <section class="col-span-12 lg:col-span-4 bg-surface-container-lowest rounded-xl p-8 border-l-[3px] border-tertiary shadow-sm border border-outline-variant/30">
        <h3 class="text-xl font-bold mb-6">AI 效能看板</h3>
        <div class="space-y-8">
          <div v-for="metric in analytics.efficiency" :key="metric.label">
            <p class="text-xs font-bold text-on-surface-variant uppercase tracking-widest mb-2.5">{{ metric.label }}</p>
            <div class="flex items-baseline gap-2">
              <span class="text-5xl font-black text-tertiary">{{ metric.value }}</span>
              <span class="text-base font-bold text-on-surface-variant">{{ metric.unit }}</span>
            </div>
            <div class="w-full h-1.5 bg-surface-container-low rounded-full mt-4 overflow-hidden">
              <div class="h-full bg-tertiary rounded-full shadow-[0_0_8px_rgba(0,74,85,0.4)]" :style="{ width: metric.progress + '%' }"></div>
            </div>
          </div>
        </div>
      </section>
    </div>

    <!-- Task Queue (7 cols) -->
    <section class="col-span-12 lg:col-span-7 space-y-6 mt-8">
      <div class="bg-surface-container-lowest rounded-xl p-8 shadow-sm border border-outline-variant/5">
        <div class="flex justify-between items-center mb-6">
          <h3 class="text-xl font-bold">待办任务队列</h3>
          <span class="text-xs font-black text-error bg-error-container/20 px-4 py-1.5 rounded-full border border-error/10 uppercase tracking-widest">5 项紧急</span>
        </div>
        <div class="space-y-4">
          <div v-for="task in tasks" :key="task.title" class="flex items-center justify-between p-4 bg-surface rounded-xl hover:bg-surface-container-low transition-colors group cursor-pointer border border-transparent hover:border-outline-variant/10">
            <div class="flex items-center gap-4">
              <div class="w-10 h-10 rounded-full flex items-center justify-center bg-surface-container-high">
                <span class="material-symbols-outlined text-xl" :class="task.color">task</span>
              </div>
              <div>
                <p class="text-sm font-bold text-on-surface">{{ task.title }}</p>
                <p class="text-[11px] text-on-surface-variant font-medium mt-0.5">{{ task.time }} · {{ task.category }}</p>
              </div>
            </div>
            <button class="text-xs font-bold text-primary group-hover:underline">立即处理</button>
          </div>
        </div>
      </div>
    </section>

    <!-- Real-time Feed -->
    <section class="mt-8 bg-surface-container-lowest rounded-xl p-8 shadow-sm border border-outline-variant/5">
      <div class="flex justify-between items-center mb-8">
        <h3 class="text-lg font-bold">AI 智能体动态</h3>
        <div class="flex items-center gap-2">
          <span class="text-[10px] font-bold text-on-surface-variant tracking-widest uppercase">Live Monitoring</span>
          <span class="w-2.5 h-2.5 bg-green-500 rounded-full animate-pulse shadow-[0_0_12px_rgba(34,197,94,0.6)]"></span>
        </div>
      </div>
      <div class="space-y-6 relative before:absolute before:left-[11px] before:top-2 before:bottom-2 before:w-[1px] before:bg-outline-variant/20">
        <div v-for="(feed, idx) in activityFeed" :key="idx" class="relative pl-9 overflow-hidden group">
          <div 
              class="absolute left-0 top-1 w-7 h-7 rounded-full flex items-center justify-center text-xs font-black shadow-sm"
              :class="feed.stepColor"
          >
              {{ feed.step }}
          </div>
          <p class="text-base font-bold text-on-surface">{{ feed.title }}</p>
          <p class="text-sm text-on-surface-variant mt-2 leading-relaxed font-medium">{{ feed.desc }}</p>
          <div v-if="feed.tags" class="flex gap-2 mt-3.5">
            <span v-for="tag in feed.tags" :key="tag" class="px-3 py-1.5 bg-surface-container-low text-xs rounded-xl font-bold text-on-surface-variant/70 border border-outline-variant/10 uppercase tracking-wider">
              {{ tag }}
            </span>
          </div>
          <div v-if="feed.highlight" class="mt-4 p-4 bg-primary/5 rounded-2xl border-l-[4px] border-primary text-sm font-medium text-primary">
             {{ feed.highlight }}
          </div>
        </div>
      </div>
      <button class="w-full mt-10 py-4 rounded-xl bg-surface-container-low text-on-surface text-sm font-black hover:bg-primary hover:text-white transition-all duration-300 shadow-sm">
        进入 Agent 监控室
      </button>
    </section>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { fetchDashboardAnalytics, type DashboardAnalytics } from '../../api';

const analytics = ref<DashboardAnalytics | null>(null);
const isLoading = ref(true);

onMounted(async () => {
    try {
        analytics.value = await fetchDashboardAnalytics();
    } catch (e) {
        console.error("Failed to fetch analytics", e);
    } finally {
        isLoading.value = false;
    }
});

const tasks = [
  { 
    title: '高匹配候选人待评审', 
    time: '10分钟前',
    category: '待处理',
    color: 'text-primary',
    desc: '职位：高级产品经理 (匹配度: 96%)',
    icon: 'person_search'
  },
  { 
    title: '流量预警：高级前端开发', 
    time: '1小时前',
    category: '系统生成',
    color: 'text-error',
    desc: '曝光量低于均值 40%，建议 AI 优化描述',
    icon: 'trending_down'
  },
  { 
    title: '面试反馈待确认 (3)', 
    time: '2小时前',
    category: '待决策',
    color: 'text-primary',
    desc: 'AI 已生成初试报告，等待人工最终决策',
    icon: 'rate_review'
  }
];

const channels = [
  { name: 'LinkedIn', rating: 4, conversion: 12.4, cost: 2400 },
  { name: 'Boss 直聘', rating: 3, conversion: 8.1, cost: 850 },
  { name: '内部推荐', rating: 5, conversion: 24.5, cost: 4500 }
];

const activityFeed = [
  { 
    step: '03', 
    stepColor: 'bg-primary-fixed text-primary',
    title: 'AI Agent #3 正在面试 张伟', 
    desc: '当前阶段: 核心能力评估 - 进行中...', 
    tags: ['实时音频流', '情绪监控: 稳定'] 
  },
  { 
    step: '01', 
    stepColor: 'bg-tertiary-fixed text-tertiary',
    title: '已生成 李明 的面试报告', 
    desc: '深度匹配度: 92% (极高匹配)', 
    highlight: '优势：极强的分布式架构经验，技术视野开阔。' 
  },
  { 
    step: '02', 
    stepColor: 'bg-primary-fixed text-primary',
    title: 'AI Agent #2 完成了 45 份简历初筛', 
    desc: '职位: 市场运营总监 | 推荐面试: 4人' 
  },
  { 
    step: '04', 
    stepColor: 'bg-surface-container-highest text-on-surface-variant',
    title: '正在自动外呼邀请面试...', 
    desc: '目标: 8位通过初筛的高级架构师' 
  }
];
</script>
