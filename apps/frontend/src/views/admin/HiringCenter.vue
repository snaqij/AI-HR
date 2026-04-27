<template>
  <div class="decision-page">
    <section class="decision-top-tabs">
      <div class="decision-tab-group">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          type="button"
          class="decision-tab"
          :class="{ active: activeTab === tab.key }"
          @click="activeTab = tab.key"
        >
          {{ tab.label }} {{ tab.count }}
        </button>
      </div>
      <div class="decision-actions">
        <button class="decision-ghost-btn" :disabled="isLoading" @click="loadData">
          <span class="material-symbols-outlined" :class="{ spin: isLoading }">refresh</span>
          刷新数据
        </button>
        <button class="decision-ghost-btn">
          <span class="material-symbols-outlined">ios_share</span>
          导出
        </button>
      </div>
    </section>

    <section class="decision-toolbar">
      <div class="decision-search">
        <span class="material-symbols-outlined">search</span>
        <input v-model.trim="keyword" type="text" placeholder="搜索候选人、职位、标签">
      </div>
      <select v-model="jobFilter" class="decision-select">
        <option value="all">全部职位</option>
        <option v-for="job in jobOptions" :key="job" :value="job">{{ job }}</option>
      </select>
      <select v-model="statusFilter" class="decision-select">
        <option value="all">全部状态</option>
        <option value="review">待审批</option>
        <option value="approved">已通过</option>
        <option value="rejected">已拒绝</option>
        <option value="invited">已邀约</option>
      </select>
      <select v-model="sortBy" class="decision-select">
        <option value="score_desc">综合评分排序</option>
        <option value="updated_desc">更新时间优先</option>
        <option value="resume_desc">简历评分优先</option>
        <option value="interview_desc">面试评分优先</option>
      </select>
    </section>

    <section v-if="isLoading" class="decision-loading">
      <div class="loader"></div>
      <p>正在加载录用决策数据...</p>
    </section>

    <section v-else-if="loadError" class="decision-loading">
      <p>{{ loadError }}</p>
      <button class="decision-primary-btn" @click="loadData">重试</button>
    </section>

    <section v-else class="decision-table-wrap">
      <div class="decision-table-head">
        <div>候选人</div>
        <div>职位</div>
        <div class="score-head">
          <span>评分总览</span>
          <span>简历评分</span>
          <span>面试评分</span>
        </div>
        <div>状态</div>
        <div>Offer 薪资</div>
        <div>更新时间</div>
        <div class="align-right">操作</div>
      </div>

      <div v-if="pagedRows.length === 0" class="decision-empty">
        暂无可展示的录用决策记录
      </div>

      <div v-for="item in pagedRows" :key="item.key" class="decision-row">
        <div class="candidate-cell">
          <div class="candidate-avatar">
            <img v-if="item.avatar" :src="item.avatar" :alt="item.name">
            <span v-else>{{ item.initials }}</span>
          </div>
          <div class="candidate-copy">
            <div class="candidate-title">
              <span>{{ item.name }}</span>
              <span v-if="item.flagText" class="flag-pill" :class="item.flagTone">{{ item.flagText }}</span>
            </div>
            <p>{{ item.metaLine }}</p>
            <p>{{ item.roleLine }}</p>
          </div>
        </div>

        <div class="job-cell">
          <p>{{ item.jobTitle }}</p>
          <span>{{ item.department }}</span>
        </div>

        <div class="score-cell">
          <div class="composite-ring" :style="ringStyle(item.compositeScore)">
            <span>{{ item.compositeScore.toFixed(1) }}</span>
          </div>
          <div class="score-item">
            <p class="score-num blue">{{ formatScore(item.resumeScore) }}</p>
            <div v-if="item.resumeScore != null" class="stars">
              <span
                v-for="n in 5"
                :key="`resume-${item.key}-${n}`"
                class="material-symbols-outlined"
                :class="{ active: n <= scoreToStars(item.resumeScore) }"
              >star</span>
            </div>
          </div>
          <div class="score-item">
            <p class="score-num green">{{ formatScore(item.interviewScore) }}</p>
            <div v-if="item.interviewScore != null" class="stars green">
              <span
                v-for="n in 5"
                :key="`interview-${item.key}-${n}`"
                class="material-symbols-outlined"
                :class="{ active: n <= scoreToStars(item.interviewScore) }"
              >star</span>
            </div>
          </div>
        </div>

        <div class="status-cell">
          <span class="status-pill" :class="item.statusTone">{{ item.statusText }}</span>
        </div>

        <div class="salary-cell">{{ item.salaryText }}</div>
        <div class="time-cell">{{ item.updatedAtText }}</div>

        <div class="operation-cell">
          <button class="link-btn" @click="openDecision(item.jobId, item.candidateId)">查看详情</button>
          <button class="link-btn muted" @click="openDecision(item.jobId, item.candidateId)">更多</button>
        </div>
      </div>

      <div class="decision-pagination">
        <span>共 {{ filteredRows.length }} 条</span>
        <div class="page-right">
          <select v-model.number="pageSize" class="page-size-select">
            <option :value="10">10条/页</option>
            <option :value="20">20条/页</option>
            <option :value="30">30条/页</option>
          </select>
          <button class="page-btn" :disabled="currentPage === 1" @click="currentPage -= 1">
            <span class="material-symbols-outlined">chevron_left</span>
          </button>
          <span class="current-page">{{ currentPage }}</span>
          <button class="page-btn" :disabled="currentPage >= totalPages" @click="currentPage += 1">
            <span class="material-symbols-outlined">chevron_right</span>
          </button>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import {
  fetchHiringCenterOverview,
  type HiringCenterEvaluationItem,
} from "../../api";

type HiringTab = "all" | "review" | "approved" | "rejected" | "invited";

type DecisionRow = {
  key: string;
  candidateId: string;
  jobId: string;
  name: string;
  initials: string;
  avatar: string | null;
  metaLine: string;
  roleLine: string;
  flagText: string;
  flagTone: string;
  jobTitle: string;
  department: string;
  resumeScore: number | null;
  interviewScore: number | null;
  compositeScore: number;
  statusKey: Exclude<HiringTab, "all">;
  statusText: string;
  statusTone: string;
  salaryText: string;
  updatedAt: number;
  updatedAtText: string;
};

const router = useRouter();

const isLoading = ref(false);
const loadError = ref("");
const rowsRaw = ref<HiringCenterEvaluationItem[]>([]);

const activeTab = ref<HiringTab>("all");
const keyword = ref("");
const jobFilter = ref("all");
const statusFilter = ref("all");
const sortBy = ref("score_desc");
const currentPage = ref(1);
const pageSize = ref(20);

const rows = computed<DecisionRow[]>(() => {
  return rowsRaw.value.map((item) => {
    const key = `${item.job_id}-${item.candidate_id}`;

    const recommendation = String(item.recommendation || "");
    const invited = Boolean(item.invited_flag);
    const status = resolveStatus(recommendation, invited);

    const finalScore = Number(item.final_score || 0);
    const resumeScore = typeof item.resume_score === "number" ? Number(item.resume_score) : null;
    const interviewScore = typeof item.interview_score === "number" ? Number(item.interview_score) : null;
    const compositeScore = finalScore;

    const profile = item as unknown as { candidate_raw_profile?: Record<string, unknown>; department?: string | null };
    const rawProfile = profile?.candidate_raw_profile || {};
    const city = String(rawProfile.city || "").trim() || "--";
    const years = String(rawProfile.work_years || rawProfile.years || "").trim() || "--";
    const role = String(rawProfile.role || "").trim() || "--";
    const avatar = String(item.avatar_url || rawProfile.avatar_url || rawProfile.avatar || "").trim() || null;

    return {
      key,
      candidateId: item.candidate_id,
      jobId: item.job_id,
      name: item.candidate_name || "未命名候选人",
      initials: toInitials(item.candidate_name || ""),
      avatar,
      metaLine: `${city} · ${years}`,
      roleLine: role,
      flagText: status.flagText,
      flagTone: status.flagTone,
      jobTitle: item.job_title || "--",
      department: String(profile?.department || "").trim() || "--",
      resumeScore,
      interviewScore,
      compositeScore,
      statusKey: status.key,
      statusText: status.text,
      statusTone: status.tone,
      salaryText: String(item.candidate_expected_salary || item.job_salary_range || "待沟通"),
      updatedAt: toTimestamp(item.updated_at || item.created_at),
      updatedAtText: formatDateTime(item.updated_at || item.created_at),
    };
  });
});

const tabs = computed(() => [
  { key: "all" as HiringTab, label: "全部", count: rows.value.length },
  { key: "review" as HiringTab, label: "待审批", count: rows.value.filter((r) => r.statusKey === "review").length },
  { key: "approved" as HiringTab, label: "已通过", count: rows.value.filter((r) => r.statusKey === "approved").length },
  { key: "rejected" as HiringTab, label: "已拒绝", count: rows.value.filter((r) => r.statusKey === "rejected").length },
  { key: "invited" as HiringTab, label: "已邀约", count: rows.value.filter((r) => r.statusKey === "invited").length },
]);

const jobOptions = computed(() => Array.from(new Set(rows.value.map((item) => item.jobTitle))).filter(Boolean));

const filteredRows = computed(() => {
  let list = [...rows.value];
  if (activeTab.value !== "all") {
    list = list.filter((item) => item.statusKey === activeTab.value);
  }
  if (statusFilter.value !== "all") {
    list = list.filter((item) => item.statusKey === statusFilter.value);
  }
  if (jobFilter.value !== "all") {
    list = list.filter((item) => item.jobTitle === jobFilter.value);
  }
  const q = keyword.value.trim().toLowerCase();
  if (q) {
    list = list.filter((item) => `${item.name} ${item.jobTitle} ${item.metaLine}`.toLowerCase().includes(q));
  }
  switch (sortBy.value) {
    case "updated_desc":
      list.sort((a, b) => b.updatedAt - a.updatedAt);
      break;
    case "resume_desc":
      list.sort((a, b) => (b.resumeScore ?? -1) - (a.resumeScore ?? -1));
      break;
    case "interview_desc":
      list.sort((a, b) => (b.interviewScore ?? -1) - (a.interviewScore ?? -1));
      break;
    default:
      list.sort((a, b) => b.compositeScore - a.compositeScore);
      break;
  }
  return list;
});

const totalPages = computed(() => Math.max(1, Math.ceil(filteredRows.value.length / pageSize.value)));
const pagedRows = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value;
  return filteredRows.value.slice(start, start + pageSize.value);
});

function toInitials(name: string): string {
  const raw = String(name || "").trim();
  if (!raw) return "NA";
  if (/^[\u4e00-\u9fa5]+$/.test(raw)) return raw.slice(0, 2);
  return raw.slice(0, 2).toUpperCase();
}

function scoreToStars(score: number | null | undefined): number {
  if (score == null) return 0;
  if (score >= 90) return 5;
  if (score >= 80) return 4;
  if (score >= 70) return 3;
  if (score >= 60) return 2;
  return 1;
}

function formatScore(score: number | null | undefined): string {
  if (score == null) return "--";
  return score.toFixed(1);
}

function ringStyle(score: number): Record<string, string> {
  const pct = Math.max(0, Math.min(100, score));
  return {
    background: `conic-gradient(#377dff ${pct}%, #dce9ff ${pct}% 100%)`,
  };
}

function toTimestamp(value?: string | null): number {
  const d = new Date(value || "");
  const ts = d.getTime();
  return Number.isNaN(ts) ? 0 : ts;
}

function formatDateTime(value?: string | null): string {
  if (!value) return "--";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "--";
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(d);
}

function resolveStatus(recommendation: string, invited: boolean) {
  if (invited) {
    return {
      key: "invited" as const,
      text: "已邀约",
      tone: "status-blue",
      flagText: "已邀约",
      flagTone: "flag-blue",
    };
  }
  if (recommendation === "reject") {
    return {
      key: "rejected" as const,
      text: "已拒绝",
      tone: "status-gray",
      flagText: "已拒绝",
      flagTone: "flag-gray",
    };
  }
  if (recommendation === "review" || recommendation === "manual_review") {
    return {
      key: "review" as const,
      text: "待审批",
      tone: "status-orange",
      flagText: "待审批",
      flagTone: "flag-orange",
    };
  }
  return {
    key: "approved" as const,
    text: "已通过",
    tone: "status-green",
    flagText: "优先推荐",
    flagTone: "flag-blue",
  };
}

function openDecision(jobId: string, candidateId: string) {
  router.push(`/admin/hiring/decision-detail?jobId=${jobId}&candidateId=${candidateId}`);
}

async function loadData() {
  isLoading.value = true;
  loadError.value = "";
  try {
    const overview = await fetchHiringCenterOverview({ top_n: 50, queue_limit: 120, max_scan: 1200 });
    const deduped = new Map<string, HiringCenterEvaluationItem>();
    [...(overview.top_items || []), ...(overview.queue_items || [])].forEach((item) => {
      deduped.set(`${item.job_id}-${item.candidate_id}`, item);
    });
    rowsRaw.value = Array.from(deduped.values());
  } catch (error) {
    console.error(error);
    rowsRaw.value = [];
    loadError.value = "加载录用决策数据失败，请稍后重试。";
  } finally {
    isLoading.value = false;
  }
}

watch([activeTab, keyword, statusFilter, sortBy, jobFilter, pageSize], () => {
  currentPage.value = 1;
});

watch(totalPages, (value) => {
  if (currentPage.value > value) currentPage.value = value;
});

onMounted(loadData);
</script>

<style scoped>
.decision-page {
  display: flex;
  flex-direction: column;
  gap: 14px;
  color: #1f2d3d;
}

.decision-top-tabs {
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid #e8eef6;
  padding-bottom: 10px;
}

.decision-tab-group {
  display: flex;
  align-items: center;
  gap: 30px;
}

.decision-tab {
  border: 0;
  background: transparent;
  color: #7e8da2;
  font-size: 16px;
  font-weight: 600;
  line-height: 24px;
  padding-bottom: 8px;
  border-bottom: 3px solid transparent;
  cursor: pointer;
}

.decision-tab.active {
  color: #2f74ff;
  border-bottom-color: #2f74ff;
}

.decision-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.decision-ghost-btn {
  height: 40px;
  border-radius: 10px;
  border: 1px solid #e4ebf5;
  background: #fff;
  color: #4f5f78;
  font-size: 14px;
  font-weight: 600;
  padding: 0 14px;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
}

.decision-ghost-btn .material-symbols-outlined {
  font-size: 18px;
}

.decision-ghost-btn .spin {
  animation: spin 0.9s linear infinite;
}

.decision-toolbar {
  border: 1px solid #e9eff8;
  border-radius: 14px;
  background: #fff;
  padding: 12px;
  display: grid;
  grid-template-columns: minmax(300px, 1fr) 160px 160px 190px;
  gap: 10px;
}

.decision-search {
  height: 42px;
  border: 1px solid #e4ebf5;
  border-radius: 10px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 12px;
}

.decision-search .material-symbols-outlined {
  font-size: 18px;
  color: #a3afc0;
}

.decision-search input {
  width: 100%;
  border: 0;
  outline: none;
  font-size: 14px;
  color: #273548;
  background: transparent;
}

.decision-select {
  height: 42px;
  border: 1px solid #e4ebf5;
  border-radius: 10px;
  font-size: 14px;
  color: #45556d;
  background: #fff;
  padding: 0 12px;
}

.decision-loading {
  border: 1px solid #e9eff8;
  border-radius: 14px;
  background: #fff;
  min-height: 280px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  color: #7d8ba0;
}

.loader {
  width: 34px;
  height: 34px;
  border: 3px solid #c9daf8;
  border-top-color: #2f74ff;
  border-radius: 999px;
  animation: spin 0.9s linear infinite;
}

.decision-primary-btn {
  height: 36px;
  border-radius: 9px;
  border: 0;
  background: #2f74ff;
  color: #fff;
  font-size: 14px;
  font-weight: 600;
  padding: 0 12px;
  cursor: pointer;
}

.decision-table-wrap {
  border: 1px solid #e9eff8;
  border-radius: 14px;
  background: #fff;
  overflow: hidden;
}

.decision-table-head,
.decision-row {
  display: grid;
  grid-template-columns: minmax(220px, 1.55fr) minmax(128px, 0.95fr) 280px 130px 130px 150px 120px;
  align-items: center;
  column-gap: 8px;
}

.decision-table-head {
  height: 62px;
  padding: 0 18px;
  font-size: 14px;
  color: #6e7e96;
  background: #f9fbff;
  border-bottom: 1px solid #eef3fa;
}

.score-head {
  padding-left: 4px;
  display: inline-flex;
  align-items: center;
  gap: 18px;
  font-size: 12px;
  line-height: 16px;
  color: #8a99ae;
  white-space: nowrap;
}

.job-cell {
  margin-left: -8px;
}

.decision-row {
  min-height: 104px;
  padding: 10px 16px;
  border-bottom: 1px solid #edf3fa;
}

.decision-row:last-of-type {
  border-bottom: 0;
}

.candidate-cell {
  display: flex;
  align-items: center;
  gap: 12px;
}

.candidate-avatar {
  width: 46px;
  height: 46px;
  border-radius: 999px;
  overflow: hidden;
  background: #eef3fa;
  color: #61738a;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
}

.candidate-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.candidate-copy {
  min-width: 0;
}

.candidate-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  line-height: 20px;
  color: #1d2c3f;
  font-weight: 700;
  white-space: nowrap;
}

.candidate-copy p {
  margin: 4px 0 0;
  font-size: 12px;
  color: #7e8da1;
  white-space: nowrap;
}

.flag-pill {
  padding: 3px 8px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
}

.flag-blue {
  background: #eaf2ff;
  color: #3a7eff;
}

.flag-orange {
  background: #fff3e8;
  color: #ff9a3d;
}

.flag-gray {
  background: #eff3f8;
  color: #7f8ca0;
}

.job-cell p {
  margin: 0;
  font-size: 14px;
  line-height: 20px;
  font-weight: 700;
  color: #1d2c3f;
}

.job-cell span {
  margin-top: 4px;
  display: block;
  font-size: 12px;
  color: #7e8da1;
}

.score-cell {
  display: flex;
  align-items: center;
  gap: 12px;
}

.score-item {
  min-width: 62px;
}

.score-num {
  margin: 0;
  font-size: 14px;
  line-height: 20px;
  font-weight: 700;
}

.score-num.blue {
  color: #3378ff;
}

.score-num.green {
  color: #29b16d;
}

.stars {
  margin-top: 2px;
  display: flex;
  align-items: center;
  gap: 1px;
}

.stars .material-symbols-outlined {
  font-size: 10px;
  color: #d4dfef;
  font-variation-settings: "FILL" 1;
}

.stars .material-symbols-outlined.active {
  color: #3b7fff;
}

.stars.green .material-symbols-outlined.active {
  color: #29b16d;
}

.composite-ring {
  width: 48px;
  height: 48px;
  border-radius: 999px;
  display: grid;
  place-items: center;
  position: relative;
}

.composite-ring::before {
  content: "";
  position: absolute;
  width: 40px;
  height: 40px;
  border-radius: 999px;
  background: #fff;
}

.composite-ring span {
  position: relative;
  z-index: 1;
  font-size: 12px;
  line-height: 16px;
  font-weight: 700;
  color: #3378ff;
}

.status-cell {
  display: flex;
  align-items: flex-start;
}

.status-pill {
  padding: 2px 10px;
  border-radius: 999px;
  font-size: 12px;
  line-height: 18px;
  font-weight: 700;
}

.status-green {
  background: #e6f7ef;
  color: #2eb06f;
}

.status-orange {
  background: #fff3e7;
  color: #ff9a3d;
}

.status-gray {
  background: #eef2f8;
  color: #8a97ac;
}

.status-blue {
  background: #eaf2ff;
  color: #3a7eff;
}

.salary-cell,
.time-cell {
  font-size: 12px;
  line-height: 18px;
  color: #637791;
}

.operation-cell {
  display: flex;
  flex-direction: row;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
}

.link-btn {
  border: 0;
  background: transparent;
  color: #2f74ff;
  font-size: 12px;
  line-height: 18px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
}

.link-btn.muted {
  color: #6794ff;
}

.align-right {
  text-align: right;
}

.decision-empty {
  height: 220px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #8a97ac;
  font-size: 14px;
}

.decision-pagination {
  height: 58px;
  border-top: 1px solid #edf3fa;
  padding: 0 18px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  color: #7f8da1;
  font-size: 14px;
}

.page-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.page-size-select {
  height: 34px;
  border: 1px solid #e4ebf5;
  border-radius: 8px;
  padding: 0 10px;
  color: #66768e;
  background: #fff;
}

.page-btn {
  width: 34px;
  height: 34px;
  border: 1px solid #e4ebf5;
  border-radius: 8px;
  background: #fff;
  color: #62758f;
  display: grid;
  place-items: center;
  cursor: pointer;
}

.page-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.current-page {
  min-width: 24px;
  text-align: center;
  color: #2f74ff;
  font-weight: 700;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

@media (max-width: 1600px) {
  .decision-table-head,
  .decision-row {
    grid-template-columns: minmax(180px, 1.28fr) minmax(112px, 0.92fr) 240px 110px 110px 130px 100px;
  }
}
</style>
