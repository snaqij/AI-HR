<template>
  <div class="mx-auto flex w-full max-w-7xl flex-col gap-6 pb-10">
    <header class="sticky top-0 z-10 rounded-2xl border border-outline-variant/15 bg-surface-container-lowest/95 px-6 py-4 backdrop-blur">
      <div class="flex flex-wrap items-start justify-between gap-4">
        <div class="flex items-center gap-3">
          <button
            class="flex h-10 w-10 items-center justify-center rounded-lg border border-outline-variant/30 text-on-surface-variant transition-colors hover:bg-surface-container-low"
            @click="$router.back()"
          >
            <span class="material-symbols-outlined text-lg">arrow_back</span>
          </button>
          <div>
            <h1 class="text-2xl font-bold text-on-surface">候选人详情</h1>
            <p class="mt-1 text-xs text-on-surface-variant">
              {{ candidateItem?.candidate.name || "--" }}
              <span class="mx-1">·</span>
              {{ job?.title || "未关联岗位" }}
              <span v-if="candidateItem?.first_synced_at" class="mx-1">·</span>
              <span v-if="candidateItem?.first_synced_at">首次同步 {{ formatDate(candidateItem?.first_synced_at) }}</span>
            </p>
          </div>
        </div>

        <div class="flex items-center gap-3">
          <button
            class="h-10 rounded-lg border border-outline-variant/30 bg-surface-container-low px-4 text-sm font-semibold text-on-surface-variant transition-colors hover:bg-surface-container"
            :disabled="isLoading"
            @click="loadData"
          >
            刷新
          </button>
          <button
            class="inline-flex h-10 items-center gap-2 rounded-lg bg-primary px-4 text-sm font-semibold text-white transition-opacity disabled:opacity-50"
            :disabled="isAnalyzing || !candidateItem"
            @click="handleAnalyze"
          >
            <span v-if="isAnalyzing" class="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
            {{ isAnalyzing ? "评估中..." : "重新评估" }}
          </button>
        </div>
      </div>
    </header>

    <section v-if="isLoading" class="rounded-2xl border border-outline-variant/15 bg-surface-container-lowest px-6 py-12 text-center">
      <div class="mx-auto mb-3 h-10 w-10 animate-spin rounded-full border-4 border-primary/20 border-t-primary" />
      <p class="text-sm font-medium text-on-surface-variant">正在加载候选人详情...</p>
    </section>

    <section v-else-if="loadError" class="rounded-2xl border border-error/25 bg-error-container/40 px-6 py-8">
      <p class="text-sm font-semibold text-on-error-container">加载失败：{{ loadError }}</p>
      <button
        class="mt-3 h-9 rounded-lg border border-on-error-container/20 bg-white px-4 text-sm font-semibold text-on-error-container"
        @click="loadData"
      >
        重试
      </button>
    </section>

    <template v-else-if="candidateItem">
      <section class="rounded-2xl border border-outline-variant/15 bg-surface-container-lowest px-6 py-5">
        <div class="flex flex-wrap items-center justify-between gap-4">
          <div>
            <p class="text-xs font-semibold uppercase tracking-wide text-on-surface-variant">决策摘要</p>
            <div class="mt-2 flex flex-wrap items-center gap-3">
              <span class="text-4xl font-bold text-on-surface">{{ formatScore(evaluation?.final_score) }}</span>
              <span class="rounded-full px-3 py-1 text-xs font-semibold" :class="getRecommendationBadge(evaluation?.recommendation || 'review')">
                {{ getRecommendationText(evaluation?.recommendation || "review") }}
              </span>
              <span class="rounded-full bg-surface-container-low px-3 py-1 text-xs font-semibold text-on-surface-variant">
                当前阶段：{{ getStageText(candidateItem.stage) }}
              </span>
            </div>
          </div>
          <div class="min-w-[260px] rounded-xl border border-outline-variant/20 bg-surface px-4 py-3">
            <p class="text-xs text-on-surface-variant">建议动作</p>
            <p class="mt-1 text-sm font-semibold text-on-surface">{{ getActionHint(evaluation?.recommendation || "review") }}</p>
          </div>
        </div>
      </section>

      <div class="grid grid-cols-12 gap-6">
        <main class="col-span-12 space-y-6 lg:col-span-8">
          <section class="rounded-2xl border border-outline-variant/15 bg-surface-container-lowest px-6 py-5">
            <div class="mb-4 flex flex-wrap items-center gap-2">
              <button
                v-for="tab in tabs"
                :key="tab.value"
                class="rounded-lg px-3 py-2 text-xs font-semibold transition-colors"
                :class="activeTab === tab.value ? 'bg-primary text-white' : 'bg-surface-container-low text-on-surface-variant hover:bg-surface-container'"
                @click="activeTab = tab.value"
              >
                {{ tab.label }}
              </button>
            </div>

            <div class="space-y-4">
              <div v-if="activeTab === 'summary'" class="space-y-2">
                <label class="text-xs font-semibold text-on-surface-variant">人工决策修正</label>
                <select
                  v-model="editRecommendation"
                  class="h-10 w-full rounded-lg border border-outline-variant/30 bg-white px-3 text-sm text-on-surface focus:border-primary focus:outline-none"
                >
                  <option value="strong_recommend">强烈推荐</option>
                  <option value="recommend">推荐</option>
                  <option value="review">待复核</option>
                  <option value="reject">不推荐</option>
                </select>
              </div>

              <div>
                <label class="mb-2 block text-xs font-semibold text-on-surface-variant">{{ activeTabConfig.label }}</label>
                <textarea
                  v-model="activeTabContent"
                  :rows="activeTabConfig.rows"
                  :placeholder="activeTabConfig.placeholder"
                  class="min-h-[140px] w-full rounded-xl border border-outline-variant/25 bg-white p-4 text-sm leading-6 text-on-surface focus:border-primary focus:outline-none"
                ></textarea>
              </div>

              <div class="flex items-center justify-between border-t border-outline-variant/15 pt-4">
                <p class="text-xs text-on-surface-variant">修改后将实时更新候选人评估记录</p>
                <button
                  class="h-10 rounded-lg bg-primary px-4 text-sm font-semibold text-white transition-opacity disabled:opacity-50"
                  :disabled="isSavingEval || !evaluation"
                  @click="handleSaveEvaluation"
                >
                  {{ isSavingEval ? "保存中..." : "保存评估" }}
                </button>
              </div>
            </div>
          </section>

          <section class="rounded-2xl border border-outline-variant/15 bg-surface-container-lowest px-6 py-5">
            <h2 class="text-base font-semibold text-on-surface">基础信息</h2>
            <div class="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div v-for="info in profileInfo" :key="info.label" class="rounded-lg border border-outline-variant/15 bg-surface px-4 py-3">
                <p class="text-xs text-on-surface-variant">{{ info.label }}</p>
                <p class="mt-1 text-sm font-semibold text-on-surface break-words">{{ info.value || "--" }}</p>
              </div>
            </div>
          </section>
        </main>

        <aside class="col-span-12 space-y-6 lg:col-span-4">
          <section class="rounded-2xl border border-outline-variant/15 bg-surface-container-lowest px-6 py-5">
            <h2 class="text-base font-semibold text-on-surface">流程操作</h2>
            <div class="mt-4 space-y-3">
              <label class="text-xs text-on-surface-variant">当前阶段</label>
              <select
                v-model="editStage"
                class="h-10 w-full rounded-lg border border-outline-variant/30 bg-white px-3 text-sm text-on-surface focus:border-primary focus:outline-none"
              >
                <option v-for="s in stages" :key="s.value" :value="s.value">{{ s.label }}</option>
              </select>
              <button
                class="h-10 w-full rounded-lg border border-outline-variant/30 bg-surface-container-low text-sm font-semibold text-on-surface transition-colors hover:bg-surface-container disabled:opacity-50"
                :disabled="isSavingStage || editStage === candidateItem.stage"
                @click="handleSaveStage"
              >
                {{ isSavingStage ? "保存中..." : "保存阶段" }}
              </button>
            </div>
          </section>

          <section class="rounded-2xl border border-outline-variant/15 bg-surface-container-lowest px-6 py-5">
            <h2 class="text-base font-semibold text-on-surface">沟通记录</h2>
            <div v-if="deliveries.length === 0" class="mt-4 rounded-lg border border-dashed border-outline-variant/35 px-4 py-6 text-center text-xs text-on-surface-variant">
              暂无邮件记录
            </div>
            <div v-else class="mt-4 space-y-3">
              <article
                v-for="item in deliveries"
                :key="item.id"
                class="rounded-lg border border-outline-variant/20 bg-surface px-4 py-3"
              >
                <div class="flex items-center justify-between gap-2">
                  <span class="rounded-full bg-surface-container-low px-2 py-1 text-[11px] font-semibold text-on-surface-variant">{{ item.status }}</span>
                  <span class="text-[11px] text-on-surface-variant">{{ formatDate(item.created_at) }}</span>
                </div>
                <p class="mt-2 line-clamp-2 text-sm font-medium text-on-surface">{{ item.subject || "(无主题)" }}</p>
              </article>
            </div>
          </section>
        </aside>
      </div>
    </template>

    <section v-else class="rounded-2xl border border-outline-variant/15 bg-surface-container-lowest px-6 py-12 text-center">
      <p class="text-sm text-on-surface-variant">未找到候选人信息</p>
      <button class="mt-4 h-10 rounded-lg bg-primary px-4 text-sm font-semibold text-white" @click="$router.back()">返回候选人列表</button>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRoute } from "vue-router";
import {
  evaluateJobCandidate,
  fetchJobEmailDeliveries,
  fetchLatestJobCandidateEvaluation,
  getJobCandidate,
  getJob,
  type CandidateEmailDelivery,
  type CandidateEvaluation,
  type Job,
  type JobCandidate,
  updateCandidateStage,
  updateLatestJobCandidateEvaluation,
} from "../../api";

const route = useRoute();

const jobId = ref((route.query.jobId as string) || "");
const candidateId = ref((route.query.candidateId as string) || "");

const job = ref<Job | null>(null);
const candidateItem = ref<JobCandidate | null>(null);
const evaluation = ref<CandidateEvaluation | null>(null);
const deliveries = ref<CandidateEmailDelivery[]>([]);

const isLoading = ref(false);
const isAnalyzing = ref(false);
const isEvaluationLoading = ref(false);
const isSavingEval = ref(false);
const isSavingStage = ref(false);
const loadError = ref("");

const activeTab = ref("summary");

const editRecommendation = ref("review");
const editSummary = ref("");
const editStrengths = ref("");
const editWeaknesses = ref("");
const editRiskFlags = ref("");
const editStage = ref("new");

const tabs = [
  { label: "评估总结", value: "summary", rows: 8, placeholder: "补充对候选人的整体评价" },
  { label: "核心优势", value: "strengths", rows: 6, placeholder: "列出候选人的关键优势" },
  { label: "改进建议", value: "weaknesses", rows: 6, placeholder: "指出岗位匹配上的主要短板" },
  { label: "风险评估", value: "risks", rows: 4, placeholder: "记录稳定性或背调关注点" },
];

const stages = [
  { label: "新申请", value: "new" },
  { label: "已初筛", value: "parsed" },
  { label: "初筛通过", value: "screen_pass" },
  { label: "面试中", value: "interview" },
  { label: "发放 Offer", value: "offer" },
  { label: "不合适", value: "rejected" },
];

const activeTabConfig = computed(() => tabs.find((tab) => tab.value === activeTab.value) || tabs[0]);

const activeTabContent = computed({
  get() {
    switch (activeTab.value) {
      case "strengths":
        return editStrengths.value;
      case "weaknesses":
        return editWeaknesses.value;
      case "risks":
        return editRiskFlags.value;
      default:
        return editSummary.value;
    }
  },
  set(nextValue: string) {
    switch (activeTab.value) {
      case "strengths":
        editStrengths.value = nextValue;
        break;
      case "weaknesses":
        editWeaknesses.value = nextValue;
        break;
      case "risks":
        editRiskFlags.value = nextValue;
        break;
      default:
        editSummary.value = nextValue;
        break;
    }
  },
});

const profileInfo = computed(() => [
  { label: "姓名", value: candidateItem.value?.candidate.name },
  { label: "邮箱", value: candidateItem.value?.candidate.email },
  { label: "学历", value: candidateItem.value?.candidate.degree },
  { label: "毕业院校", value: candidateItem.value?.candidate.school },
  { label: "最近公司", value: candidateItem.value?.candidate.latest_company },
  { label: "工作经验", value: candidateItem.value?.candidate.work_experience },
  { label: "期望薪资", value: candidateItem.value?.candidate.expected_salary },
  { label: "来源渠道", value: candidateItem.value?.channel },
]);

function toMultiline(values?: string[]) {
  return (values || []).join("\n");
}

function parseLines(raw: string) {
  return raw
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);
}

function formatDate(value?: string | null) {
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

function fillEvaluationForm(item: CandidateEvaluation | null) {
  editRecommendation.value = item?.recommendation || "review";
  editSummary.value = localizeEvaluationText(item?.summary || "");
  editStrengths.value = toMultiline((item?.strengths || []).map(localizeEvaluationText));
  editWeaknesses.value = toMultiline((item?.weaknesses || []).map(localizeEvaluationText));
  editRiskFlags.value = toMultiline((item?.risk_flags || []).map(localizeEvaluationText));
}

async function loadData() {
  if (!jobId.value || !candidateId.value) {
    return;
  }

  isLoading.value = true;
  loadError.value = "";

  try {
    const [jobRes, candidateRes] = await Promise.all([
      getJob(jobId.value),
      getJobCandidate(jobId.value, candidateId.value),
    ]);

    job.value = jobRes;
    candidateItem.value = candidateRes || null;
    editStage.value = candidateItem.value?.stage || "new";

    if (candidateItem.value?.evaluation) {
      evaluation.value = candidateItem.value.evaluation;
      fillEvaluationForm(candidateItem.value.evaluation);
    } else {
      evaluation.value = null;
      fillEvaluationForm(null);
      void loadLatestEvaluation();
    }

    void loadDeliveries();
  } catch (error) {
    const message = error instanceof Error ? error.message : "未知错误";
    loadError.value = message;
  } finally {
    isLoading.value = false;
  }
}

async function loadLatestEvaluation() {
  if (!jobId.value || !candidateId.value || isEvaluationLoading.value) {
    return;
  }

  isEvaluationLoading.value = true;
  try {
    const detail = await fetchLatestJobCandidateEvaluation(jobId.value, candidateId.value);
    evaluation.value = detail.evaluation;
    fillEvaluationForm(detail.evaluation);
  } catch {
    if (!evaluation.value) {
      fillEvaluationForm(null);
    }
  } finally {
    isEvaluationLoading.value = false;
  }
}

async function loadDeliveries() {
  if (!jobId.value || !candidateId.value) {
    deliveries.value = [];
    return;
  }

  try {
    const result = await fetchJobEmailDeliveries(jobId.value, candidateId.value, 30);
    deliveries.value = result.items || [];
  } catch {
    deliveries.value = [];
  }
}

async function handleAnalyze() {
  if (!jobId.value || !candidateId.value || isAnalyzing.value) {
    return;
  }

  isAnalyzing.value = true;
  try {
    const result = await evaluateJobCandidate(jobId.value, candidateId.value, {
      force_refresh: true,
      evaluation_version: "v1",
    });
    evaluation.value = result.evaluation;
    fillEvaluationForm(result.evaluation);
  } finally {
    isAnalyzing.value = false;
  }
}

async function handleSaveEvaluation() {
  if (!jobId.value || !candidateId.value || !evaluation.value || isSavingEval.value) {
    return;
  }

  isSavingEval.value = true;
  try {
    const result = await updateLatestJobCandidateEvaluation(jobId.value, candidateId.value, {
      recommendation: editRecommendation.value,
      summary: editSummary.value,
      strengths: parseLines(editStrengths.value),
      weaknesses: parseLines(editWeaknesses.value),
      risk_flags: parseLines(editRiskFlags.value),
      reviewed_by: "admin-ui",
    });

    evaluation.value = result.evaluation;
    fillEvaluationForm(result.evaluation);
  } finally {
    isSavingEval.value = false;
  }
}

async function handleSaveStage() {
  if (!jobId.value || !candidateId.value || !candidateItem.value || isSavingStage.value) {
    return;
  }
  if (editStage.value === candidateItem.value.stage) {
    return;
  }

  isSavingStage.value = true;
  try {
    const updated = await updateCandidateStage(jobId.value, candidateId.value, editStage.value);
    candidateItem.value = updated;
    editStage.value = updated.stage;
  } finally {
    isSavingStage.value = false;
  }
}

function getStageText(stage: string) {
  return stages.find((item) => item.value === stage)?.label || stage;
}

function formatScore(value?: number | null) {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "--";
  }
  return value.toFixed(1);
}

function getRecommendationText(recommendation: string) {
  switch (recommendation) {
    case "strong_recommend":
      return "强烈推荐";
    case "recommend":
      return "推荐";
    case "review":
      return "待复核";
    case "reject":
      return "不推荐";
    default:
      return recommendation;
  }
}

function getActionHint(recommendation: string) {
  switch (recommendation) {
    case "strong_recommend":
      return "优先推进到面试，尽快锁定沟通时段。";
    case "recommend":
      return "建议安排一轮结构化面试，重点验证项目深度。";
    case "reject":
      return "建议终止推进并记录原因，避免重复沟通。";
    default:
      return "建议由 HR 复核后再决定下一步流程动作。";
  }
}

function getRecommendationBadge(recommendation: string) {
  switch (recommendation) {
    case "strong_recommend":
      return "bg-primary text-white";
    case "recommend":
      return "bg-emerald-50 text-emerald-700";
    case "reject":
      return "bg-red-50 text-red-700";
    default:
      return "bg-amber-50 text-amber-700";
  }
}

function localizeEvaluationText(text: string) {
  const raw = (text || "").trim();
  if (!raw) {
    return "";
  }

  const lower = raw.toLowerCase();
  const exactMap: Record<string, string> = {
    core_stack_aligned: "核心技术栈匹配度高",
    resume_contains_project_context: "简历包含项目上下文信息",
    insufficient_quantified_impact: "量化成果描述不足",
    candidate_shows_direct_stack_overlap: "候选人与岗位技术栈高度重合",
    "mock detailed evaluation output": "模拟评估结果",
  };

  if (exactMap[lower]) {
    return exactMap[lower];
  }
  if (lower.startsWith("core skills aligned:")) {
    return `核心技能匹配：${raw.slice("core skills aligned:".length).trim()}`;
  }
  if (lower.startsWith("matched_skill:")) {
    return `匹配技能：${raw.slice("matched_skill:".length).trim()}`;
  }
  if (lower.startsWith("final_score:")) {
    return `最终得分：${raw.slice("final_score:".length).trim()}`;
  }
  return raw;
}

onMounted(loadData);

watch(
  () => [route.query.jobId, route.query.candidateId],
  ([nextJobId, nextCandidateId]) => {
    jobId.value = (nextJobId as string) || "";
    candidateId.value = (nextCandidateId as string) || "";
    loadData();
  },
);
</script>

<style scoped>
textarea::-webkit-scrollbar {
  width: 6px;
}

textarea::-webkit-scrollbar-thumb {
  border-radius: 8px;
  background: rgba(67, 70, 84, 0.2);
}
</style>
