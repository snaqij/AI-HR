<template>
  <div class="max-w-7xl mx-auto flex flex-col gap-8 pb-12">
    <!-- 顶部导航与操作栏 -->
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-4">
        <button
          class="w-12 h-12 rounded-2xl hover:bg-surface-container-high transition-all flex items-center justify-center border border-outline-variant/10 shadow-sm grow-0 shrink-0"
          @click="$router.back()"
        >
          <span class="material-symbols-outlined text-on-surface-variant">arrow_back</span>
        </button>
        <div class="flex flex-col">
          <h1 class="text-2xl font-black text-on-surface leading-tight">候选人详情</h1>
          <div class="flex items-center gap-2 mt-0.5">
            <span class="text-[10px] font-black text-primary uppercase tracking-[0.2em]">Candidate Analysis</span>
            <div class="w-1 h-1 bg-outline-variant/30 rounded-full"></div>
            <p class="text-xs font-bold text-on-surface-variant/60">
              数据采集于 {{ candidateItem?.first_synced_at || '最近' }}
            </p>
          </div>
        </div>
      </div>
      <div class="flex items-center gap-3">
        <button
          class="h-11 px-6 rounded-2xl bg-surface-container-low text-on-surface-variant text-sm font-black hover:bg-surface-container-high transition-all border border-outline-variant/5"
          :disabled="isLoading"
          @click="loadData"
        >
          刷新数据
        </button>
        <button
          class="h-11 px-6 rounded-2xl bg-primary text-white text-sm font-black disabled:opacity-50 hover-lift shadow-lg shadow-primary/20 transition-all flex items-center gap-2"
          :disabled="isAnalyzing || !candidateItem"
          @click="handleAnalyze"
        >
          <span v-if="isAnalyzing" class="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"></span>
          {{ isAnalyzing ? "分析中..." : "重新深度分析" }}
        </button>
      </div>
    </div>

    <!-- 加载状态 -->
    <div v-if="isLoading" class="bg-surface-container-lowest rounded-[32px] p-20 text-center border border-outline-variant/10">
      <div class="w-12 h-12 border-4 border-primary/20 border-t-primary rounded-full animate-spin mx-auto mb-4"></div>
      <p class="text-on-surface-variant font-bold">正在提取深度人才画像...</p>
    </div>

    <template v-else-if="candidateItem">
      <div class="grid grid-cols-12 gap-8 items-start">
        <!-- 左侧：基础档案 (Sidebar) -->
        <aside class="col-span-12 lg:col-span-4 space-y-6 lg:sticky lg:top-8">
          <section class="bg-surface-container-lowest rounded-[32px] p-8 border border-outline-variant/10 shadow-sm overflow-hidden relative">
            <div class="absolute top-0 right-0 w-32 h-32 bg-primary/5 rounded-full -mr-16 -mt-16 blur-3xl"></div>
            
            <h2 class="text-sm font-black uppercase tracking-[0.2em] text-primary mb-8 ml-1">档案概览</h2>
            
            <div class="space-y-6">
              <!-- 各类信息条目 -->
              <div v-for="info in sidebarInfo" :key="info.label" class="flex items-start gap-4 p-4 rounded-2xl hover:bg-surface-container-low transition-colors group">
                <div class="w-10 h-10 rounded-xl bg-surface-container-high flex items-center justify-center grow-0 shrink-0 group-hover:bg-primary/10 transition-colors">
                  <span class="material-symbols-outlined text-on-surface-variant group-hover:text-primary transition-colors text-xl">{{ info.icon }}</span>
                </div>
                <div class="flex flex-col min-w-0">
                  <span class="text-[10px] font-black text-on-surface-variant/50 uppercase tracking-widest leading-none mb-1.5">{{ info.label }}</span>
                  <span class="text-sm font-bold text-on-surface truncate break-all leading-tight">{{ info.value || '-' }}</span>
                </div>
              </div>

              <!-- 流程阶段 -->
              <div class="pt-4 border-t border-outline-variant/10">
                <label class="text-[10px] font-black text-on-surface-variant/50 uppercase tracking-widest block mb-4 ml-1">当前流程阶段</label>
                <div class="flex items-center gap-2 p-2 bg-surface-container-low rounded-2xl border border-outline-variant/5">
                  <select
                    v-model="editStage"
                    class="flex-1 bg-transparent border-none text-sm font-black focus:ring-0 cursor-pointer pl-3 py-2"
                  >
                    <option v-for="s in stages" :key="s.value" :value="s.value">{{ s.label }}</option>
                  </select>
                  <button
                    class="h-9 px-4 rounded-xl bg-on-surface text-white text-[10px] font-black uppercase tracking-wider hover-lift disabled:opacity-50"
                    :disabled="isSavingStage || editStage === candidateItem.stage"
                    @click="handleSaveStage"
                  >
                    {{ isSavingStage ? "SAVE" : "保存" }}
                  </button>
                </div>
              </div>
            </div>
          </section>

          <!-- 邮件记录 -->
          <section class="bg-surface-container-lowest rounded-[32px] p-8 border border-outline-variant/10 shadow-sm">
            <h2 class="text-sm font-black uppercase tracking-[0.2em] text-on-surface-variant mb-6 ml-1">沟通历史</h2>
            <div v-if="deliveries.length === 0" class="flex flex-col items-center py-6">
               <span class="material-symbols-outlined text-outline-variant text-3xl mb-2">history</span>
               <p class="text-[10px] font-bold text-on-surface-variant/40">暂无往来邮件记录</p>
            </div>
            <div v-else class="space-y-3">
              <div
                v-for="item in deliveries"
                :key="item.id"
                class="flex flex-col gap-1 p-4 bg-surface-container-low rounded-2xl border border-outline-variant/5 hover:bg-surface-container-high transition-colors"
              >
                <div class="flex items-center justify-between">
                  <span class="text-[10px] font-black text-primary uppercase tracking-widest">{{ item.status }}</span>
                  <span class="text-[10px] text-on-surface-variant/50 font-bold">{{ formatDate(item.created_at) }}</span>
                </div>
                <span class="text-xs font-bold text-on-surface line-clamp-1 leading-normal">{{ item.subject }}</span>
              </div>
            </div>
          </section>
        </aside>

        <!-- 右侧：评估报告 (Main Content) -->
        <main class="col-span-12 lg:col-span-8 space-y-8">
          <!-- 核心评估指标 -->
          <section class="bg-surface-container-lowest rounded-[40px] p-10 border border-outline-variant/10 shadow-sm relative overflow-hidden">
            <div class="absolute bottom-0 right-0 w-64 h-64 bg-primary/5 rounded-full -mr-32 -mb-32 blur-3xl"></div>
            
            <div class="flex flex-col lg:flex-row lg:items-center justify-between gap-8 mb-10">
              <div>
                <h2 class="text-2xl font-black text-on-surface mb-2">人才价值评估</h2>
                <p class="text-sm text-on-surface-variant leading-relaxed max-w-lg">基于 AI 对应聘岗位需求的精准匹配分析。以下评估结果涵盖了技术契合度、项目背景及潜在职业风险。</p>
              </div>
              <div v-if="evaluation" class="flex items-center gap-6">
                <!-- 指标 1 -->
                <div class="flex flex-col items-end">
                  <span class="text-[10px] font-black text-on-surface-variant/50 uppercase tracking-widest mb-1.5">人才匹配得分</span>
                  <div class="text-5xl font-black text-primary tracking-tighter">{{ formatScore(evaluation.final_score) }}</div>
                </div>
                <!-- 分隔线 -->
                <div class="w-px h-12 bg-outline-variant/20 hidden lg:block"></div>
                <!-- 指标 2 -->
                <div class="flex flex-col items-end">
                  <span class="text-[10px] font-black text-on-surface-variant/50 uppercase tracking-widest mb-1.5">官方专家建议</span>
                  <div 
                    :class="[
                      'text-lg h-9 px-4 rounded-xl font-black flex items-center',
                      evaluation.recommendation.includes('strong') ? 'bg-primary text-white' : 'bg-surface-container-high text-on-surface'
                    ]"
                  >
                    {{ getRecommendationText(evaluation.recommendation) }}
                  </div>
                </div>
              </div>
              <div v-else class="text-center py-4 px-8 border-2 border-dashed border-outline-variant/20 rounded-3xl">
                <p class="text-sm font-bold text-on-surface-variant">评估报告待生成</p>
              </div>
            </div>

            <!-- 深度解析区域 (Tabs) -->
            <div class="bg-surface rounded-[24px] p-6 border border-outline-variant/5 shadow-inner">
              <!-- 标签切换 -->
              <div class="flex flex-wrap gap-2 mb-8 bg-surface-container-low p-1.5 rounded-2xl w-fit">
                <button
                  v-for="tab in tabs"
                  :key="tab.value"
                  @click="activeTab = tab.value"
                  :class="[
                    'h-10 px-6 rounded-xl text-xs font-black transition-all flex items-center gap-2',
                    activeTab === tab.value ? 'bg-white text-primary shadow-sm' : 'text-on-surface-variant/60 hover:text-on-surface'
                  ]"
                >
                  <span class="material-symbols-outlined text-[18px]">{{ tab.icon }}</span>
                  {{ tab.label }}
                </button>
              </div>

              <!-- 标签内容 -->
              <div class="space-y-6">
                <!-- 结论选择 -->
                <div v-if="activeTab === 'summary'" class="flex flex-col gap-2 mb-4">
                  <label class="text-[10px] font-black text-on-surface-variant uppercase tracking-widest ml-1">人工决策修正</label>
                  <select
                    v-model="editRecommendation"
                    class="w-full lg:w-48 h-10 px-4 rounded-xl bg-white border border-outline-variant/10 text-xs font-bold shadow-sm focus:ring-0"
                  >
                    <option value="strong_recommend">强力推荐 (Strong)</option>
                    <option value="recommend">推荐 (Recommend)</option>
                    <option value="review">待复核 (Review)</option>
                    <option value="reject">不推荐 (Reject)</option>
                  </select>
                </div>

                <!-- 文本编辑区 -->
                <div v-for="tab in tabs" :key="tab.value" v-show="activeTab === tab.value">
                   <div class="flex items-center justify-between mb-4 px-1">
                      <div class="flex items-center gap-2">
                        <span class="text-sm font-black text-on-surface">{{ tab.label }}分析</span>
                        <div class="px-2 py-0.5 rounded-md bg-primary/5 text-[8px] font-black text-primary uppercase tracking-tighter">AI Insight</div>
                      </div>
                      <span class="text-[10px] text-on-surface-variant/40 font-bold italic">{{ tab.placeholder }}</span>
                   </div>
                   <textarea
                    v-model="fieldMap[tab.modelKey as keyof typeof fieldMap].value"
                    :rows="tab.rows"
                    class="w-full bg-white rounded-3xl p-6 text-sm text-on-surface border border-outline-variant/10 focus:outline-none focus:border-primary/30 transition-all font-medium leading-relaxed shadow-sm min-h-[160px]"
                    :placeholder="tab.placeholder"
                  ></textarea>
                </div>

                <!-- 动作条 -->
                <div class="flex items-center justify-between pt-4 mt-4 border-t border-outline-variant/5">
                   <div class="flex items-center gap-2 text-on-surface-variant/40">
                      <span class="material-symbols-outlined text-sm">info</span>
                      <p class="text-[10px] font-bold">所有修改将在确认保存后实时更新到人才库</p>
                   </div>
                   <button
                    class="h-12 px-10 rounded-2xl bg-primary text-white text-sm font-black disabled:opacity-50 hover-lift shadow-xl shadow-primary/20 transition-all"
                    :disabled="isSavingEval || !evaluation"
                    @click="handleSaveEvaluation"
                  >
                    {{ isSavingEval ? "处理中..." : "保存核心评估修改" }}
                  </button>
                </div>
              </div>
            </div>
          </section>
        </main>
      </div>
    </template>

    <div v-else class="bg-surface-container-lowest rounded-[32px] p-20 text-center border border-outline-variant/10">
      <div class="w-16 h-16 bg-surface-container-high rounded-full flex items-center justify-center mx-auto mb-6">
        <span class="material-symbols-outlined text-on-surface-variant/20 text-4xl font-black">person_off</span>
      </div>
      <p class="text-on-surface-variant font-black text-lg">无法连接该候选人档案</p>
      <p class="text-sm text-on-surface-variant/60 mt-2">请确认 ID 是否正确或联系管理员。</p>
      <button @click="$router.back()" class="mt-8 px-6 py-3 rounded-2xl bg-on-surface text-white font-black text-sm">返回人才库</button>
    </div>
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
const isSavingEval = ref(false);
const isSavingStage = ref(false);

const activeTab = ref("summary");

const editRecommendation = ref("review");
const editSummary = ref("");
const editStrengths = ref("");
const editWeaknesses = ref("");
const editRiskFlags = ref("");
const editStage = ref("new");

// --- UI Constants & Mappings ---
const tabs = [
  { label: '评估总结', value: 'summary', icon: 'auto_awesome', modelKey: 'summary', rows: 8, placeholder: '在此补充对候选人的整体评价...' },
  { label: '核心优势', value: 'strengths', icon: 'verified', modelKey: 'strengths', rows: 6, placeholder: '罗列候选人最突出的技术能力或项目经验...' },
  { label: '改进建议', value: 'weaknesses', icon: 'error_outline', modelKey: 'weaknesses', rows: 6, placeholder: '指出与岗位的不匹配处或面试考察重点...' },
  { label: '风险评估', value: 'risks', icon: 'warning', modelKey: 'risks', rows: 4, placeholder: '记录离职动机、稳定性或其他背调疑点...' },
];

const fieldMap = {
  summary: editSummary,
  strengths: editStrengths,
  weaknesses: editWeaknesses,
  risks: editRiskFlags
};

const stages = [
  { label: '新申请 (New)', value: 'new' },
  { label: '已初筛 (Parsed)', value: 'parsed' },
  { label: '初筛通过 (Pass)', value: 'screen_pass' },
  { label: '面试中 (Interview)', value: 'interview' },
  { label: '录取 (Offer)', value: 'offer' },
  { label: '不合适 (Rejected)', value: 'rejected' },
];

const sidebarInfo = computed(() => [
  { label: '姓名', value: candidateItem.value?.candidate.name, icon: 'person' },
  { label: '联系邮箱', value: candidateItem.value?.candidate.email, icon: 'mail' },
  { label: '最高学历', value: candidateItem.value?.candidate.degree, icon: 'school' },
  { label: '毕业院校', value: candidateItem.value?.candidate.school, icon: 'account_balance' },
  { label: '最近公司', value: candidateItem.value?.candidate.latest_company, icon: 'apartment' },
  { label: '职业年限', value: candidateItem.value?.candidate.work_experience, icon: 'work_history' },
  { label: '期望薪酬', value: candidateItem.value?.candidate.expected_salary, icon: 'payments' },
]);

// --- Business Logic ---
function toMultiline(values?: string[]) {
  return (values || []).join("\n");
}

function parseLines(raw: string) {
  return raw
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);
}

function formatDate(val: string) {
  if (!val) return '';
  const d = new Date(val);
  return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours()}:${d.getMinutes().toString().padStart(2, '0')}`;
}

function fillEvaluationForm(item: CandidateEvaluation | null) {
  editRecommendation.value = item?.recommendation || "review";
  editSummary.value = localizeEvaluationText(item?.summary || "");
  editStrengths.value = toMultiline((item?.strengths || []).map(localizeEvaluationText));
  editWeaknesses.value = toMultiline((item?.weaknesses || []).map(localizeEvaluationText));
  editRiskFlags.value = toMultiline(item?.risk_flags);
}

async function loadData() {
  if (!jobId.value || !candidateId.value) {
    return;
  }
  isLoading.value = true;
  try {
    const [jobRes, candidatesRes, deliveriesRes] = await Promise.all([
      getJob(jobId.value),
      getJobCandidate(jobId.value, candidateId.value),
      fetchJobEmailDeliveries(jobId.value, candidateId.value),
    ]);
    job.value = jobRes;
    candidateItem.value = candidatesRes || null;
    editStage.value = candidateItem.value?.stage || "new";
    deliveries.value = deliveriesRes.items;

    try {
      const detail = await fetchLatestJobCandidateEvaluation(jobId.value, candidateId.value);
      evaluation.value = detail.evaluation;
      fillEvaluationForm(detail.evaluation);
    } catch (_error) {
      evaluation.value = null;
      fillEvaluationForm(null);
    }
  } finally {
    isLoading.value = false;
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

function formatScore(value?: number | null) {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "-";
  }
  return value.toFixed(1);
}

function getRecommendationText(recommendation: string) {
  switch (recommendation) {
    case "strong_recommend":
      return "强力推荐";
    case "recommend":
      return "推荐面试";
    case "review":
      return "待人工复核";
    case "reject":
      return "不推荐";
    default:
      return recommendation;
  }
}

function localizeEvaluationText(text: string) {
  const raw = (text || "").trim();
  if (!raw) {
    return "";
  }
  const lower = raw.toLowerCase();
  const exactMap: Record<string, string> = {
    "core_stack_aligned": "核心技术栈匹配度高",
    "resume_contains_project_context": "简历包含项目上下文信息",
    "insufficient_quantified_impact": "量化成果描述不足",
    "candidate_shows_direct_stack_overlap": "候选人与岗位技术栈直接重合",
    "mock detailed evaluation output": "模拟评估结果",
  };
  if (exactMap[lower]) {
    return exactMap[lower];
  }
  if (lower.startsWith("core skills aligned:")) {
    return `核心技能匹配度高：${raw.slice("core skills aligned:".length).trim()}`;
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
  ([newJobId, newCandidateId]) => {
    jobId.value = (newJobId as string) || "";
    candidateId.value = (newCandidateId as string) || "";
    loadData();
  },
);
</script>

<style scoped>
.hover-lift {
  transition: all 0.2s ease;
}
.hover-lift:hover {
  transform: translateY(-2px);
  filter: brightness(1.05);
}

textarea::-webkit-scrollbar {
  width: 6px;
}
textarea::-webkit-scrollbar-thumb {
  background: rgba(0, 0, 0, 0.05);
  border-radius: 10px;
}
textarea:hover::-webkit-scrollbar-thumb {
  background: rgba(0, 0, 0, 0.1);
}
</style>
