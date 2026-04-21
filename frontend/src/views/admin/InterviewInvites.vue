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
      <div class="w-full max-w-5xl max-h-[90vh] overflow-hidden bg-surface-container-lowest rounded-3xl border border-outline-variant/10 shadow-2xl">
        <div class="px-8 py-5 border-b border-outline-variant/10 flex items-center justify-between">
          <div>
            <h3 class="text-xl font-black text-on-surface">面试记录</h3>
            <p class="text-xs font-bold text-on-surface-variant mt-1">
              {{ selectedInvite?.candidate_name || "-" }} · {{ selectedInvite?.job_title || "-" }}
            </p>
          </div>
          <button
            class="w-10 h-10 rounded-xl hover:bg-surface-container-high text-on-surface-variant flex items-center justify-center"
            @click="closeInterviewRecord"
            title="关闭"
          >
            <span class="material-symbols-outlined">close</span>
          </button>
        </div>

        <div class="p-8 overflow-y-auto max-h-[calc(90vh-84px)]">
          <div v-if="recordLoading" class="py-20 text-center">
            <div class="inline-block w-8 h-8 border-4 border-primary/20 border-t-primary rounded-full animate-spin"></div>
            <p class="text-xs font-bold text-on-surface-variant mt-4 uppercase tracking-widest">正在加载面试记录...</p>
          </div>

          <div v-else-if="recordError" class="py-20 text-center">
            <p class="text-sm font-bold text-rose-600">{{ recordError }}</p>
          </div>

          <template v-else>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
              <div class="rounded-2xl border border-outline-variant/10 p-4 bg-surface-container-low/40">
                <p class="text-[11px] font-black uppercase tracking-widest text-on-surface-variant">邀请状态</p>
                <p class="text-sm font-bold mt-2 text-on-surface">{{ getStatusText(recordDetail?.delivery_status || "") }}</p>
              </div>
              <div class="rounded-2xl border border-outline-variant/10 p-4 bg-surface-container-low/40">
                <p class="text-[11px] font-black uppercase tracking-widest text-on-surface-variant">会话 ID</p>
                <p class="text-sm font-bold mt-2 text-on-surface break-all">{{ recordDetail?.session_id || "尚未开始" }}</p>
              </div>
            </div>

            <div v-if="recordDetail?.record_message" class="mb-6 rounded-2xl border border-outline-variant/10 p-4 bg-surface-container-low/40">
              <p class="text-sm font-bold text-on-surface-variant">{{ recordDetail.record_message }}</p>
            </div>

            <div class="mb-8">
              <div class="flex items-center justify-between mb-4">
                <h4 class="text-base font-black text-on-surface">题目与作答</h4>
                <span class="text-[11px] font-bold text-on-surface-variant">共 {{ recordDetail?.questions.length || 0 }} 题</span>
              </div>

              <div v-if="!recordDetail?.questions.length" class="rounded-2xl border border-outline-variant/10 p-5 bg-surface-container-low/40 text-sm font-bold text-on-surface-variant">
                暂无作答记录
              </div>

              <div v-else class="space-y-4">
                <div
                  v-for="(item, index) in recordDetail.questions"
                  :key="`${item.question_id}-${index}`"
                  class="rounded-2xl border border-outline-variant/10 p-5 bg-surface-container-low/40"
                >
                  <p class="text-xs font-black tracking-widest uppercase text-primary mb-2">题目 {{ index + 1 }}</p>
                  <p class="text-sm font-bold text-on-surface leading-relaxed">{{ item.question }}</p>
                  <div class="mt-4 pt-4 border-t border-outline-variant/10">
                    <p class="text-[11px] font-black uppercase tracking-widest text-on-surface-variant mb-2">候选人回答</p>
                    <p class="text-sm font-medium text-on-surface whitespace-pre-wrap break-words">{{ item.candidate_answer || "候选人尚未作答" }}</p>
                  </div>
                </div>
              </div>
            </div>

            <div class="rounded-2xl border border-outline-variant/10 p-5 bg-surface-container-low/40">
              <h4 class="text-base font-black text-on-surface mb-4">AI 分析结果</h4>
              <div class="space-y-4">
                <div>
                  <p class="text-[11px] font-black uppercase tracking-widest text-on-surface-variant mb-1">综合结论</p>
                  <p class="text-sm font-medium text-on-surface whitespace-pre-wrap break-words">{{ recordDetail?.analysis.summary || "暂无 AI 分析结论" }}</p>
                </div>
                <div>
                  <p class="text-[11px] font-black uppercase tracking-widest text-on-surface-variant mb-1">推荐建议</p>
                  <p class="text-sm font-bold text-on-surface">{{ formatRecommendation(recordDetail?.analysis.recommendation) }}</p>
                </div>
                <div>
                  <p class="text-[11px] font-black uppercase tracking-widest text-on-surface-variant mb-2">维度得分</p>
                  <div v-if="dimensionScoreEntries.length" class="flex flex-wrap gap-2">
                    <span
                      v-for="item in dimensionScoreEntries"
                      :key="item.key"
                      class="px-3 py-1 rounded-full bg-primary/10 text-primary text-xs font-black"
                    >
                      {{ item.key }}: {{ item.value }}
                    </span>
                  </div>
                  <p v-else class="text-sm font-medium text-on-surface-variant">暂无维度评分</p>
                </div>
                <div>
                  <p class="text-[11px] font-black uppercase tracking-widest text-on-surface-variant mb-2">风险标签</p>
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
              </div>
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
    .map((key) => ({ key, value: source[key] }))
    .sort((a, b) => Number(b.value || 0) - Number(a.value || 0));
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
    case "manual_review":
      return "待复核";
    case "reject":
      return "不推荐";
    default:
      return value || "暂无";
  }
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
