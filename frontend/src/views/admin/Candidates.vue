<template>
  <div class="max-w-7xl mx-auto flex flex-col gap-5">
    <div class="bg-surface-container-lowest p-6 rounded-2xl border border-outline-variant/10 shadow-sm" v-if="job">
      <div class="flex items-center justify-between mb-5">
        <div class="flex flex-col gap-1.5">
          <div class="flex items-center gap-2 text-on-surface-variant mb-1">
            <router-link
              to="/admin/jobs"
              class="text-xs font-black tracking-widest uppercase hover:text-primary transition-colors flex items-center gap-1.5"
            >
              <span class="material-symbols-outlined text-base">arrow_back</span>
              岗位管理
            </router-link>
            <span class="material-symbols-outlined text-base opacity-30">chevron_right</span>
            <span class="text-xs font-black tracking-widest uppercase text-primary">候选人管理</span>
          </div>
          <h2 class="font-headline text-3xl font-black tracking-tight text-on-surface">{{ job.title }}</h2>
        </div>

        <div class="flex gap-3 items-center">
          <button
            @click="refreshData"
            class="flex items-center gap-2 px-5 py-3 bg-surface-container-low rounded-xl text-[13px] font-black text-on-surface-variant uppercase tracking-widest hover:bg-surface-container-high transition-all"
          >
            <span class="material-symbols-outlined text-base" :class="{ 'animate-spin': isLoading }">refresh</span>
            刷新列表
          </button>
          <button
            @click="handleSync"
            :disabled="isSyncing"
            class="flex items-center gap-2 px-6 py-3 bg-primary text-white rounded-xl text-[13px] font-black uppercase tracking-widest shadow-lg shadow-primary/20 hover:brightness-110 active:scale-95 transition-all disabled:opacity-50 disabled:cursor-wait"
          >
            <span class="material-symbols-outlined text-base font-black" :class="{ 'animate-spin': isSyncing }">
              {{ isSyncing ? "sync" : "cloud_sync" }}
            </span>
            {{ isSyncing ? "正在同步..." : "同步候选人" }}
          </button>
        </div>
      </div>

      <div
        class="flex items-center gap-8 text-on-surface-variant font-bold text-sm uppercase tracking-widest opacity-90 border-t border-outline-variant/5 pt-5"
      >
        <div class="flex items-center gap-2">
          <span class="material-symbols-outlined text-lg text-primary">location_on</span>
          <span>{{ job.city }} · {{ job.department || "默认部门" }}</span>
        </div>
        <div class="flex items-center gap-2">
          <span class="material-symbols-outlined text-lg text-primary">calendar_today</span>
          <span>发布时间 {{ formatDate(job.published_at || job.created_at) }}</span>
        </div>
        <div class="h-4 w-px bg-outline-variant/20"></div>
        <div class="flex items-center gap-2">
          <span class="text-on-surface font-black">{{ syncedTotalCandidates }}</span>
          <span class="text-[11px] opacity-60">已同步候选人</span>
        </div>
        <div class="flex items-center gap-2">
          <span class="text-tertiary font-black">{{ evaluatedCount }}</span>
          <span class="text-[11px] opacity-60">已评估</span>
        </div>
        <div class="flex items-center gap-2">
          <span class="text-primary font-black">{{ sentDeliveryCount }}</span>
          <span class="text-[11px] opacity-60">已发送邮件</span>
        </div>
      </div>
    </div>

    <div class="bg-surface-container-lowest rounded-2xl shadow-sm border border-outline-variant/10 overflow-hidden min-h-[500px]">
      <div class="flex items-center justify-between px-8 py-5 border-b border-outline-variant/10 bg-surface-container-low/10">
        <div class="flex gap-2">
          <button
            v-for="tab in tabs"
            :key="tab.key"
            @click="handleTabChange(tab.key)"
            class="px-5 py-2.5 text-xs font-black uppercase tracking-widest rounded-full transition-all"
            :class="
              activeTab === tab.key
                ? 'bg-on-surface text-white shadow-md'
                : 'bg-surface-container-high text-on-surface-variant/70 hover:bg-surface-container-highest border border-outline-variant/5'
            "
          >
            {{ tab.label }}
          </button>
        </div>

        <div class="flex items-center gap-4">
          <div class="relative min-w-[160px]">
            <span class="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-variant/50 text-base">
              filter_list
            </span>
            <select
              v-model="activeResumeStatus"
              class="pl-10 pr-8 py-2 bg-surface-container-lowest border border-outline-variant/20 rounded-xl text-xs font-black uppercase tracking-widest focus:ring-2 focus:ring-primary/10 outline-none w-full shadow-inner appearance-none cursor-pointer"
            >
              <option v-for="opt in resumeStatusOptions" :key="opt.value" :value="opt.value">
                {{ opt.label }}
              </option>
            </select>
            <span class="material-symbols-outlined absolute right-2 top-1/2 -translate-y-1/2 text-on-surface-variant/30 text-base pointer-events-none">
              expand_more
            </span>
          </div>

          <div class="relative">
            <span class="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-variant/50 text-base">
              search
            </span>
            <input
              v-model.trim="keyword"
              type="text"
              placeholder="搜索候选人..."
              class="pl-10 pr-4 py-2 bg-surface-container-lowest border border-outline-variant/20 rounded-xl text-sm focus:ring-2 focus:ring-primary/10 outline-none w-64 shadow-inner"
            >
          </div>
        </div>
      </div>

      <div class="grid grid-cols-12 bg-surface-container-low/50 px-8 py-4 text-on-surface-variant/60 border-b border-outline-variant/5">
        <div class="col-span-3"><span class="text-[11px] font-black uppercase tracking-widest">候选人基础资料</span></div>
        <div class="col-span-2 text-center"><span class="text-[11px] font-black uppercase tracking-widest">教育与工作背景</span></div>
        <div class="col-span-2 text-center"><span class="text-[11px] font-black uppercase tracking-widest">简历状态</span></div>
        <div class="col-span-2 text-center">
          <div class="inline-flex items-center gap-1.5">
            <span class="text-[11px] font-black uppercase tracking-widest">评估结果</span>
            <button
              type="button"
              class="w-5 h-5 rounded-md hover:bg-surface-container-high text-on-surface-variant/70 hover:text-primary transition-colors inline-flex items-center justify-center"
              :title="scoreSortOrder === 'desc' ? '按分数降序' : '按分数升序'"
              @click="toggleScoreSort"
            >
              <span class="material-symbols-outlined text-sm leading-none">
                {{ scoreSortOrder === "desc" ? "arrow_downward" : "arrow_upward" }}
              </span>
            </button>
          </div>
        </div>
        <div class="col-span-1 text-center"><span class="text-[11px] font-black uppercase tracking-widest">邮件</span></div>
        <div class="col-span-2 text-center"><span class="text-[11px] font-black uppercase tracking-widest">操作</span></div>
      </div>

      <div v-if="!isLoading && filteredCandidates.length > 0" class="divide-y divide-outline-variant/5">
        <div
          v-for="item in filteredCandidates"
          :key="item.external_candidate_id"
          class="grid grid-cols-12 px-8 py-5 items-center hover:bg-surface/60 transition-all group border-l-[4px] border-transparent hover:border-primary"
        >
          <div class="col-span-3">
            <div class="flex items-center gap-4">
              <div class="w-12 h-12 rounded-2xl ai-gradient flex items-center justify-center text-white text-lg font-black shadow-lg shadow-primary/10">
                {{ item.candidate.name.charAt(0) }}
              </div>
              <div>
                <p class="font-headline font-black text-base text-on-surface group-hover:text-primary transition-colors">
                  {{ item.candidate.name }}
                </p>
                <p class="text-xs text-on-surface-variant font-bold mt-1 uppercase tracking-widest flex items-center gap-2 opacity-60">
                  <span class="w-2 h-2 bg-green-500 rounded-full shadow-[0_0_8px_rgba(34,197,94,0.5)]"></span>
                  首次同步 {{ formatDate(item.first_synced_at) }}
                </p>
              </div>
            </div>
          </div>

          <div class="col-span-2 text-center">
            <p v-if="buildEducationLine(item)" class="text-[13px] text-on-surface font-black uppercase tracking-tight">
              {{ buildEducationLine(item) }}
            </p>
            <p
              v-if="buildExperienceLine(item)"
              class="text-xs text-on-surface-variant font-bold mt-1.5 uppercase tracking-widest opacity-60"
            >
              {{ buildExperienceLine(item) }}
            </p>
          </div>

          <div class="col-span-2 text-center">
             <div class="flex flex-col items-center gap-1.5">
                <span
                  class="px-3 py-1 rounded-full text-[10px] font-black tracking-widest uppercase border transition-all"
                  :class="getResumeStatusBadge(item)"
                >
                  {{ getResumeStatusText(item) }}
                </span>
                <p v-if="item.last_resume_requested_at" class="text-[9px] text-on-surface-variant/40 font-bold uppercase tracking-tighter">
                    {{ formatDate(item.last_resume_requested_at) }}
                </p>
             </div>
          </div>

          <div class="col-span-2 text-center">
            <template v-if="evaluationByCandidateId[item.candidate.id]">
              <div class="flex flex-col items-center gap-2">
                <span class="text-xl font-black text-primary leading-none">
                  {{ formatScore(evaluationByCandidateId[item.candidate.id].final_score) }}
                </span>
                <span
                  class="px-3 py-1 rounded-full text-[10px] font-black tracking-widest uppercase"
                  :class="getRecommendationBadge(getEffectiveRecommendation(item.candidate.id))"
                >
                  {{ getRecommendationText(getEffectiveRecommendation(item.candidate.id)) }}
                </span>
              </div>
            </template>
            <p v-else class="text-xs font-bold text-on-surface-variant/70 uppercase tracking-widest">未评估</p>
          </div>

          <div class="col-span-1 text-center">
            <template v-if="latestDeliveryByCandidateId[item.candidate.id]">
              <div class="flex flex-col items-center gap-1">
                <span
                  class="px-2 py-0.5 rounded-full text-[9px] font-black tracking-widest uppercase"
                  :class="getDeliveryBadge(latestDeliveryByCandidateId[item.candidate.id].status)"
                >
                  {{ getDeliveryText(latestDeliveryByCandidateId[item.candidate.id].status) }}
                </span>
              </div>
            </template>
            <p v-else class="text-[10px] font-bold text-on-surface-variant/40 uppercase tracking-widest">无</p>
          </div>

          <div class="col-span-2 flex justify-center gap-3">
            <button
              class="px-4 h-11 rounded-xl hover:bg-primary/10 text-on-surface-variant hover:text-primary transition-all flex items-center justify-center border border-outline-variant/10 whitespace-nowrap"
              @click="handleViewDetails(item)"
            >
              详情
            </button>
            <button
              class="px-4 h-11 rounded-xl bg-surface-container-low text-primary hover:bg-primary hover:text-white transition-all flex items-center justify-center shadow-md border border-primary/5 disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap"
              :disabled="sendingCandidateId === item.candidate.id"
              @click="handleManualInvite(item)"
            >
              {{ sendingCandidateId === item.candidate.id ? "发送中" : "发送邀约" }}
            </button>
          </div>
        </div>
      </div>
      <div
        v-if="!isLoading && filteredCandidates.length > 0 && hasMoreCandidates && keyword.trim() === ''"
        class="px-8 py-5 border-t border-outline-variant/5 flex justify-center"
      >
        <button
          class="px-6 py-2.5 rounded-xl bg-surface-container-low text-on-surface-variant text-xs font-black uppercase tracking-widest disabled:opacity-50"
          :disabled="isLoadingMoreCandidates"
          @click="loadMoreCandidates"
        >
          {{ isLoadingMoreCandidates ? "加载中..." : "加载更多候选人" }}
        </button>
      </div>

      <div v-if="jobId && !isLoading && filteredCandidates.length === 0" class="p-40 text-center">
        <div class="w-24 h-24 bg-surface-container-low rounded-full flex items-center justify-center mx-auto mb-6">
          <span class="material-symbols-outlined text-5xl text-on-surface-variant/20">person_add</span>
        </div>
        <p class="text-lg font-black text-on-surface-variant uppercase tracking-widest">暂无候选人</p>
        <p class="text-xs font-bold text-on-surface-variant/50 mt-2 uppercase tracking-widest">
          请点击右上角按钮同步 BOSS 平台候选人
        </p>
      </div>

      <div v-if="jobId && isLoading" class="p-40 text-center">
        <div class="inline-block w-10 h-10 border-4 border-primary/20 border-t-primary rounded-full animate-spin"></div>
        <p class="text-sm font-black text-on-surface-variant mt-6 uppercase tracking-widest">正在加载候选人数据...</p>
      </div>

      <div v-if="!jobId" class="p-40 text-center">
        <div class="w-24 h-24 bg-surface-container-low rounded-full flex items-center justify-center mx-auto mb-6">
          <span class="material-symbols-outlined text-5xl text-on-surface-variant/20 scale-150">work_history</span>
        </div>
        <p class="text-lg font-black text-on-surface uppercase tracking-widest mb-2">未选择岗位</p>
        <p class="text-xs font-bold text-on-surface-variant/60 uppercase tracking-widest mb-8">
          请先返回岗位管理并进入一个岗位
        </p>
        <router-link
          to="/admin/jobs"
          class="inline-flex items-center gap-2 px-8 py-3 bg-primary text-white rounded-xl text-sm font-black uppercase tracking-widest shadow-lg shadow-primary/20"
        >
          前往岗位中心
        </router-link>
      </div>
    </div>

    <div
      v-if="inviteDialogVisible"
      class="fixed top-24 left-1/2 -translate-x-1/2 z-50 px-4 pointer-events-none"
    >
      <div class="w-full max-w-md rounded-2xl bg-surface-container-lowest border border-outline-variant/20 shadow-2xl p-6 pointer-events-auto">
        <h3 class="text-lg font-black text-on-surface">发送邀约确认</h3>
        <p class="mt-3 text-sm text-on-surface-variant leading-relaxed">{{ inviteDialogMessage }}</p>
        <div class="mt-6 flex items-center justify-end gap-3">
          <button
            class="px-4 h-10 rounded-xl bg-surface-container-low text-on-surface-variant font-bold border border-outline-variant/20 hover:bg-surface-container-high transition-all"
            :disabled="inviteDialogSending"
            @click="closeInviteDialog"
          >
            取消
          </button>
          <button
            class="px-4 h-10 rounded-xl bg-primary text-white font-bold hover:brightness-110 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
            :disabled="!inviteDialogAllowSend || inviteDialogSending"
            @click="confirmInviteDialog"
          >
            {{ inviteDialogSending ? "发送中..." : "确认发送" }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  fetchJobEmailDeliveries,
  fetchJobEvaluations,
  getJob,
  listJobCandidates,
  sendCandidateInvitationEmail,
  syncJobCandidates,
  type CandidateEmailDelivery,
  type CandidateEvaluation,
  type Job,
  type JobCandidate,
} from "../../api";

const route = useRoute();
const router = useRouter();

const jobId = ref((route.query.jobId as string) || "");
const job = ref<Job | null>(null);
const candidates = ref<JobCandidate[]>([]);
const evaluations = ref<CandidateEvaluation[]>([]);
const deliveries = ref<CandidateEmailDelivery[]>([]);
const keyword = ref("");
const activeTab = ref("all");
const activeResumeStatus = ref("all");
const isLoading = ref(false);
const isSyncing = ref(false);
const sendingCandidateId = ref("");
const candidatesNextCursor = ref<string | null>(null);
const hasMoreCandidates = ref(false);
const isLoadingMoreCandidates = ref(false);
const syncedTotalCandidates = ref(0);
const evaluatedCount = ref(0);
const sentDeliveryCount = ref(0);
const scoreSortOrder = ref<"asc" | "desc">("desc");
const recommendScoreThreshold = 80;
const manualInviteScoreThreshold = 75;
const inviteDialogVisible = ref(false);
const inviteDialogMessage = ref("");
const inviteDialogAllowSend = ref(false);
const inviteDialogCandidate = ref<JobCandidate | null>(null);
const pageSize = 30;
const keywordDebounced = ref("");
let keywordDebounceTimer: ReturnType<typeof setTimeout> | null = null;

const tabs = [
  { key: "all", label: "全部候选人" },
  { key: "recommended", label: "AI 推荐" },
  { key: "invited", label: "已发邀约" },
  { key: "failed", label: "发送失败" },
];

const resumeStatusOptions = [
  { value: "all", label: "全部简历状态" },
  { value: "downloaded", label: "简历已获取" },
  { value: "requested", label: "全自动申请中" },
  { value: "failed", label: "申请失败" },
  { value: "pending", label: "待申请" },
];

const evaluationByCandidateId = computed<Record<string, CandidateEvaluation>>(() => {
  const map: Record<string, CandidateEvaluation> = {};
  for (const evaluation of evaluations.value) {
    map[evaluation.candidate_id] = evaluation;
  }
  return map;
});

const latestDeliveryByCandidateId = computed<Record<string, CandidateEmailDelivery>>(() => {
  const map: Record<string, CandidateEmailDelivery> = {};
  for (const delivery of deliveries.value) {
    if (!map[delivery.candidate_id]) {
      map[delivery.candidate_id] = delivery;
    }
  }
  return map;
});

// Stats are now ref-based and updated from API response

const filteredCandidates = computed(() => {
  let result = [...candidates.value];

  if (activeTab.value === "recommended") {
    result = result.filter((item) => {
      const recommendation = getEffectiveRecommendation(item.candidate.id);
      return recommendation === "recommend" || recommendation === "strong_recommend";
    });
  } else if (activeTab.value === "invited") {
    result = result.filter((item) => {
      const status = latestDeliveryByCandidateId.value[item.candidate.id]?.status;
      return status ? ["sending", "sent", "delivered", "opened", "clicked"].includes(status) : false;
    });
  } else if (activeTab.value === "failed") {
    result = result.filter((item) => latestDeliveryByCandidateId.value[item.candidate.id]?.status === "failed");
  }

  result.sort((left, right) => {
    const leftScore = getCandidateFinalScore(left);
    const rightScore = getCandidateFinalScore(right);

    if (leftScore === null && rightScore === null) {
      return 0;
    }
    if (leftScore === null) {
      return 1;
    }
    if (rightScore === null) {
      return -1;
    }
    return scoreSortOrder.value === "desc" ? rightScore - leftScore : leftScore - rightScore;
  });

  return result;
});

const inviteDialogSending = computed(() => {
  const candidateId = inviteDialogCandidate.value?.candidate.id || "";
  return Boolean(candidateId && sendingCandidateId.value === candidateId);
});

function toggleScoreSort() {
  scoreSortOrder.value = scoreSortOrder.value === "desc" ? "asc" : "desc";
}

function resolveCandidateSegment() {
  if (activeTab.value === "recommended" || activeTab.value === "invited" || activeTab.value === "failed") {
    return activeTab.value;
  }
  return "all";
}

async function handleTabChange(tabKey: string) {
  if (activeTab.value === tabKey) {
    return;
  }
  activeTab.value = tabKey;
  candidatesNextCursor.value = null;
  hasMoreCandidates.value = false;
  await refreshData();
}

function getCandidateFinalScore(item: JobCandidate): number | null {
  const score = evaluationByCandidateId.value[item.candidate.id]?.final_score;
  return typeof score === "number" && !Number.isNaN(score) ? score : null;
}

async function fetchJobDetails() {
  if (!jobId.value) {
    job.value = null;
    return;
  }
  job.value = await getJob(jobId.value);
}

async function fetchCandidates() {
  if (!jobId.value) {
    candidates.value = [];
    candidatesNextCursor.value = null;
    hasMoreCandidates.value = false;
    syncedTotalCandidates.value = 0;
    return;
  }
  const result = await listJobCandidates(jobId.value, {
    limit: pageSize,
    keyword: keywordDebounced.value || undefined,
    resume_status: activeResumeStatus.value,
    segment: resolveCandidateSegment(),
  });
  candidates.value = result.candidates;
  candidatesNextCursor.value = result.next_cursor || null;
  hasMoreCandidates.value = result.has_more;
  
  syncedTotalCandidates.value = result.total || 0;
  evaluatedCount.value = result.evaluated_count || 0;
  sentDeliveryCount.value = result.sent_count || 0;

  // Sync evaluations and deliveries from embedded data to maintain local maps for filtering/UI
  evaluations.value = result.candidates
    .filter((c) => c.evaluation)
    .map((c) => c.evaluation!);
  deliveries.value = result.candidates
    .filter((c) => c.latest_delivery)
    .map((c) => c.latest_delivery!);
}

async function loadMoreCandidates() {
  if (!jobId.value || !hasMoreCandidates.value || !candidatesNextCursor.value || isLoadingMoreCandidates.value) {
    return;
  }
  isLoadingMoreCandidates.value = true;
  try {
    const result = await listJobCandidates(jobId.value, {
      limit: pageSize,
      cursor: candidatesNextCursor.value,
      keyword: keywordDebounced.value || undefined,
      resume_status: activeResumeStatus.value,
      segment: resolveCandidateSegment(),
    });
    const appendedCandidates = result.candidates;
    candidates.value = [...candidates.value, ...appendedCandidates];
    candidatesNextCursor.value = result.next_cursor || null;
    hasMoreCandidates.value = result.has_more;
    syncedTotalCandidates.value = result.total;
    sentDeliveryCount.value = result.sent_count || 0;
    evaluatedCount.value = result.evaluated_count || 0;

    // Sync evaluations and deliveries from embedded data
    const newEvals = result.candidates
      .filter((c) => c.evaluation)
      .map((c) => c.evaluation!);
    const newDeliveries = result.candidates
      .filter((c) => c.latest_delivery)
      .map((c) => c.latest_delivery!);

    evaluations.value = [...evaluations.value, ...newEvals];
    deliveries.value = [...deliveries.value, ...newDeliveries];

    // const appendedIds = appendedCandidates.map((item) => item.candidate.id);
    // await fetchEvaluations(appendedIds, true);
  } catch (error) {
    console.error("Failed to load more candidates", error);
  } finally {
    isLoadingMoreCandidates.value = false;
  }
}

async function fetchEvaluations(candidateIds?: string[], append = false) {
  if (!jobId.value || !candidateIds?.length) {
    if (!append) {
      evaluations.value = [];
    }
    return;
  }
  const result = await fetchJobEvaluations(jobId.value, {
    limit: Math.max(200, candidateIds.length),
    candidateIds,
  });
  const newEvals = result.items.map((item) => item.evaluation);
  if (!append) {
    evaluations.value = newEvals;
    return;
  }
  const merged = new Map<string, CandidateEvaluation>();
  for (const item of evaluations.value) {
    merged.set(item.candidate_id, item);
  }
  for (const item of newEvals) {
    merged.set(item.candidate_id, item);
  }
  evaluations.value = Array.from(merged.values());
}

async function fetchDeliveries() {
  if (!jobId.value) {
    deliveries.value = [];
    return;
  }
  const result = await fetchJobEmailDeliveries(jobId.value);
  deliveries.value = result.items;
}

async function refreshData() {
  if (!jobId.value) {
    return;
  }
  isLoading.value = true;
  try {
    await Promise.all([fetchJobDetails(), fetchCandidates()]);
  } catch (error) {
    console.error("Failed to refresh candidates page", error);
  } finally {
    isLoading.value = false;
  }
}

async function handleSync() {
  if (!jobId.value || isSyncing.value) {
    return;
  }
  isSyncing.value = true;
  try {
    await syncJobCandidates(jobId.value);
    await refreshData();
  } catch (error) {
    console.error("Manual sync failed", error);
  } finally {
    isSyncing.value = false;
  }
}

function canInvite(candidateId: string): boolean {
  const evaluation = evaluationByCandidateId.value[candidateId];
  if (!evaluation) {
    return false;
  }
  return Number(evaluation.final_score || 0) >= manualInviteScoreThreshold;
}

async function handleManualInvite(item: JobCandidate) {
  if (!jobId.value || sendingCandidateId.value) {
    return;
  }
  const candidateId = item.candidate.id;
  const evaluation = evaluationByCandidateId.value[candidateId];
  inviteDialogCandidate.value = item;
  inviteDialogVisible.value = true;

  if (!evaluation) {
    inviteDialogAllowSend.value = false;
    inviteDialogMessage.value = "当前候选人暂无评估结果，暂不可发送邀约。";
    return;
  }

  if (!canInvite(candidateId)) {
    inviteDialogAllowSend.value = false;
    inviteDialogMessage.value = `当前候选人评分低于 ${manualInviteScoreThreshold} 分，暂不可发送邀约。`;
    return;
  }

  inviteDialogAllowSend.value = true;
  inviteDialogMessage.value = `确认向候选人「${item.candidate.name}」发送面试邀约吗？`;
}

function closeInviteDialog() {
  if (inviteDialogSending.value) {
    return;
  }
  inviteDialogVisible.value = false;
  inviteDialogMessage.value = "";
  inviteDialogAllowSend.value = false;
  inviteDialogCandidate.value = null;
}

async function confirmInviteDialog() {
  const item = inviteDialogCandidate.value;
  if (!item || !jobId.value || sendingCandidateId.value || !inviteDialogAllowSend.value) {
    return;
  }
  const candidateId = item.candidate.id;
  const evaluation = evaluationByCandidateId.value[candidateId];
  if (!evaluation || Number(evaluation.final_score || 0) < manualInviteScoreThreshold) {
    inviteDialogAllowSend.value = false;
    inviteDialogMessage.value = `当前候选人评分低于 ${manualInviteScoreThreshold} 分，暂不可发送邀约。`;
    return;
  }

  // Non-blocking UX: close dialog first and continue sending in background.
  closeInviteDialog();
  sendingCandidateId.value = candidateId;
  try {
    await sendCandidateInvitationEmail(jobId.value, candidateId, { evaluation_id: evaluation.id });
    await fetchDeliveries();
    await fetchEvaluations(candidates.value.map((entry) => entry.candidate.id));
  } catch (error) {
    console.error("Failed to send invitation email", error);
    inviteDialogCandidate.value = item;
    inviteDialogAllowSend.value = false;
    inviteDialogMessage.value =
      error instanceof Error && error.message.trim()
        ? error.message
        : "发送邀约失败，请稍后重试。";
    inviteDialogVisible.value = true;
  } finally {
    sendingCandidateId.value = "";
  }
}

function handleViewDetails(item: JobCandidate) {
  router.push(`/admin/candidate-detail?jobId=${jobId.value}&candidateId=${item.candidate.id}`);
}

function buildEducationLine(item: JobCandidate) {
  const parts = [item.candidate.degree, item.candidate.school].filter(Boolean);
  return parts.join(" · ");
}

function buildExperienceLine(item: JobCandidate) {
  const parts = [item.candidate.latest_company, item.candidate.work_experience].filter(Boolean);
  return parts.join(" · ");
}

function getRecommendationBadge(recommendation: string) {
  switch (recommendation) {
    case "strong_recommend":
      return "bg-green-50 text-green-700";
    case "recommend":
      return "bg-primary/10 text-primary";
    case "review":
      return "bg-amber-100 text-amber-700";
    case "reject":
      return "bg-rose-100 text-rose-700";
    default:
      return "bg-surface-container-high text-on-surface-variant";
  }
}

function getRecommendationText(recommendation: string) {
  switch (recommendation) {
    case "strong_recommend":
      return "强推";
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

function getDeliveryBadge(status: string) {
  switch (status) {
    case "sent":
    case "delivered":
    case "opened":
    case "clicked":
      return "bg-green-50 text-green-700";
    case "failed":
      return "bg-rose-100 text-rose-700";
    case "sending":
      return "bg-amber-100 text-amber-700";
    default:
      return "bg-surface-container-high text-on-surface-variant";
  }
}

function getDeliveryText(status: string) {
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
      return status;
  }
}

function getResumeStatusBadge(item: JobCandidate) {
    const status = item.resume_request_status;
    const download = item.resume_download_status;
    
    if (download === 'downloaded') return 'bg-green-50 text-green-700 border-green-200 shadow-sm shadow-green-100';
    if (status === 'visible') return 'bg-amber-50 text-amber-700 border-amber-200';
    if (status === 'requested') return 'bg-primary/5 text-primary border-primary/20 animate-pulse';
    if (status === 'failed') return 'bg-rose-50 text-rose-700 border-rose-200';
    return 'bg-surface-container-high text-on-surface-variant/40 border-outline-variant/10';
}

function getResumeStatusText(item: JobCandidate) {
    const status = item.resume_request_status;
    const download = item.resume_download_status;
    
    if (download === 'downloaded') return '简历已获取';
    if (status === 'visible') return '简历可获取';
    if (status === 'requested') return '全自动申请中';
    if (status === 'failed') return '申请失败';
    return '待申请';
}

function formatScore(value?: number | null) {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "-";
  }
  return value.toFixed(1);
}

function formatDate(dateStr?: string | null) {
  if (!dateStr) {
    return "-";
  }
  return new Date(dateStr).toLocaleDateString("zh-CN");
}

function formatDateTime(dateStr?: string | null) {
  if (!dateStr) {
    return "-";
  }
  return new Date(dateStr).toLocaleString("zh-CN");
}

function getEffectiveRecommendation(candidateId: string): string {
  const evaluation = evaluationByCandidateId.value[candidateId];
  if (!evaluation) {
    return "review";
  }
  const score = Number(evaluation.final_score || 0);
  if (score >= 85) {
    return "strong_recommend";
  }
  if (score >= recommendScoreThreshold) {
    return "recommend";
  }
  return evaluation.recommendation;
}

watch(keyword, (nextValue) => {
  if (keywordDebounceTimer) {
    clearTimeout(keywordDebounceTimer);
  }
  keywordDebounceTimer = setTimeout(() => {
    keywordDebounced.value = nextValue.trim();
  }, 300);
});

watch([keywordDebounced, activeResumeStatus], async () => {
  activeTab.value = "all";
  candidatesNextCursor.value = null;
  hasMoreCandidates.value = false;
  await refreshData();
});

onMounted(() => {
  refreshData();
});

watch(
  () => route.query.jobId,
  (newId) => {
    jobId.value = (newId as string) || "";
    refreshData();
  },
);
</script>
