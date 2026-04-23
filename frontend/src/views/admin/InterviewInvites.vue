<template>
  <div class="max-w-7xl mx-auto">
    <div class="flex justify-between items-center mb-10">
      <div>
        <h1 class="text-3xl font-black tracking-tight text-on-surface">面试邀请记录</h1>
        <p class="text-xs text-on-surface-variant font-bold mt-1 uppercase tracking-widest">
          跟踪所有 AI 面试邀请的状态与进展
        </p>
      </div>
    </div>

    <div class="bg-surface-container-lowest p-6 rounded-2xl shadow-sm border border-outline-variant/10 mb-8 flex items-center gap-6">
      <div class="flex-1 flex gap-4">
        <div class="relative flex-1">
          <span class="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-variant text-lg">search</span>
          <input
            v-model.trim="keyword"
            type="text"
            placeholder="搜索候选人或岗位..."
            class="w-full pl-10 pr-4 py-2 bg-surface-container-low/50 border border-outline-variant/10 rounded-lg text-xs font-medium focus:ring-2 focus:ring-primary/10 outline-none"
          >
        </div>
        <select
          v-model="activeStatus"
          class="bg-surface-container-low/50 border border-outline-variant/10 rounded-lg px-4 py-2 text-xs font-bold appearance-none cursor-pointer min-w-[140px]"
        >
          <option value="all">邀请状态</option>
          <option value="sending">发送中</option>
          <option value="sent">已发送</option>
          <option value="delivered">已送达</option>
          <option value="opened">已打开</option>
          <option value="clicked">已点击</option>
          <option value="failed">发送失败</option>
        </select>
      </div>
    </div>

    <div class="bg-surface-container-lowest rounded-2xl shadow-sm border border-outline-variant/10 overflow-hidden">
      <div class="grid grid-cols-12 bg-surface-container-low/50 px-8 py-4 text-on-surface-variant border-b border-outline-variant/5">
        <div class="col-span-3"><span class="text-xs font-black uppercase tracking-widest">候选人</span></div>
        <div class="col-span-3"><span class="text-xs font-black uppercase tracking-widest">申请岗位</span></div>
        <div class="col-span-2 text-center"><span class="text-xs font-black uppercase tracking-widest">邀请时间</span></div>
        <div class="col-span-2 text-center"><span class="text-xs font-black uppercase tracking-widest">状态</span></div>
        <div class="col-span-2 text-center"><span class="text-xs font-black uppercase tracking-widest">操作</span></div>
      </div>

      <div v-if="isLoading" class="p-20 text-center">
        <div class="inline-block w-8 h-8 border-4 border-primary/20 border-t-primary rounded-full animate-spin"></div>
        <p class="text-xs font-bold text-on-surface-variant mt-4 uppercase tracking-widest">正在加载邀请记录...</p>
      </div>

      <div v-else-if="invites.length === 0" class="p-20 text-center">
        <p class="text-xs font-bold text-on-surface-variant mt-4 uppercase tracking-widest">暂无邀请记录</p>
      </div>

      <div v-else class="divide-y divide-outline-variant/5">
        <div v-for="invite in invites" :key="invite.id" class="grid grid-cols-12 px-8 py-6 items-center hover:bg-surface/50 transition-colors group">
          <div class="col-span-3">
            <p class="font-headline font-black text-base text-on-surface group-hover:text-primary transition-colors">{{ invite.candidate_name }}</p>
            <p class="text-xs text-on-surface-variant font-bold mt-1">{{ invite.candidate_email || "-" }}</p>
          </div>
          <div class="col-span-3 font-bold text-sm text-on-surface-variant">
            {{ invite.job_title }}
          </div>
          <div class="col-span-2 text-center">
            <p class="text-sm font-bold text-on-surface">{{ formatDate(invite.sent_at || invite.created_at) }}</p>
            <p class="text-xs text-on-surface-variant opacity-60 mt-0.5">{{ formatTime(invite.sent_at || invite.created_at) }}</p>
          </div>
          <div class="col-span-2 text-center">
            <span class="px-3 py-1.5 rounded-full text-[10px] font-black tracking-widest uppercase border" :class="getStatusClass(invite.delivery_status)">
              {{ getStatusText(invite.delivery_status) }}
            </span>
          </div>
          <div class="col-span-2 grid grid-cols-2 items-center">
            <button
              @click="openInterviewRecord(invite)"
              class="text-center text-xs font-black text-primary hover:underline uppercase tracking-widest whitespace-nowrap"
            >
              查看面试记录
            </button>
            <button
              @click="$router.push(`/admin/candidate-detail?jobId=${invite.job_id}&candidateId=${invite.candidate_id}`)"
              class="text-center text-xs font-black text-on-surface-variant hover:underline uppercase tracking-widest whitespace-nowrap"
            >
              详情
            </button>
          </div>
        </div>
      </div>
    </div>

    <div
      v-if="recordDialogVisible"
      class="fixed inset-0 z-[70] bg-black/35 backdrop-blur-[1px] flex items-center justify-center p-4"
      @click.self="closeInterviewRecord"
    >
      <div class="w-full max-w-6xl max-h-[90vh] overflow-hidden bg-surface-container-lowest rounded-3xl border border-outline-variant/20 shadow-2xl">
        <div class="px-6 lg:px-8 py-5 border-b border-outline-variant/10 flex items-start justify-between bg-gradient-to-r from-surface-container-low/80 to-surface-container-high/50">
          <div>
            <h3 class="text-xl font-black text-on-surface">面试记录与决策摘要</h3>
            <p class="text-sm font-bold text-on-surface-variant mt-1">
              {{ selectedInvite?.candidate_name || "-" }} · {{ selectedInvite?.job_title || "-" }}
            </p>
          </div>
          <div class="flex items-center gap-2">
            <button
              v-if="selectedInvite"
              class="h-11 px-5 rounded-xl border border-outline-variant/20 bg-surface-container-lowest hover:bg-surface-container-low text-sm font-black text-on-surface-variant"
              @click="$router.push(`/admin/candidate-detail?jobId=${selectedInvite.job_id}&candidateId=${selectedInvite.candidate_id}`)"
            >
              打开候选人详情
            </button>
            <button
              class="w-11 h-11 rounded-xl hover:bg-surface-container-high text-on-surface-variant flex items-center justify-center"
              @click="closeInterviewRecord"
              title="关闭"
            >
              <span class="material-symbols-outlined">close</span>
            </button>
          </div>
        </div>

        <div class="p-8 overflow-y-auto max-h-[calc(90vh-84px)] bg-surface">
          <div v-if="recordLoading" class="py-20 text-center">
            <div class="inline-block w-8 h-8 border-4 border-primary/20 border-t-primary rounded-full animate-spin"></div>
            <p class="text-xs font-bold text-on-surface-variant mt-4 uppercase tracking-widest">正在加载面试记录...</p>
          </div>

          <div v-else-if="recordError" class="py-20 text-center">
            <p class="text-sm font-bold text-rose-600">{{ recordError }}</p>
            <button
              class="mt-4 px-5 py-2.5 rounded-lg bg-primary text-white text-xs font-black uppercase tracking-widest"
              @click="selectedInvite && openInterviewRecord(selectedInvite)"
            >
              重试加载
            </button>
          </div>

          <template v-else>
            <div class="grid grid-cols-2 xl:grid-cols-4 gap-3 lg:gap-4 mb-6">
              <div class="rounded-2xl border border-outline-variant/15 p-4 bg-surface-container-lowest shadow-sm">
                <p class="text-[11px] font-black uppercase tracking-widest text-on-surface-variant">邀请状态</p>
                <p class="text-lg font-black mt-2 text-on-surface">{{ getStatusText(recordDetail?.delivery_status || "") }}</p>
              </div>
              <div class="rounded-2xl border border-outline-variant/15 p-4 bg-surface-container-lowest shadow-sm">
                <p class="text-[11px] font-black uppercase tracking-widest text-on-surface-variant">会话 ID</p>
                <p class="text-sm font-bold mt-2 text-on-surface break-all">{{ recordDetail?.session_id || "尚未开始" }}</p>
              </div>
              <div class="rounded-2xl border border-outline-variant/15 p-4 bg-surface-container-lowest shadow-sm">
                <p class="text-[11px] font-black uppercase tracking-widest text-on-surface-variant">已作答题数</p>
                <p class="text-lg font-black mt-2 text-on-surface">{{ answeredCount }} / {{ totalQuestionCount }}</p>
              </div>
              <div class="rounded-2xl border border-outline-variant/15 p-4 bg-surface-container-lowest shadow-sm">
                <p class="text-[11px] font-black uppercase tracking-widest text-on-surface-variant">平均维度分</p>
                <p class="text-lg font-black mt-2 text-on-surface">{{ averageDimensionScore }}</p>
              </div>
            </div>

            <div v-if="recordDetail?.record_message" class="mb-6 rounded-2xl border border-amber-200/60 p-4 bg-amber-50/70">
              <p class="text-sm font-bold text-on-surface-variant">{{ recordDetail.record_message }}</p>
            </div>

            <div class="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_380px] gap-6">
              <section class="min-w-0">
                <div class="flex items-center justify-between mb-4">
                  <h4 class="text-xl font-black tracking-tight text-on-surface">问答时间线</h4>
                  <span class="px-3 py-1 rounded-full bg-surface-container-low text-xs font-black text-on-surface-variant">共 {{ totalQuestionCount }} 题（含开场）</span>
                </div>

                <div v-if="!(recordDetail?.questions.length || recordDetail?.opening_segments?.length)" class="rounded-2xl border border-outline-variant/15 p-6 bg-surface-container-lowest shadow-sm text-sm font-bold text-on-surface-variant">
                  暂无作答记录
                </div>

                <div v-else class="space-y-3">
                  <article
                    v-for="(item, index) in (recordDetail?.opening_segments || [])"
                    :key="`opening-${index}`"
                    class="rounded-2xl border border-outline-variant/15 p-5 bg-surface-container-lowest shadow-sm"
                  >
                    <div class="flex items-center justify-between mb-2">
                      <p class="text-base font-black tracking-tight text-primary">{{ item.title }}</p>
                      <span class="text-[11px] font-bold text-on-surface-variant">
                        {{ item.answer_turn_no ? `轮次 #${item.answer_turn_no}` : "未记录轮次" }}
                      </span>
                    </div>
                    <div class="pt-2 border-t border-outline-variant/10">
                      <p class="text-[11px] font-black uppercase tracking-widest text-on-surface-variant mb-2">候选人回答</p>
                      <p class="text-sm font-medium text-on-surface whitespace-pre-wrap break-words">{{ item.candidate_answer || "候选人尚未作答" }}</p>
                    </div>
                  </article>

                  <article
                    v-for="(item, index) in recordDetail.questions"
                    :key="`${item.question_id}-${index}`"
                    class="rounded-2xl border border-outline-variant/15 p-5 bg-surface-container-lowest shadow-sm"
                  >
                    <div class="flex items-center justify-between mb-2">
                      <p class="text-base font-black tracking-tight text-primary">题目 {{ index + 1 }}</p>
                      <span class="text-[11px] font-bold text-on-surface-variant">
                        {{ item.answer_turn_no ? `轮次 #${item.answer_turn_no}` : "未记录轮次" }}
                      </span>
                    </div>
                    <p class="text-sm font-semibold text-on-surface leading-relaxed">{{ item.question }}</p>
                    <div class="mt-4 pt-4 border-t border-outline-variant/10">
                      <p class="text-[11px] font-black uppercase tracking-widest text-on-surface-variant mb-2">候选人回答</p>
                      <p class="text-sm font-medium text-on-surface whitespace-pre-wrap break-words">{{ item.candidate_answer || "候选人尚未作答" }}</p>
                    </div>
                  </article>
                </div>
              </section>

              <aside class="space-y-4 xl:sticky xl:top-0 h-fit">
                <div class="rounded-2xl border border-outline-variant/15 p-5 bg-surface-container-lowest shadow-sm">
                  <div class="flex items-center justify-between mb-3">
                    <h4 class="text-xl font-black tracking-tight text-on-surface">AI 结论</h4>
                    <span class="px-3 py-1 rounded-full text-[10px] font-black tracking-widest uppercase border" :class="recommendationClass">
                      {{ formatRecommendation(recordDetail?.analysis.recommendation) }}
                    </span>
                  </div>
                  <p class="text-sm font-medium text-on-surface whitespace-pre-wrap break-words">
                    {{ recordDetail?.analysis.summary || "暂无 AI 分析结论" }}
                  </p>
                </div>

                <div class="rounded-2xl border border-outline-variant/15 p-5 bg-surface-container-lowest shadow-sm">
                  <h4 class="text-xl font-black tracking-tight text-on-surface mb-3">维度得分</h4>
                  <div v-if="dimensionScoreEntries.length" class="space-y-3">
                    <div v-for="item in dimensionScoreEntries" :key="item.key">
                      <div class="flex items-center justify-between mb-1">
                        <span class="text-xs font-bold text-on-surface-variant">{{ formatDimensionLabel(item.key) }}</span>
                        <span class="text-xs font-black text-on-surface">{{ item.display }}</span>
                      </div>
                      <div class="h-2 w-full bg-surface-container-high rounded-full overflow-hidden">
                        <div class="h-full bg-primary rounded-full" :style="{ width: `${item.percent}%` }"></div>
                      </div>
                    </div>
                  </div>
                  <p v-else class="text-sm font-medium text-on-surface-variant">暂无维度评分</p>
                </div>

                <div class="rounded-2xl border border-outline-variant/15 p-5 bg-surface-container-lowest shadow-sm">
                  <h4 class="text-xl font-black tracking-tight text-on-surface mb-3">风险标签</h4>
                  <div v-if="recordDetail?.analysis.risk_tags?.length" class="flex flex-wrap gap-2">
                    <span
                      v-for="tag in recordDetail.analysis.risk_tags"
                      :key="tag"
                      class="px-3 py-1 rounded-full bg-rose-50 text-rose-700 text-xs font-black"
                    >
                      {{ tag }}
                    </span>
                  </div>
                  <p v-else class="text-sm font-medium text-on-surface-variant">暂无风险标签</p>
                </div>
              </aside>
            </div>
          </template>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import {
  fetchInterviewInvitationHistory,
  fetchInterviewInvitationRecord,
  type InterviewInvitationHistoryItem,
  type InterviewInvitationRecordDetailResult,
} from "../../api";

const invites = ref<InterviewInvitationHistoryItem[]>([]);
const keyword = ref("");
const activeStatus = ref("all");
const isLoading = ref(false);
const recordDialogVisible = ref(false);
const recordLoading = ref(false);
const recordError = ref("");
const selectedInvite = ref<InterviewInvitationHistoryItem | null>(null);
const recordDetail = ref<InterviewInvitationRecordDetailResult | null>(null);
let filterDebounceTimer: ReturnType<typeof setTimeout> | null = null;

const dimensionScoreEntries = computed(() => {
  const source = recordDetail.value?.analysis?.dimension_scores || {};
  return Object.keys(source)
    .map((key) => {
      const raw = Number(source[key] || 0);
      const normalized = Math.max(0, Math.min(raw, 100));
      return {
        key,
        value: raw,
        percent: normalized,
        display: Number.isFinite(raw) ? raw.toFixed(1) : "--",
      };
    })
    .sort((a, b) => b.value - a.value);
});

const answeredCount = computed(() => {
  const questionCount = (recordDetail.value?.questions || []).filter((item) => (item.candidate_answer || "").trim()).length;
  const openingCount = (recordDetail.value?.opening_segments || []).filter((item) => (item.candidate_answer || "").trim()).length;
  return questionCount + openingCount;
});

const totalQuestionCount = computed(() => {
  const questionCount = recordDetail.value?.questions.length || 0;
  const openingCount = recordDetail.value?.opening_segments.length || 0;
  return questionCount + openingCount;
});

const averageDimensionScore = computed(() => {
  const items = dimensionScoreEntries.value;
  if (!items.length) {
    return "--";
  }
  const avg = items.reduce((sum, item) => sum + item.value, 0) / items.length;
  return avg.toFixed(1);
});

const recommendationClass = computed(() => {
  const value = recordDetail.value?.analysis?.recommendation;
  if (value === "strong_recommend" || value === "recommend") {
    return "bg-green-50 text-green-700 border-green-100";
  }
  if (value === "reject") {
    return "bg-rose-50 text-rose-700 border-rose-100";
  }
  return "bg-amber-50 text-amber-700 border-amber-100";
});

async function loadHistory() {
  isLoading.value = true;
  try {
    const result = await fetchInterviewInvitationHistory({
      limit: 300,
      keyword: keyword.value || undefined,
      status: activeStatus.value,
    });
    invites.value = result.items;
  } catch (error) {
    console.error("Failed to load invitation history", error);
    invites.value = [];
  } finally {
    isLoading.value = false;
  }
}

async function openInterviewRecord(invite: InterviewInvitationHistoryItem) {
  selectedInvite.value = invite;
  recordDialogVisible.value = true;
  recordError.value = "";
  recordDetail.value = null;
  recordLoading.value = true;
  try {
    recordDetail.value = await fetchInterviewInvitationRecord(invite.id);
  } catch (error) {
    console.error("Failed to load interview record", error);
    recordError.value = "加载面试记录失败，请稍后重试。";
  } finally {
    recordLoading.value = false;
  }
}

function closeInterviewRecord() {
  recordDialogVisible.value = false;
  recordLoading.value = false;
  recordError.value = "";
  selectedInvite.value = null;
  recordDetail.value = null;
}

function formatRecommendation(value?: string | null): string {
  switch (value) {
    case "strong_recommend":
      return "强烈推荐";
    case "recommend":
      return "推荐";
    case "review":
    case "manual_review":
      return "待复核";
    case "reject":
      return "不推荐";
    default:
      return value || "暂无";
  }
}

function formatDimensionLabel(value: string): string {
  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function getStatusText(status: string): string {
  switch (status) {
    case "pending":
      return "待发送";
    case "sending":
      return "发送中";
    case "sent":
      return "已发送";
    case "delivered":
      return "已送达";
    case "opened":
      return "已打开";
    case "clicked":
      return "已点击";
    case "failed":
      return "发送失败";
    default:
      return status || "未知";
  }
}

function getStatusClass(status: string): string {
  switch (status) {
    case "sent":
    case "delivered":
    case "opened":
    case "clicked":
      return "bg-green-50 text-green-700 border-green-100";
    case "sending":
      return "bg-primary/10 text-primary border-primary/10";
    case "failed":
      return "bg-rose-50 text-rose-700 border-rose-100";
    default:
      return "bg-surface-container-high text-on-surface-variant/60 border-outline-variant/10";
  }
}

function formatDate(value: string): string {
  return new Date(value).toLocaleDateString("zh-CN");
}

function formatTime(value: string): string {
  return new Date(value).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
}

watch([keyword, activeStatus], () => {
  if (filterDebounceTimer) {
    clearTimeout(filterDebounceTimer);
  }
  filterDebounceTimer = setTimeout(() => {
    loadHistory();
  }, 250);
});

onMounted(() => {
  loadHistory();
});
</script>
