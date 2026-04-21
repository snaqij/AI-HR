<template>
  <div class="max-w-7xl mx-auto">
    <div class="flex justify-between items-center mb-10">
      <h1 class="text-3xl font-black tracking-tight text-on-surface">录用决策中心</h1>
    </div>

    <div class="grid grid-cols-4 gap-6 mb-12">
      <div v-for="stat in summaryStats" :key="stat.label" class="bg-surface-container-lowest p-6 rounded-2xl shadow-sm border border-outline-variant/10">
        <p class="text-on-surface-variant text-[10px] font-black uppercase tracking-wider mb-2">{{ stat.label }}</p>
        <div class="flex items-baseline gap-2">
          <span class="text-3xl font-black text-on-surface">{{ stat.value }}</span>
          <span v-if="stat.subValue" class="text-[10px] font-bold" :class="stat.subValueColor">{{ stat.subValue }}</span>
        </div>
      </div>
    </div>

    <div v-if="isLoading" class="bg-surface-container-lowest rounded-3xl p-16 text-center border border-outline-variant/10 mb-16">
      <div class="inline-block w-8 h-8 border-4 border-primary/20 border-t-primary rounded-full animate-spin"></div>
      <p class="text-xs font-bold text-on-surface-variant mt-4 uppercase tracking-widest">正在加载录用决策数据...</p>
    </div>

    <div v-else-if="loadError" class="bg-surface-container-lowest rounded-3xl p-16 text-center border border-outline-variant/10 mb-16">
      <p class="text-sm font-black text-rose-600">{{ loadError }}</p>
    </div>

    <div v-else>
      <div class="grid grid-cols-3 gap-8 mb-16">
        <div v-for="card in decisionCards" :key="card.key" class="bg-surface-container-lowest rounded-3xl shadow-sm border border-outline-variant/10 overflow-hidden flex flex-col group hover-lift">
          <div class="p-8 pb-4">
            <div class="flex justify-between items-start mb-6">
              <div class="flex items-center gap-4">
                <div class="w-16 h-16 rounded-2xl bg-surface-container-high border border-outline-variant/10 flex items-center justify-center text-base font-black text-primary">
                  {{ card.initials }}
                </div>
                <div>
                  <h3 class="text-lg font-black text-on-surface group-hover:text-primary transition-colors">{{ card.name }}</h3>
                  <p class="text-xs text-on-surface-variant font-bold mt-0.5">{{ card.title }}</p>
                  <div class="mt-2 flex gap-2">
                    <span v-for="tag in card.tags" :key="tag.label" class="px-2 py-0.5 rounded-md text-[9px] font-black tracking-widest uppercase shadow-sm" :class="tag.bg">
                      {{ tag.label }}
                    </span>
                  </div>
                </div>
              </div>
              <button class="text-on-surface-variant/40 hover:text-on-surface transition-colors" @click="openCandidate(card.jobId, card.candidateId)">
                <span class="material-symbols-outlined">open_in_new</span>
              </button>
            </div>

            <div class="bg-primary/5 rounded-2xl p-5 border border-primary/10 mb-6 relative">
              <div class="flex items-center gap-2 mb-3 text-primary">
                <span class="material-symbols-outlined text-sm material-fill">auto_awesome</span>
                <span class="text-[10px] font-black uppercase tracking-widest">AI 决策洞察</span>
              </div>
              <p class="text-[11px] text-on-surface leading-relaxed font-medium">{{ card.aiInsight }}</p>
            </div>

            <div class="mb-8">
              <p class="text-[10px] font-black text-on-surface-variant uppercase tracking-widest mb-4">录用流程进度</p>
              <div class="flex items-center justify-between relative px-2">
                <div class="absolute top-1/2 left-4 right-4 h-0.5 bg-surface-container-high -translate-y-1/2 -z-0"></div>
                <div class="absolute top-1/2 left-4 h-0.5 bg-green-500 -translate-y-1/2 transition-all duration-1000" :style="{ width: card.progressWidth }"></div>
                <div v-for="(step, idx) in card.steps" :key="idx" class="relative z-10 flex flex-col items-center gap-2">
                  <div class="w-3.5 h-3.5 rounded-full border-2 flex items-center justify-center transition-all duration-500"
                    :class="[
                      step.status === 'completed' ? 'bg-green-500 border-green-500 text-white' :
                      step.status === 'active' ? 'bg-white border-primary shadow-[0_0_8px_rgba(0,58,162,0.3)]' :
                      'bg-white border-outline-variant'
                    ]"
                  >
                    <span v-if="step.status === 'completed'" class="material-symbols-outlined text-[10px] font-black">check</span>
                    <div v-if="step.status === 'active'" class="w-1.5 h-1.5 bg-primary rounded-full animate-pulse"></div>
                  </div>
                  <span class="text-[8px] font-black uppercase tracking-tighter" :class="step.status === 'completed' ? 'text-green-600' : 'text-on-surface-variant opacity-60'">{{ step.label }}</span>
                </div>
              </div>
            </div>

            <div class="grid grid-cols-2 gap-6 mb-8 border-t border-b border-outline-variant/5 py-6">
              <div>
                <p class="text-[9px] font-black text-on-surface-variant uppercase tracking-widest mb-1">期望薪资</p>
                <p class="text-sm font-black text-on-surface">{{ card.salary }}</p>
              </div>
              <div>
                <p class="text-[9px] font-black text-on-surface-variant uppercase tracking-widest mb-1">评估时间</p>
                <p class="text-sm font-black text-on-surface">{{ card.date }}</p>
              </div>
            </div>

            <div class="bg-surface p-4 rounded-xl mb-8 border border-outline-variant/10 italic">
              <p class="text-[10px] text-on-surface-variant leading-relaxed">
                "{{ card.note }}" <span class="not-italic font-bold ml-1 opacity-60">- AI 评估引擎</span>
              </p>
            </div>
          </div>

          <div class="mt-auto p-8 pt-0 space-y-3">
            <button class="w-full py-3.5 rounded-xl bg-primary text-white text-xs font-black shadow-lg shadow-primary/20 hover:brightness-110 active:scale-95 transition-all" @click="openCandidate(card.jobId, card.candidateId)">
              {{ card.primaryAction }}
            </button>
            <div class="grid grid-cols-2 gap-3">
              <button class="py-2.5 rounded-xl bg-surface-container-high text-on-surface-variant text-[10px] font-black hover:bg-outline-variant/30 transition-all uppercase tracking-widest" @click="openCandidate(card.jobId, card.candidateId)">
                {{ card.secondaryAction }}
              </button>
              <button class="py-2.5 rounded-xl bg-surface-container-high text-on-surface-variant text-[10px] font-black hover:bg-outline-variant/30 transition-all uppercase tracking-widest" @click="openCandidate(card.jobId, card.candidateId)">
                查看完整报告
              </button>
            </div>
          </div>
        </div>
      </div>

      <div class="bg-surface-container-lowest rounded-3xl p-8 shadow-sm border border-outline-variant/10">
        <div class="flex justify-between items-center mb-8">
          <div>
            <h3 class="text-xl font-black text-on-surface">待处理决策队列</h3>
            <p class="text-xs text-on-surface-variant font-bold mt-1">系统从数据库中筛选待复核候选人，请尽快处理。</p>
          </div>
          <div class="flex gap-3">
            <button class="px-5 py-2.5 bg-surface-container-high rounded-xl text-[11px] font-black text-on-surface-variant flex items-center gap-2" @click="loadData">
              <span class="material-symbols-outlined text-base">refresh</span> 刷新
            </button>
          </div>
        </div>

        <div class="overflow-x-auto">
          <table class="w-full text-left">
            <thead>
              <tr class="bg-surface-container-low/50 text-on-surface-variant border-b border-outline-variant/10">
                <th class="px-6 py-4 text-[10px] font-black uppercase tracking-widest">候选人</th>
                <th class="px-6 py-4 text-[10px] font-black uppercase tracking-widest">职位</th>
                <th class="px-6 py-4 text-[10px] font-black uppercase tracking-widest">期望薪资</th>
                <th class="px-6 py-4 text-[10px] font-black uppercase tracking-widest">AI 评分</th>
                <th class="px-6 py-4 text-[10px] font-black uppercase tracking-widest text-right">操作</th>
              </tr>
            </thead>
            <tbody class="text-sm divide-y divide-outline-variant/5">
              <tr v-for="item in decisionQueue" :key="item.key" class="group hover:bg-surface transition-colors">
                <td class="px-6 py-5 flex items-center gap-3">
                  <div class="w-10 h-10 rounded-xl bg-surface-container-high flex items-center justify-center font-black text-xs text-on-surface-variant border border-outline-variant/10">
                    {{ item.initials }}
                  </div>
                  <span class="font-black text-on-surface">{{ item.name }}</span>
                </td>
                <td class="px-6 py-5 font-bold text-on-surface-variant">{{ item.job }}</td>
                <td class="px-6 py-5 font-black text-on-surface">{{ item.salary }}</td>
                <td class="px-6 py-5">
                  <div class="flex items-center gap-4">
                    <div class="flex items-center gap-1 text-primary">
                      <span v-for="i in 5" :key="i" class="material-symbols-outlined text-base" :class="{ 'material-fill': i <= item.rating }">star</span>
                    </div>
                    <span class="px-2 py-0.5 bg-primary/5 text-primary text-[10px] font-black rounded border border-primary/10 tracking-widest uppercase">{{ item.analysis }}</span>
                  </div>
                </td>
                <td class="px-6 py-5 text-right">
                  <button class="text-xs font-black text-primary hover:underline tracking-widest uppercase" @click="openCandidate(item.jobId, item.candidateId)">立即处理</button>
                </td>
              </tr>
              <tr v-if="!decisionQueue.length">
                <td colspan="5" class="px-6 py-10 text-center text-sm font-bold text-on-surface-variant">当前没有待处理决策。</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
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

type DecisionStep = {
  label: string;
  status: "completed" | "active" | "pending";
};

type DecisionCard = {
  key: string;
  candidateId: string;
  jobId: string;
  initials: string;
  name: string;
  title: string;
  tags: Array<{ label: string; bg: string }>;
  aiInsight: string;
  progressWidth: string;
  steps: DecisionStep[];
  salary: string;
  date: string;
  note: string;
  primaryAction: string;
  secondaryAction: string;
};

type QueueItem = {
  key: string;
  candidateId: string;
  jobId: string;
  initials: string;
  name: string;
  job: string;
  salary: string;
  rating: number;
  analysis: string;
};

const router = useRouter();
const isLoading = ref(false);
const loadError = ref("");
const overview = ref<HiringCenterOverviewResult | null>(null);
const decisionCards = ref<DecisionCard[]>([]);
const decisionQueue = ref<QueueItem[]>([]);

const summaryStats = computed(() => {
  const snapshot = overview.value;
  const total = snapshot?.total || 0;
  const reviewCount = snapshot?.review_count || 0;
  const invitedCount = snapshot?.invited_count || 0;
  const recommendedCount = snapshot?.recommended_count || 0;
  const conversion = String(snapshot?.conversion_rate ?? 0);
  return [
    { label: "待处理决策", value: String(reviewCount).padStart(2, "0"), subValue: `总计 ${total}`, subValueColor: "text-primary" },
    { label: "已发面试邀约", value: String(invitedCount).padStart(2, "0"), subValue: `${recommendedCount} 人推荐`, subValueColor: "text-green-600" },
    { label: "高优先级候选人", value: String(recommendedCount).padStart(2, "0"), subValue: "来自评估结果", subValueColor: "text-on-surface-variant/50" },
    { label: "邀约转化率", value: `${conversion}%`, subValue: "基于数据库数据", subValueColor: "text-green-600" },
  ];
});

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
  if (!text) {
    return "待沟通";
  }
  return text;
}

function recommendationTag(recommendation: string): { label: string; bg: string } {
  if (recommendation === "strong_recommend") {
    return { label: "强烈推荐", bg: "bg-green-100 text-green-700" };
  }
  if (recommendation === "recommend") {
    return { label: "推荐", bg: "bg-primary/10 text-primary" };
  }
  if (recommendation === "reject") {
    return { label: "不推荐", bg: "bg-rose-100 text-rose-700" };
  }
  return { label: "待复核", bg: "bg-amber-100 text-amber-700" };
}

function buildSteps(item: HiringCenterEvaluationItem): DecisionStep[] {
  const stage = String(item.candidate_stage || "").toLowerCase();
  const flags = [
    item.evaluation_status === "completed" || item.evaluation_status === "reviewed",
    ["recommend", "strong_recommend"].includes(item.recommendation),
    Boolean(item.invited_flag),
    ["offer", "hired"].includes(stage),
  ];
  const labels = ["评估完成", "进入推荐", "已发邀约", "最终决策"];
  const firstPendingIndex = flags.findIndex((done) => !done);
  return labels.map((label, idx) => {
    if (flags[idx]) {
      return { label, status: "completed" };
    }
    if (firstPendingIndex === idx) {
      return { label, status: "active" };
    }
    return { label, status: "pending" };
  });
}

function buildProgressWidth(steps: DecisionStep[]): string {
  const completedCount = steps.filter((step) => step.status === "completed").length;
  const width = Math.max(0, Math.min(100, (completedCount / Math.max(1, steps.length - 1)) * 100));
  return `${width}%`;
}

function toCard(item: HiringCenterEvaluationItem): DecisionCard {
  const steps = buildSteps(item);
  const tag = recommendationTag(item.recommendation);
  return {
    key: `${item.job_id}-${item.candidate_id}`,
    candidateId: item.candidate_id,
    jobId: item.job_id,
    initials: toInitials(item.candidate_name),
    name: item.candidate_name,
    title: item.job_title,
    tags: [tag],
    aiInsight: item.summary || item.candidate_score_explanation || "暂无评估总结，建议人工复核候选人核心能力。",
    progressWidth: buildProgressWidth(steps),
    steps,
    salary: formatSalary(item.candidate_expected_salary || item.job_salary_range),
    date: new Date(item.updated_at || item.created_at).toLocaleDateString("zh-CN"),
    note: item.highlights?.length ? item.highlights.join("；") : "暂无补充备注。",
    primaryAction: ["recommend", "strong_recommend"].includes(item.recommendation) ? "进入候选人详情" : "发起人工复核",
    secondaryAction: "查看候选人",
  };
}

function scoreToRating(score: number): number {
  if (score >= 90) {
    return 5;
  }
  if (score >= 80) {
    return 4;
  }
  if (score >= 70) {
    return 3;
  }
  if (score >= 60) {
    return 2;
  }
  return 1;
}

function toQueueItem(item: HiringCenterEvaluationItem): QueueItem {
  return {
    key: `${item.job_id}-${item.candidate_id}`,
    candidateId: item.candidate_id,
    jobId: item.job_id,
    initials: toInitials(item.candidate_name),
    name: item.candidate_name,
    job: item.job_title,
    salary: formatSalary(item.candidate_expected_salary || item.job_salary_range),
    rating: scoreToRating(Number(item.final_score || 0)),
    analysis: recommendationTag(item.recommendation).label,
  };
}

function openCandidate(jobId: string, candidateId: string) {
  router.push(`/admin/candidate-detail?jobId=${jobId}&candidateId=${candidateId}`);
}

async function loadData() {
  isLoading.value = true;
  loadError.value = "";
  try {
    const result = await fetchHiringCenterOverview({ top_n: 3, queue_limit: 20, max_scan: 3000 });
    overview.value = result;
    decisionCards.value = result.top_items.map(toCard);
    decisionQueue.value = result.queue_items.map(toQueueItem);
  } catch (error) {
    console.error("Failed to load hiring center data", error);
    loadError.value = "加载录用决策数据失败，请稍后重试。";
    overview.value = null;
    decisionCards.value = [];
    decisionQueue.value = [];
  } finally {
    isLoading.value = false;
  }
}

onMounted(() => {
  loadData();
});
</script>
