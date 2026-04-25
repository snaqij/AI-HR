<template>
  <div class="admin-page">
    <section class="flex flex-wrap items-center justify-between gap-4 border-b border-[#eef2f7]">
      <div class="flex flex-wrap items-center gap-6">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          type="button"
          class="admin-tab"
          :class="{ 'is-active': activeTab === tab.key }"
          @click="activeTab = tab.key"
        >
          <span>{{ tab.label }}</span>
          <span>{{ tab.count }}</span>
        </button>
      </div>

      <button class="admin-quiet-btn" :disabled="isLoading" @click="loadHistory">
        <span class="material-symbols-outlined text-[16px]" :class="{ 'animate-spin': isLoading }">refresh</span>
        刷新
      </button>
    </section>

    <section class="admin-toolbar px-5 py-4">
      <div class="flex flex-col gap-4 xl:flex-row xl:items-center">
        <div class="relative min-w-0 flex-1">
          <span class="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-[16px] text-[#a9b4c4]">search</span>
          <input
            v-model.trim="keyword"
            type="text"
            placeholder="搜索候选人、岗位、面试状态"
            class="admin-input admin-search-input"
          >
        </div>

        <div class="grid grid-cols-1 gap-3 md:grid-cols-[180px_140px] xl:min-w-[340px]">
          <div class="relative">
            <select v-model="statusFilter" class="admin-select appearance-none pr-9">
              <option value="all">全部状态</option>
              <option value="pending">待发送</option>
              <option value="sending">发送中</option>
              <option value="sent">已发送</option>
              <option value="delivered">已送达</option>
              <option value="opened">已打开</option>
              <option value="clicked">已完成</option>
              <option value="failed">发送失败</option>
            </select>
            <span class="material-symbols-outlined pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-[16px] text-[#a9b4c4]">expand_more</span>
          </div>

          <button class="admin-quiet-btn" @click="resetFilters">
            <span class="material-symbols-outlined text-[16px]">restart_alt</span>
            重置
          </button>
        </div>
      </div>
    </section>

    <section class="admin-table-shell">
      <div class="grid grid-cols-[minmax(220px,1.6fr)_minmax(180px,1.4fr)_160px_140px_180px] gap-4 px-6 py-4 admin-table-head">
        <div class="admin-table-label">候选人</div>
        <div class="admin-table-label">申请岗位</div>
        <div class="admin-table-label text-center">邀请时间</div>
        <div class="admin-table-label text-center">状态</div>
        <div class="admin-table-label text-right">操作</div>
      </div>

      <div v-if="isLoading" class="admin-empty">
        <div class="h-10 w-10 animate-spin rounded-full border-4 border-primary/20 border-t-primary"></div>
        <p class="mt-4 text-sm text-on-surface-variant">正在加载邀请记录...</p>
      </div>

      <div v-else-if="filteredInvites.length === 0" class="admin-empty">
        <div class="flex h-16 w-16 items-center justify-center rounded-full bg-surface-container-low text-on-surface-variant">
          <span class="material-symbols-outlined text-[28px]">mail</span>
        </div>
        <p class="mt-4 text-sm font-semibold text-on-surface">暂无邀请记录</p>
        <p class="mt-1 text-sm text-on-surface-variant">发送候选人邀约后，会在这里查看状态与面试记录。</p>
      </div>

      <div v-else>
        <div
          v-for="invite in pagedInvites"
          :key="invite.id"
          class="admin-table-row grid grid-cols-[minmax(220px,1.6fr)_minmax(180px,1.4fr)_160px_140px_180px] gap-4 border-b border-[#f0f4fa] px-6 py-5 last:border-b-0"
        >
          <div class="min-w-0">
            <p class="truncate text-[15px] font-semibold text-on-surface">{{ invite.candidate_name }}</p>
            <p class="mt-1 truncate text-[12px] text-on-surface-variant">{{ invite.candidate_email || "-" }}</p>
          </div>
          <div class="flex items-center text-[13px] text-on-surface-variant">
            {{ invite.job_title }}
          </div>
          <div class="flex flex-col items-center justify-center text-center">
            <p class="text-[13px] font-semibold text-on-surface">{{ formatDate(invite.sent_at || invite.created_at) }}</p>
            <p class="mt-1 text-[12px] text-on-surface-variant">{{ formatTime(invite.sent_at || invite.created_at) }}</p>
          </div>
          <div class="flex items-center justify-center">
            <span class="admin-badge" :class="getStatusClass(invite.delivery_status)">
              {{ getStatusText(invite.delivery_status) }}
            </span>
          </div>
          <div class="flex items-center justify-end gap-4">
            <button class="admin-link-btn whitespace-nowrap" @click="openInterviewRecord(invite)">查看面试记录</button>
            <button
              class="text-[12px] font-semibold text-on-surface-variant transition-colors hover:text-primary whitespace-nowrap"
              @click="$router.push(`/admin/candidate-detail?jobId=${invite.job_id}&candidateId=${invite.candidate_id}`)"
            >
              详情
            </button>
          </div>
        </div>
      </div>

      <div class="flex items-center justify-between border-t border-[#eef2f7] px-6 py-4">
        <p class="text-[12px] text-on-surface-variant">共 {{ filteredInvites.length }} 条</p>
        <div class="flex items-center gap-2">
          <button class="admin-pagination-btn" :disabled="currentPage === 1" @click="currentPage = Math.max(1, currentPage - 1)">
            <span class="material-symbols-outlined text-[18px]">chevron_left</span>
          </button>
          <button
            v-for="page in visiblePages"
            :key="page"
            class="admin-pagination-btn"
            :class="{ 'is-active': page === currentPage }"
            @click="currentPage = page"
          >
            {{ page }}
          </button>
          <button class="admin-pagination-btn" :disabled="currentPage === totalPages" @click="currentPage = Math.min(totalPages, currentPage + 1)">
            <span class="material-symbols-outlined text-[18px]">chevron_right</span>
          </button>
        </div>
      </div>
    </section>

    <div
      v-if="recordDialogVisible"
      class="fixed inset-0 z-[70] flex items-center justify-center bg-black/18 p-4 backdrop-blur-[2px]"
      @click.self="closeInterviewRecord"
    >
      <div class="w-full max-w-6xl max-h-[90vh] overflow-hidden rounded-[20px] border border-[#e7edf6] bg-white shadow-[0_24px_64px_-36px_rgba(42,72,126,0.4)]">
        <div class="flex items-start justify-between border-b border-[#eef2f7] bg-[#f8fbff] px-6 py-5 lg:px-8">
          <div>
            <h3 class="text-[18px] font-semibold text-on-surface">面试记录与决策摘要</h3>
            <p class="mt-1 text-sm text-on-surface-variant">
              {{ selectedInvite?.candidate_name || "-" }} · {{ selectedInvite?.job_title || "-" }}
            </p>
          </div>
          <div class="flex items-center gap-2">
            <button
              v-if="selectedInvite"
              class="admin-quiet-btn h-9 px-4"
              @click="$router.push(`/admin/candidate-detail?jobId=${selectedInvite.job_id}&candidateId=${selectedInvite.candidate_id}`)"
            >
              打开候选人详情
            </button>
            <button
              class="flex h-9 w-9 items-center justify-center rounded-[10px] text-on-surface-variant transition-colors hover:bg-white hover:text-primary"
              @click="closeInterviewRecord"
              title="关闭"
            >
              <span class="material-symbols-outlined">close</span>
            </button>
          </div>
        </div>

        <div class="max-h-[calc(90vh-84px)] overflow-y-auto bg-background p-8">
          <div v-if="recordLoading" class="py-20 text-center">
            <div class="inline-block h-8 w-8 animate-spin rounded-full border-4 border-primary/20 border-t-primary"></div>
            <p class="mt-4 text-sm text-on-surface-variant">正在加载面试记录...</p>
          </div>

          <div v-else-if="recordError" class="py-20 text-center">
            <p class="text-sm font-semibold text-on-error-container">{{ recordError }}</p>
            <button class="admin-primary-btn mt-4" @click="selectedInvite && openInterviewRecord(selectedInvite)">重试加载</button>
          </div>

          <template v-else>
            <div class="grid grid-cols-2 gap-3 lg:grid-cols-4 lg:gap-4">
              <div class="rounded-[14px] border border-[#e7edf6] bg-white p-4">
                <p class="text-[11px] text-on-surface-variant">邀请状态</p>
                <p class="mt-2 text-[18px] font-semibold text-on-surface">{{ getStatusText(recordDetail?.delivery_status || "") }}</p>
              </div>
              <div class="rounded-[14px] border border-[#e7edf6] bg-white p-4">
                <p class="text-[11px] text-on-surface-variant">会话 ID</p>
                <p class="mt-2 text-[13px] font-semibold text-on-surface break-all">{{ recordDetail?.session_id || "尚未开始" }}</p>
              </div>
              <div class="rounded-[14px] border border-[#e7edf6] bg-white p-4">
                <p class="text-[11px] text-on-surface-variant">已作答题数</p>
                <p class="mt-2 text-[18px] font-semibold text-on-surface">{{ answeredCount }} / {{ totalQuestionCount }}</p>
              </div>
              <div class="rounded-[14px] border border-[#e7edf6] bg-white p-4">
                <p class="text-[11px] text-on-surface-variant">平均维度分</p>
                <p class="mt-2 text-[18px] font-semibold text-on-surface">{{ averageDimensionScore }}</p>
              </div>
            </div>

            <div v-if="recordDetail?.record_message" class="mt-6 rounded-[14px] border border-amber-200/60 bg-amber-50/70 p-4">
              <p class="text-sm text-on-surface-variant">{{ recordDetail.record_message }}</p>
            </div>

            <div class="mt-6 grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_340px]">
              <section class="space-y-3">
                <div class="flex items-center justify-between">
                  <h4 class="text-[16px] font-semibold text-on-surface">问答时间线</h4>
                  <span class="admin-badge bg-[#f3f6fb] text-[#708099]">共 {{ totalQuestionCount }} 题</span>
                </div>

                <div v-if="!(recordDetail?.questions.length || recordDetail?.opening_segments?.length)" class="rounded-[14px] border border-[#e7edf6] bg-white p-6 text-sm text-on-surface-variant">
                  暂无作答记录
                </div>

                <div v-else class="space-y-3">
                  <article
                    v-for="(item, index) in (recordDetail?.opening_segments || [])"
                    :key="`opening-${index}`"
                    class="rounded-[14px] border border-[#e7edf6] bg-white p-5"
                  >
                    <div class="flex items-center justify-between gap-3">
                      <p class="text-[14px] font-semibold text-primary">{{ item.title }}</p>
                      <span class="text-[11px] text-on-surface-variant">{{ item.answer_turn_no ? `轮次 #${item.answer_turn_no}` : "未记录轮次" }}</span>
                    </div>
                    <div v-if="item.followup_questions?.length" class="mt-3 rounded-[10px] border border-[#eef2f7] bg-[#f8fbff] p-3">
                      <p class="mb-2 text-[11px] text-on-surface-variant">追问</p>
                      <ul class="space-y-1.5">
                        <li
                          v-for="(followup, fidx) in item.followup_questions"
                          :key="`opening-${index}-followup-${fidx}`"
                          class="text-[12px] leading-6 text-on-surface"
                        >
                          {{ fidx + 1 }}. {{ followup }}
                        </li>
                      </ul>
                    </div>
                    <div class="mt-3 border-t border-[#eef2f7] pt-3">
                      <p class="mb-2 text-[11px] text-on-surface-variant">候选人回答</p>
                      <p class="text-[13px] leading-7 text-on-surface">{{ item.candidate_answer || "候选人尚未作答" }}</p>
                    </div>
                  </article>

                  <article
                    v-for="(item, index) in (recordDetail?.questions || [])"
                    :key="`${item.question_id}-${index}`"
                    class="rounded-[14px] border border-[#e7edf6] bg-white p-5"
                  >
                    <div class="flex items-center justify-between gap-3">
                      <p class="text-[14px] font-semibold text-primary">题目 {{ index + 1 }}</p>
                      <span class="text-[11px] text-on-surface-variant">{{ item.answer_turn_no ? `轮次 #${item.answer_turn_no}` : "未记录轮次" }}</span>
                    </div>
                    <p class="mt-2 text-[13px] font-semibold leading-7 text-on-surface">{{ item.question }}</p>
                    <div v-if="item.followup_questions?.length" class="mt-3 rounded-[10px] border border-[#eef2f7] bg-[#f8fbff] p-3">
                      <p class="mb-2 text-[11px] text-on-surface-variant">追问</p>
                      <ul class="space-y-1.5">
                        <li
                          v-for="(followup, fidx) in item.followup_questions"
                          :key="`${item.question_id}-followup-${fidx}`"
                          class="text-[12px] leading-6 text-on-surface"
                        >
                          {{ fidx + 1 }}. {{ followup }}
                        </li>
                      </ul>
                    </div>
                    <div class="mt-4 border-t border-[#eef2f7] pt-3">
                      <p class="mb-2 text-[11px] text-on-surface-variant">候选人回答</p>
                      <p class="text-[13px] leading-7 text-on-surface">{{ item.candidate_answer || "候选人尚未作答" }}</p>
                    </div>
                  </article>
                </div>
              </section>

              <aside class="space-y-4">
                <div class="rounded-[14px] border border-[#e7edf6] bg-white p-5">
                  <div class="flex items-center justify-between gap-3">
                    <h4 class="text-[16px] font-semibold text-on-surface">AI 结论</h4>
                    <span class="admin-badge border" :class="recommendationClass">{{ formatRecommendation(recordDetail?.analysis.recommendation) }}</span>
                  </div>
                  <p class="mt-3 text-[13px] leading-7 text-on-surface-variant">
                    {{ recordDetail?.analysis.summary || "暂无 AI 分析结论" }}
                  </p>
                </div>

                <div class="rounded-[14px] border border-[#e7edf6] bg-white p-5">
                  <h4 class="text-[16px] font-semibold text-on-surface">维度得分</h4>
                  <div v-if="dimensionScoreEntries.length" class="mt-4 space-y-3">
                    <div v-for="item in dimensionScoreEntries" :key="item.key">
                      <div class="mb-1 flex items-center justify-between">
                        <span class="text-[12px] text-on-surface-variant">{{ formatDimensionLabel(item.key) }}</span>
                        <span class="text-[12px] font-semibold text-on-surface">{{ item.display }}</span>
                      </div>
                      <div class="h-2 w-full overflow-hidden rounded-full bg-surface-container-high">
                        <div class="h-full rounded-full bg-primary" :style="{ width: `${item.percent}%` }"></div>
                      </div>
                    </div>
                  </div>
                  <p v-else class="mt-4 text-[13px] text-on-surface-variant">暂无维度评分</p>
                </div>

                <div class="rounded-[14px] border border-[#e7edf6] bg-white p-5">
                  <h4 class="text-[16px] font-semibold text-on-surface">风险标签</h4>
                  <div v-if="recordDetail?.analysis.risk_tags?.length" class="mt-4 flex flex-wrap gap-2">
                    <span
                      v-for="tag in recordDetail.analysis.risk_tags"
                      :key="tag"
                      class="admin-badge bg-[#fff1ef] text-[#ef6a6a]"
                    >
                      {{ tag }}
                    </span>
                  </div>
                  <p v-else class="mt-4 text-[13px] text-on-surface-variant">暂无风险标签</p>
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

type InviteTab = "all" | "pending" | "sent" | "accepted" | "rejected" | "completed";

const allInvites = ref<InterviewInvitationHistoryItem[]>([]);
const keyword = ref("");
const statusFilter = ref("all");
const activeTab = ref<InviteTab>("all");
const currentPage = ref(1);
const isLoading = ref(false);

const recordDialogVisible = ref(false);
const recordLoading = ref(false);
const recordError = ref("");
const selectedInvite = ref<InterviewInvitationHistoryItem | null>(null);
const recordDetail = ref<InterviewInvitationRecordDetailResult | null>(null);

const pageSize = 8;

const tabs = computed(() => [
  { key: "all" as InviteTab, label: "全部", count: allInvites.value.length },
  { key: "pending" as InviteTab, label: "待邀请", count: allInvites.value.filter((item) => tabKey(item) === "pending").length },
  { key: "sent" as InviteTab, label: "已发送", count: allInvites.value.filter((item) => tabKey(item) === "sent").length },
  { key: "accepted" as InviteTab, label: "已接受", count: allInvites.value.filter((item) => tabKey(item) === "accepted").length },
  { key: "rejected" as InviteTab, label: "已拒绝", count: allInvites.value.filter((item) => tabKey(item) === "rejected").length },
  { key: "completed" as InviteTab, label: "已完成", count: allInvites.value.filter((item) => tabKey(item) === "completed").length },
]);

const filteredInvites = computed(() => {
  let list = [...allInvites.value];

  if (activeTab.value !== "all") {
    list = list.filter((item) => tabKey(item) === activeTab.value);
  }

  if (statusFilter.value !== "all") {
    list = list.filter((item) => item.delivery_status === statusFilter.value);
  }

  const query = keyword.value.trim().toLowerCase();
  if (query) {
    list = list.filter((item) => `${item.candidate_name} ${item.job_title} ${item.delivery_status}`.toLowerCase().includes(query));
  }

  return list.sort((a, b) => toTimestamp(b.sent_at || b.created_at) - toTimestamp(a.sent_at || a.created_at));
});

const totalPages = computed(() => Math.max(1, Math.ceil(filteredInvites.value.length / pageSize)));

const pagedInvites = computed(() => {
  const start = (currentPage.value - 1) * pageSize;
  return filteredInvites.value.slice(start, start + pageSize);
});

const visiblePages = computed(() => {
  const pages: number[] = [];
  const start = Math.max(1, currentPage.value - 1);
  const end = Math.min(totalPages.value, start + 2);
  for (let page = start; page <= end; page += 1) {
    pages.push(page);
  }
  if (!pages.includes(1)) pages.unshift(1);
  if (!pages.includes(totalPages.value)) pages.push(totalPages.value);
  return Array.from(new Set(pages));
});

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
  if (!items.length) return "--";
  const avg = items.reduce((sum, item) => sum + item.value, 0) / items.length;
  return avg.toFixed(1);
});

const recommendationClass = computed(() => {
  const value = recordDetail.value?.analysis?.recommendation;
  if (value === "strong_recommend" || value === "recommend") {
    return "border-green-100 bg-green-50 text-green-700";
  }
  if (value === "reject") {
    return "border-rose-100 bg-rose-50 text-rose-700";
  }
  return "border-amber-100 bg-amber-50 text-amber-700";
});

function tabKey(item: InterviewInvitationHistoryItem): Exclude<InviteTab, "all"> {
  if (item.delivery_status === "failed") return "rejected";
  if (item.delivery_status === "clicked") return "completed";
  if (item.delivery_status === "opened") return "accepted";
  if (item.delivery_status === "sent" || item.delivery_status === "delivered") return "sent";
  return "pending";
}

function toTimestamp(value?: string | null): number {
  const d = new Date(value || "");
  const ts = d.getTime();
  return Number.isNaN(ts) ? 0 : ts;
}

async function loadHistory() {
  isLoading.value = true;
  try {
    const result = await fetchInterviewInvitationHistory({ limit: 300 });
    allInvites.value = result.items || [];
  } catch (error) {
    console.error("Failed to load invitation history", error);
    allInvites.value = [];
  } finally {
    isLoading.value = false;
  }
}

function resetFilters() {
  keyword.value = "";
  statusFilter.value = "all";
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
  return value.replaceAll("_", " ").replace(/\b\w/g, (char) => char.toUpperCase());
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
      return "已接受";
    case "clicked":
      return "已完成";
    case "failed":
      return "已拒绝";
    default:
      return status || "未知";
  }
}

function getStatusClass(status: string): string {
  switch (status) {
    case "sent":
    case "delivered":
      return "admin-badge-blue";
    case "opened":
    case "clicked":
      return "admin-badge-green";
    case "failed":
      return "bg-[#f3f6fb] text-[#7c889a]";
    case "sending":
      return "admin-badge-orange";
    default:
      return "bg-[#f3f6fb] text-[#7c889a]";
  }
}

function formatDate(value?: string | null): string {
  if (!value) return "--";
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date(value));
}

function formatTime(value?: string | null): string {
  if (!value) return "--";
  return new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(value));
}

watch([keyword, statusFilter, activeTab], () => {
  currentPage.value = 1;
});

watch(totalPages, (value) => {
  if (currentPage.value > value) currentPage.value = value;
});

onMounted(() => {
  loadHistory();
});
</script>
