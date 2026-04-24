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

      <button class="admin-quiet-btn" :disabled="isLoading" @click="loadData">
        <span class="material-symbols-outlined text-[16px]" :class="{ 'animate-spin': isLoading }">refresh</span>
        刷新数据
      </button>
    </section>

    <section class="admin-toolbar px-5 py-4">
      <div class="flex flex-col gap-4 xl:flex-row xl:items-center">
        <div class="relative min-w-0 flex-1">
          <span class="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-[16px] text-[#a9b4c4]">search</span>
          <input
            v-model.trim="keyword"
            type="text"
            placeholder="搜索候选人、职位、薪资"
            class="admin-input admin-search-input"
          >
        </div>

        <div class="grid grid-cols-1 gap-3 md:grid-cols-3 xl:min-w-[520px]">
          <div class="relative">
            <select v-model="recommendationFilter" class="admin-select appearance-none pr-9">
              <option value="all">全部审批状态</option>
              <option value="strong_recommend">强烈推荐</option>
              <option value="recommend">推荐</option>
              <option value="review">待复核</option>
              <option value="reject">不推荐</option>
            </select>
            <span class="material-symbols-outlined pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-[16px] text-[#a9b4c4]">expand_more</span>
          </div>

          <div class="relative">
            <select v-model="sortBy" class="admin-select appearance-none pr-9">
              <option value="updated_desc">最近更新优先</option>
              <option value="updated_asc">最早更新优先</option>
              <option value="score_desc">评分从高到低</option>
              <option value="score_asc">评分从低到高</option>
            </select>
            <span class="material-symbols-outlined pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-[16px] text-[#a9b4c4]">expand_more</span>
          </div>

          <button class="admin-quiet-btn w-full justify-between" @click="resetFilters">
            <span class="flex items-center gap-2">
              <span class="material-symbols-outlined text-[16px]">filter_alt</span>
              更多筛选
            </span>
            <span class="material-symbols-outlined text-[16px]">restart_alt</span>
          </button>
        </div>
      </div>
    </section>

    <section v-if="isLoading" class="admin-panel px-6 py-12 text-center">
      <div class="mx-auto mb-3 h-10 w-10 animate-spin rounded-full border-4 border-primary/20 border-t-primary"></div>
      <p class="text-sm font-medium text-on-surface-variant">正在加载录用决策数据...</p>
    </section>

    <section v-else-if="loadError" class="admin-panel px-6 py-8">
      <p class="text-sm font-semibold text-on-error-container">{{ loadError }}</p>
      <button class="admin-primary-btn mt-4" @click="loadData">重试</button>
    </section>

    <section v-else class="admin-table-shell">
      <div class="grid grid-cols-[minmax(220px,1.5fr)_minmax(220px,1.6fr)_150px_130px_130px_120px] gap-4 px-6 py-4 admin-table-head">
        <div class="admin-table-label">候选人</div>
        <div class="admin-table-label">职位</div>
        <div class="admin-table-label">Offer 薪资</div>
        <div class="admin-table-label">审批状态</div>
        <div class="admin-table-label text-center">更新时间</div>
        <div class="admin-table-label text-right">操作</div>
      </div>

      <div v-if="filteredRows.length === 0" class="admin-empty">
        <div class="flex h-16 w-16 items-center justify-center rounded-full bg-surface-container-low text-on-surface-variant">
          <span class="material-symbols-outlined text-[28px]">task_alt</span>
        </div>
        <p class="mt-4 text-sm font-semibold text-on-surface">暂无待处理决策</p>
        <p class="mt-1 text-sm text-on-surface-variant">当前筛选条件下没有可展示的录用决策记录。</p>
      </div>

      <div v-else>
        <div
          v-for="item in pagedRows"
          :key="item.key"
          class="admin-table-row grid grid-cols-[minmax(220px,1.5fr)_minmax(220px,1.6fr)_150px_130px_130px_120px] gap-4 border-b border-[#f0f4fa] px-6 py-5 last:border-b-0"
        >
          <div class="flex items-center gap-3 min-w-0">
            <div class="flex h-10 w-10 items-center justify-center rounded-full bg-[#edf3fb] text-[12px] font-semibold text-[#62708c]">
              {{ item.initials }}
            </div>
            <div class="min-w-0">
              <p class="truncate text-[14px] font-semibold text-on-surface">{{ item.name }}</p>
              <p class="truncate text-[12px] text-on-surface-variant">{{ item.summary }}</p>
            </div>
          </div>

          <div class="min-w-0">
            <p class="truncate text-[14px] font-semibold text-on-surface">{{ item.job }}</p>
            <p class="mt-1 truncate text-[12px] text-on-surface-variant">{{ item.jobMeta }}</p>
          </div>

          <div class="flex items-center text-[13px] text-on-surface-variant">
            {{ item.salary }}
          </div>

          <div class="flex items-center">
            <span class="admin-badge" :class="item.statusClass">{{ item.statusLabel }}</span>
          </div>

          <div class="flex items-center justify-center text-[13px] text-on-surface-variant">
            {{ item.updatedAtText }}
          </div>

          <div class="flex items-center justify-end">
            <button class="admin-link-btn" @click="openCandidate(item.jobId, item.candidateId)">
              立即处理
            </button>
          </div>
        </div>
      </div>

      <div class="flex items-center justify-between border-t border-[#eef2f7] px-6 py-4">
        <p class="text-[12px] text-on-surface-variant">共 {{ filteredRows.length }} 条</p>
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
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import {
  fetchHiringCenterOverview,
  type HiringCenterEvaluationItem,
  type HiringCenterOverviewResult,
} from "../../api";

type HiringTab = "all" | "review" | "approved" | "rejected" | "invited";

type DecisionRow = {
  key: string;
  candidateId: string;
  jobId: string;
  initials: string;
  name: string;
  summary: string;
  job: string;
  jobMeta: string;
  salary: string;
  recommendation: string;
  invited: boolean;
  score: number;
  statusLabel: string;
  statusClass: string;
  updatedAt: number;
  updatedAtText: string;
};

const router = useRouter();

const overview = ref<HiringCenterOverviewResult | null>(null);
const isLoading = ref(false);
const loadError = ref("");

const activeTab = ref<HiringTab>("all");
const keyword = ref("");
const recommendationFilter = ref("all");
const sortBy = ref("updated_desc");
const currentPage = ref(1);

const pageSize = 8;

const rows = computed<DecisionRow[]>(() => {
  const deduped = new Map<string, HiringCenterEvaluationItem>();
  [...(overview.value?.top_items || []), ...(overview.value?.queue_items || [])].forEach((item) => {
    deduped.set(`${item.job_id}-${item.candidate_id}`, item);
  });

  return Array.from(deduped.values()).map((item) => {
    const recommendation = String(item.recommendation || "");
    const status = statusMeta(recommendation, Boolean(item.invited_flag));
    const updatedAt = item.updated_at || item.created_at;
    const score = Number(item.final_score || 0);

    return {
      key: `${item.job_id}-${item.candidate_id}`,
      candidateId: item.candidate_id,
      jobId: item.job_id,
      initials: toInitials(item.candidate_name),
      name: item.candidate_name,
      summary: item.summary || item.candidate_score_explanation || `AI 评分 ${score.toFixed(1)}`,
      job: item.job_title,
      jobMeta: `AI 评分 ${score.toFixed(1)}`,
      salary: formatSalary(item.candidate_expected_salary || item.job_salary_range),
      recommendation,
      invited: Boolean(item.invited_flag),
      score,
      statusLabel: status.label,
      statusClass: status.className,
      updatedAt: toTimestamp(updatedAt),
      updatedAtText: formatDate(updatedAt),
    };
  });
});

const tabs = computed(() => [
  { key: "all" as HiringTab, label: "全部", count: rows.value.length },
  { key: "review" as HiringTab, label: "待审批", count: rows.value.filter((item) => tabKey(item) === "review").length },
  { key: "approved" as HiringTab, label: "已通过", count: rows.value.filter((item) => tabKey(item) === "approved").length },
  { key: "rejected" as HiringTab, label: "已拒绝", count: rows.value.filter((item) => tabKey(item) === "rejected").length },
  { key: "invited" as HiringTab, label: "已邀约", count: rows.value.filter((item) => tabKey(item) === "invited").length },
]);

const filteredRows = computed(() => {
  let list = [...rows.value];

  if (activeTab.value !== "all") {
    list = list.filter((item) => tabKey(item) === activeTab.value);
  }

  if (recommendationFilter.value !== "all") {
    list = list.filter((item) => item.recommendation === recommendationFilter.value);
  }

  const query = keyword.value.trim().toLowerCase();
  if (query) {
    list = list.filter((item) => `${item.name} ${item.job} ${item.salary}`.toLowerCase().includes(query));
  }

  switch (sortBy.value) {
    case "updated_asc":
      list.sort((a, b) => a.updatedAt - b.updatedAt);
      break;
    case "score_desc":
      list.sort((a, b) => b.score - a.score);
      break;
    case "score_asc":
      list.sort((a, b) => a.score - b.score);
      break;
    default:
      list.sort((a, b) => b.updatedAt - a.updatedAt);
      break;
  }

  return list;
});

const totalPages = computed(() => Math.max(1, Math.ceil(filteredRows.value.length / pageSize)));

const pagedRows = computed(() => {
  const start = (currentPage.value - 1) * pageSize;
  return filteredRows.value.slice(start, start + pageSize);
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

function tabKey(item: DecisionRow): Exclude<HiringTab, "all"> {
  if (item.invited) return "invited";
  if (item.recommendation === "reject") return "rejected";
  if (item.recommendation === "review") return "review";
  return "approved";
}

function statusMeta(recommendation: string, invited: boolean): { label: string; className: string } {
  if (invited) return { label: "已邀约", className: "admin-badge-blue" };
  if (recommendation === "strong_recommend") return { label: "强烈推荐", className: "admin-badge-green" };
  if (recommendation === "recommend") return { label: "已通过", className: "admin-badge-green" };
  if (recommendation === "reject") return { label: "已拒绝", className: "bg-[#f3f6fb] text-[#7c889a]" };
  return { label: "待审批", className: "admin-badge-orange" };
}

function toInitials(name: string): string {
  const raw = (name || "").trim();
  if (!raw) return "NA";
  if (/^[\u4e00-\u9fa5]+$/.test(raw)) return raw.slice(0, 2);
  const parts = raw.split(/\s+/).filter(Boolean);
  if (!parts.length) return raw.slice(0, 2).toUpperCase();
  return parts.slice(0, 2).map((item) => item.slice(0, 1).toUpperCase()).join("");
}

function formatSalary(value?: string | null): string {
  const text = String(value || "").trim();
  return text || "待沟通";
}

function toTimestamp(value?: string | null): number {
  const d = new Date(value || "");
  const ts = d.getTime();
  return Number.isNaN(ts) ? 0 : ts;
}

function formatDate(value?: string | null): string {
  if (!value) return "--";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "--";
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(d);
}

function resetFilters() {
  keyword.value = "";
  recommendationFilter.value = "all";
  sortBy.value = "updated_desc";
}

function openCandidate(jobId: string, candidateId: string) {
  router.push(`/admin/candidate-detail?jobId=${jobId}&candidateId=${candidateId}`);
}

async function loadData() {
  isLoading.value = true;
  loadError.value = "";
  try {
    overview.value = await fetchHiringCenterOverview({ top_n: 12, queue_limit: 80, max_scan: 3000 });
  } catch (error) {
    console.error("Failed to load hiring center data", error);
    loadError.value = "加载录用决策数据失败，请稍后重试。";
    overview.value = null;
  } finally {
    isLoading.value = false;
  }
}

watch([keyword, recommendationFilter, sortBy, activeTab], () => {
  currentPage.value = 1;
});

watch(totalPages, (value) => {
  if (currentPage.value > value) currentPage.value = value;
});

onMounted(loadData);
</script>
