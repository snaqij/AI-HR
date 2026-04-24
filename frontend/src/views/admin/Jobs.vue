<template>
  <div class="admin-page">
    <section class="flex flex-wrap items-center justify-between gap-4">
      <div class="flex flex-wrap items-center gap-6 border-b border-[#eef2f7]">
        <button
          v-for="tab in statusTabs"
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

      <div class="flex items-center gap-3">
        <button
          v-if="hasSelection"
          class="admin-quiet-btn text-red-600 hover:bg-red-50"
          @click="openDeleteConfirm"
        >
          <span class="material-symbols-outlined text-[18px]">delete</span>
          删除选中 ({{ selectedJobIds.size }})
        </button>
        <button class="admin-quiet-btn" :disabled="isGlobalSyncing" @click="handleGlobalSync">
          <span class="material-symbols-outlined text-[18px]" :class="{ 'animate-spin': isGlobalSyncing }">sync</span>
          {{ isGlobalSyncing ? "同步中..." : "同步职位" }}
        </button>
        <button class="admin-primary-btn">
          <span class="material-symbols-outlined text-[18px]">add</span>
          新建职位
        </button>
      </div>
    </section>

    <section class="admin-toolbar px-5 py-4">
      <div class="flex flex-col gap-4 xl:flex-row xl:items-center">
        <div class="relative min-w-0 flex-1">
          <span class="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-[17px] text-[#a4afc0]">search</span>
          <input
            v-model.trim="keyword"
            type="text"
            placeholder="搜索职位名称、部门、工作地点"
            class="admin-input admin-search-input"
          >
        </div>

        <div class="grid grid-cols-1 gap-3 md:grid-cols-3 xl:min-w-[520px]">
          <div class="relative">
            <select v-model="departmentFilter" class="admin-select appearance-none pr-9">
              <option value="">全部部门</option>
              <option v-for="department in departmentOptions" :key="department" :value="department">
                {{ department }}
              </option>
            </select>
            <span class="material-symbols-outlined pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-[18px] text-[#a4afc0]">expand_more</span>
          </div>

          <div class="relative">
            <select v-model="statusFilter" class="admin-select appearance-none pr-9">
              <option value="">全部状态</option>
              <option value="active">招聘中</option>
              <option value="paused">暂停中</option>
              <option value="closed">已关闭</option>
            </select>
            <span class="material-symbols-outlined pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-[18px] text-[#a4afc0]">expand_more</span>
          </div>

          <button class="admin-quiet-btn w-full justify-between" @click="resetFilters">
            <span class="flex items-center gap-2">
              <span class="material-symbols-outlined text-[17px]">filter_alt</span>
              重置筛选
            </span>
            <span class="material-symbols-outlined text-[16px]">refresh</span>
          </button>
        </div>
      </div>
    </section>

    <section class="admin-table-shell">
      <div class="grid grid-cols-[48px_minmax(280px,2.4fr)_140px_1fr_120px_120px_100px_140px_132px] gap-4 px-8 py-4 admin-table-head">
        <div class="flex items-center justify-center">
          <input
            type="checkbox"
            :checked="isAllSelected"
            :indeterminate="hasSelection && !isAllSelected"
            class="h-4 w-4 cursor-pointer rounded border-gray-300 text-primary focus:ring-2 focus:ring-primary"
            @change="toggleSelectAll"
          >
        </div>
        <div class="admin-table-label">职位名称</div>
        <div class="admin-table-label">职位编号</div>
        <div class="admin-table-label">部门</div>
        <div class="admin-table-label">工作地点</div>
        <div class="admin-table-label">招聘状态</div>
        <div class="admin-table-label text-center">候选人</div>
        <div class="admin-table-label">更新时间</div>
        <div class="admin-table-label text-right">操作</div>
      </div>

      <div v-if="isLoading" class="admin-empty">
        <div class="h-10 w-10 animate-spin rounded-full border-4 border-primary/20 border-t-primary"></div>
        <p class="mt-4 text-sm text-on-surface-variant">正在加载职位数据...</p>
      </div>

      <div v-else-if="pagedJobs.length === 0" class="admin-empty">
        <div class="flex h-16 w-16 items-center justify-center rounded-full bg-surface-container-low text-on-surface-variant">
          <span class="material-symbols-outlined text-[28px]">work_outline</span>
        </div>
        <p class="mt-4 text-sm font-semibold text-on-surface">暂无职位数据</p>
        <p class="mt-1 text-sm text-on-surface-variant">当前筛选条件下没有可展示的职位。</p>
      </div>

      <div v-else>
        <div
          v-for="job in pagedJobs"
          :key="job.id"
          class="admin-table-row grid cursor-pointer grid-cols-[48px_minmax(280px,2.4fr)_140px_1fr_120px_120px_100px_140px_132px] gap-4 border-b border-[#f0f4fa] px-8 py-5 last:border-b-0"
          @click="openJobCandidates(job.id)"
        >
          <div class="flex items-center justify-center" @click.stop>
            <input
              type="checkbox"
              :checked="selectedJobIds.has(job.id)"
              class="h-4 w-4 cursor-pointer rounded border-gray-300 text-primary focus:ring-2 focus:ring-primary"
              @change="toggleSelectJob(job.id)"
            >
          </div>
          <div class="min-w-0">
            <p class="truncate text-[18px] font-bold tracking-tight text-on-surface">{{ job.title }}</p>
            <p class="mt-1 truncate text-[13px] text-on-surface-variant">
              {{ [job.department || "默认部门", job.city || "未设置", job.salary_range || "薪资面议"].join(" · ") }}
            </p>
            <div class="mt-3 flex flex-wrap items-center gap-2">
              <span
                v-if="job.auto_request_resume"
                class="inline-flex items-center rounded-full bg-[#ecf8f1] px-3 py-1 text-[12px] font-semibold text-[#1f9d62]"
              >
                自动请求已开启
              </span>
              <span
                v-if="hasConfig(job)"
                class="inline-flex items-center rounded-full bg-[#f3f6fb] px-3 py-1 text-[12px] font-medium text-[#71819a]"
              >
                {{ configSummary(job) }}
              </span>
            </div>
          </div>

          <div class="flex items-center text-[13px] font-medium text-on-surface-variant">
            {{ jobCode(job) }}
          </div>

          <div class="flex items-center text-[13px] text-on-surface-variant">
            {{ job.department || "未分配" }}
          </div>

          <div class="flex items-center text-[13px] text-on-surface-variant">
            {{ job.city || "-" }}
          </div>

          <div class="flex items-center">
            <span class="admin-badge" :class="statusBadgeClass(job)">{{ statusText(job) }}</span>
          </div>

          <div class="flex items-center justify-center">
            <span class="admin-badge admin-badge-blue min-w-[42px]">{{ job.candidate_count || 0 }}</span>
          </div>

          <div class="flex items-center text-[13px] text-on-surface-variant">
            {{ formatDate(job.published_at || job.created_at) }}
          </div>

          <div class="flex items-center justify-end gap-4">
            <button type="button" class="admin-link-btn" @click.stop="openConfig(job.id)">配置</button>
            <button type="button" class="admin-link-btn" @click.stop="openJobCandidates(job.id)">详情</button>
          </div>
        </div>
      </div>

      <div class="flex items-center justify-between border-t border-[#eef2f7] px-6 py-4">
        <p class="text-[13px] text-on-surface-variant">共 {{ filteredJobs.length }} 条</p>
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
      v-if="configDialogOpen"
      class="fixed inset-0 z-40 bg-[rgba(15,23,42,0.18)] backdrop-blur-[2px]"
      @click="closeConfig"
    ></div>

    <div
      v-if="configDialogOpen && activeConfigJob"
      class="fixed left-1/2 top-1/2 z-50 w-[min(640px,calc(100vw-32px))] -translate-x-1/2 -translate-y-1/2 rounded-[20px] border border-[#e8eef8] bg-white p-6 shadow-[0_24px_80px_rgba(15,23,42,0.16)]"
      @click.stop
    >
      <div class="flex items-start justify-between gap-4">
        <div>
          <p class="text-[12px] font-semibold uppercase tracking-[0.16em] text-primary">配置</p>
          <h3 class="mt-2 text-[24px] font-bold tracking-tight text-on-surface">{{ activeConfigJob.title }}</h3>
          <p class="mt-2 text-[13px] text-on-surface-variant">设置岗位筛选条件和自动请求简历策略</p>
        </div>
        <button
          type="button"
          class="flex h-9 w-9 items-center justify-center rounded-full text-[#7b8798] transition-colors hover:bg-[#f5f8fd] hover:text-primary"
          @click="closeConfig"
        >
          <span class="material-symbols-outlined text-[18px]">close</span>
        </button>
      </div>

      <div class="mt-6 grid grid-cols-1 gap-4 md:grid-cols-2">
        <div>
          <label class="admin-label">最低学历</label>
          <select v-model="activeDraft.min_degree" class="admin-select mt-2">
            <option value="">不限</option>
            <option v-for="option in degreeOptions" :key="option" :value="option">{{ option }}</option>
          </select>
        </div>

        <div>
          <label class="admin-label">最低工作经验</label>
          <input
            v-model="activeDraft.min_experience_years"
            type="number"
            min="0"
            class="admin-input mt-2"
            placeholder="例如 3"
          >
        </div>

        <div>
          <label class="admin-label">每日请求获取点数</label>
          <input
            v-model="activeDraft.max_daily_resume_requests"
            type="number"
            min="0"
            class="admin-input mt-2"
            placeholder="例如 10"
          >
        </div>

        <div>
          <label class="admin-label">自动获取简历</label>
          <button
            type="button"
            class="mt-2 flex h-[44px] w-full items-center justify-between rounded-[12px] border border-[#e7edf7] bg-white px-4 text-[13px] font-medium transition-colors"
            :class="activeDraft.auto_request_resume ? 'border-[#cfe0ff] text-primary' : 'text-on-surface-variant'"
            @click="toggleAutoRequest(activeConfigJob.id)"
          >
            <span>{{ activeDraft.auto_request_resume ? "已开启" : "已关闭" }}</span>
            <span
              class="relative h-5 w-9 rounded-full transition-colors"
              :class="activeDraft.auto_request_resume ? 'bg-primary' : 'bg-[#d9e1ee]'"
            >
              <span
                class="absolute top-[2px] h-4 w-4 rounded-full bg-white transition-transform"
                :class="activeDraft.auto_request_resume ? 'translate-x-4' : 'translate-x-0.5'"
              ></span>
            </span>
          </button>
        </div>
      </div>

      <div class="mt-6 flex flex-wrap items-center justify-between gap-3 rounded-[14px] bg-[#f7faff] px-4 py-4">
        <div>
          <p class="text-[13px] font-semibold text-on-surface">岗位筛选条件</p>
          <p class="mt-1 text-[12px] text-on-surface-variant">保存后会应用到自动请求简历流程</p>
        </div>
        <div class="flex items-center gap-3">
          <span
            v-if="activeDraft.auto_request_resume"
            class="inline-flex items-center rounded-full bg-[#ecf8f1] px-3 py-1 text-[12px] font-semibold text-[#1f9d62]"
          >
            自动请求已开启
          </span>
          <button type="button" class="admin-quiet-btn" @click="closeConfig">取消</button>
          <button
            type="button"
            class="admin-primary-btn whitespace-nowrap"
            :disabled="savingJobId === activeConfigJob.id"
            @click="handleSaveJobSettings(activeConfigJob.id)"
          >
            <span
              v-if="savingJobId === activeConfigJob.id"
              class="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white"
            ></span>
            {{ savingJobId === activeConfigJob.id ? "保存中..." : "保存配置" }}
          </button>
        </div>
      </div>
    </div>

    <!-- Delete confirmation dialog -->
    <div
      v-if="showDeleteConfirm"
      class="fixed inset-0 z-40 bg-[rgba(15,23,42,0.18)] backdrop-blur-[2px]"
      @click="closeDeleteConfirm"
    ></div>

    <div
      v-if="showDeleteConfirm"
      class="fixed left-1/2 top-1/2 z-50 w-[min(480px,calc(100vw-32px))] -translate-x-1/2 -translate-y-1/2 rounded-[20px] border border-[#e8eef8] bg-white p-6 shadow-[0_24px_80px_rgba(15,23,42,0.16)]"
      @click.stop
    >
      <div class="flex items-start gap-4">
        <div class="flex h-12 w-12 items-center justify-center rounded-full bg-red-50">
          <span class="material-symbols-outlined text-[24px] text-red-600">warning</span>
        </div>
        <div class="flex-1">
          <h3 class="text-[20px] font-bold tracking-tight text-on-surface">确认删除职位</h3>
          <p class="mt-2 text-[14px] text-on-surface-variant">
            您即将删除 <span class="font-semibold text-red-600">{{ selectedJobIds.size }}</span> 个职位，此操作不可撤销。
          </p>
          <p class="mt-1 text-[13px] text-on-surface-variant">
            删除职位将同时删除相关的候选人数据和面试记录。
          </p>
        </div>
      </div>

      <div class="mt-6 flex items-center justify-end gap-3">
        <button type="button" class="admin-quiet-btn" :disabled="isDeleting" @click="closeDeleteConfirm">
          取消
        </button>
        <button
          type="button"
          class="admin-primary-btn bg-red-600 hover:bg-red-700"
          :disabled="isDeleting"
          @click="handleBatchDelete"
        >
          <span
            v-if="isDeleting"
            class="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white"
          ></span>
          {{ isDeleting ? "删除中..." : "确认删除" }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { batchDeleteJobs, importRemoteJobs, listJobs, updateJobSettings, type Job } from "../../api";

type JobTab = "all" | "active" | "paused" | "closed";
type JobSettingDraft = {
  min_degree: string;
  min_experience_years: string;
  max_daily_resume_requests: string;
  auto_request_resume: boolean;
};

const router = useRouter();

const jobs = ref<Job[]>([]);
const isLoading = ref(true);
const isGlobalSyncing = ref(false);
const savingJobId = ref("");
const keyword = ref("");
const departmentFilter = ref("");
const statusFilter = ref("");
const activeTab = ref<JobTab>("all");
const currentPage = ref(1);
const settingDrafts = ref<Record<string, JobSettingDraft>>({});
const configDialogOpen = ref(false);
const activeConfigJobId = ref("");
const selectedJobIds = ref<Set<string>>(new Set());
const isDeleting = ref(false);
const showDeleteConfirm = ref(false);

const pageSize = 6;
const degreeOptions = ["博士", "硕士", "本科", "大专", "中专", "高中"];

const departmentOptions = computed(() => Array.from(new Set(jobs.value.map((job) => job.department).filter(Boolean) as string[])).sort());
const activeJobsCount = computed(() => jobs.value.filter((job) => normalizedStatus(job) === "active").length);
const pausedJobsCount = computed(() => jobs.value.filter((job) => normalizedStatus(job) === "paused").length);
const closedJobsCount = computed(() => jobs.value.filter((job) => normalizedStatus(job) === "closed").length);

const statusTabs = computed(() => [
  { key: "all" as JobTab, label: "全部职位", count: jobs.value.length },
  { key: "active" as JobTab, label: "招聘中", count: activeJobsCount.value },
  { key: "paused" as JobTab, label: "暂停中", count: pausedJobsCount.value },
  { key: "closed" as JobTab, label: "已关闭", count: closedJobsCount.value },
]);

const filteredJobs = computed(() => {
  return jobs.value.filter((job) => {
    const status = normalizedStatus(job);
    const query = keyword.value.trim().toLowerCase();

    if (activeTab.value !== "all" && status !== activeTab.value) return false;
    if (statusFilter.value && status !== statusFilter.value) return false;
    if (departmentFilter.value && (job.department || "") !== departmentFilter.value) return false;
    if (query && ![job.title, job.department || "", job.city || "", job.id].join(" ").toLowerCase().includes(query)) return false;

    return true;
  });
});

const totalPages = computed(() => Math.max(1, Math.ceil(filteredJobs.value.length / pageSize)));
const pagedJobs = computed(() => filteredJobs.value.slice((currentPage.value - 1) * pageSize, currentPage.value * pageSize));
const visiblePages = computed(() => {
  const pages: number[] = [];
  const start = Math.max(1, currentPage.value - 1);
  const end = Math.min(totalPages.value, start + 2);
  for (let page = start; page <= end; page += 1) pages.push(page);
  if (!pages.includes(1)) pages.unshift(1);
  if (!pages.includes(totalPages.value)) pages.push(totalPages.value);
  return Array.from(new Set(pages));
});

const activeConfigJob = computed(() => jobs.value.find((job) => job.id === activeConfigJobId.value) || null);
const activeDraft = computed(() => {
  if (!activeConfigJobId.value) {
    return { min_degree: "", min_experience_years: "", max_daily_resume_requests: "", auto_request_resume: false };
  }
  return settingDrafts.value[activeConfigJobId.value];
});

const isAllSelected = computed(() => {
  return pagedJobs.value.length > 0 && pagedJobs.value.every((job) => selectedJobIds.value.has(job.id));
});

const hasSelection = computed(() => selectedJobIds.value.size > 0);

function normalizedStatus(job: Job): JobTab {
  const value = String(job.status || "").toLowerCase();
  if (value.includes("pause")) return "paused";
  if (value.includes("draft") || value.includes("close")) return "closed";
  return "active";
}

function statusText(job: Job): string {
  const value = normalizedStatus(job);
  if (value === "paused") return "暂停中";
  if (value === "closed") return "已关闭";
  return "招聘中";
}

function statusBadgeClass(job: Job): string {
  const value = normalizedStatus(job);
  if (value === "paused") return "admin-badge-orange";
  if (value === "closed") return "bg-[#f3f6fb] text-[#7d8799]";
  return "admin-badge-green";
}

function jobCode(job: Job): string {
  return `JOB-${job.id.replace(/[^a-zA-Z0-9]/g, "").slice(0, 6).toUpperCase()}`;
}

function formatDate(value?: string | null): string {
  if (!value) return "-";
  return new Intl.DateTimeFormat("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(value));
}

function hasConfig(job: Job): boolean {
  return Boolean(job.min_degree || job.min_experience_years != null || job.max_daily_resume_requests != null);
}

function configSummary(job: Job): string {
  const parts = [
    job.min_degree ? `学历 ${job.min_degree}` : "",
    job.min_experience_years != null ? `经验 ${job.min_experience_years} 年` : "",
    job.max_daily_resume_requests != null ? `点数 ${job.max_daily_resume_requests}` : "",
  ].filter(Boolean);
  return parts.join(" · ");
}

function resetFilters(): void {
  keyword.value = "";
  departmentFilter.value = "";
  statusFilter.value = "";
  activeTab.value = "all";
}

function syncSettingDrafts(): void {
  const next: Record<string, JobSettingDraft> = {};
  for (const job of jobs.value) {
    next[job.id] = {
      min_degree: job.min_degree || "",
      min_experience_years: job.min_experience_years == null ? "" : String(job.min_experience_years),
      max_daily_resume_requests: job.max_daily_resume_requests == null ? "" : String(job.max_daily_resume_requests),
      auto_request_resume: Boolean(job.auto_request_resume),
    };
  }
  settingDrafts.value = next;
}

async function fetchJobs(): Promise<void> {
  isLoading.value = true;
  try {
    jobs.value = await listJobs();
    syncSettingDrafts();
  } catch (error) {
    console.error("Failed to fetch jobs", error);
    jobs.value = [];
    settingDrafts.value = {};
  } finally {
    isLoading.value = false;
  }
}

async function handleGlobalSync(): Promise<void> {
  if (isGlobalSyncing.value) return;
  isGlobalSyncing.value = true;
  try {
    await importRemoteJobs("boss");
    await fetchJobs();
  } catch (error) {
    console.error("Failed to sync jobs", error);
  } finally {
    isGlobalSyncing.value = false;
  }
}

function openConfig(jobId: string): void {
  activeConfigJobId.value = jobId;
  if (!settingDrafts.value[jobId]) {
    syncSettingDrafts();
  }
  configDialogOpen.value = true;
}

function closeConfig(): void {
  configDialogOpen.value = false;
  activeConfigJobId.value = "";
}

async function handleSaveJobSettings(jobId: string): Promise<void> {
  const draft = settingDrafts.value[jobId];
  if (!draft || savingJobId.value) return;

  savingJobId.value = jobId;
  try {
    const updated = await updateJobSettings(jobId, {
      auto_request_resume: draft.auto_request_resume,
      min_degree: draft.min_degree || null,
      min_experience_years: draft.min_experience_years === "" ? null : Number(draft.min_experience_years),
      max_daily_resume_requests: draft.max_daily_resume_requests === "" ? null : Number(draft.max_daily_resume_requests),
    });
    jobs.value = jobs.value.map((job) => (job.id === jobId ? updated : job));
    settingDrafts.value[jobId] = {
      min_degree: updated.min_degree || "",
      min_experience_years: updated.min_experience_years == null ? "" : String(updated.min_experience_years),
      max_daily_resume_requests: updated.max_daily_resume_requests == null ? "" : String(updated.max_daily_resume_requests),
      auto_request_resume: Boolean(updated.auto_request_resume),
    };
    closeConfig();
  } catch (error) {
    console.error("Failed to save job settings", error);
  } finally {
    savingJobId.value = "";
  }
}

function toggleAutoRequest(jobId: string): void {
  settingDrafts.value[jobId].auto_request_resume = !settingDrafts.value[jobId].auto_request_resume;
}

function openJobCandidates(jobId: string): void {
  router.push(`/admin/candidates?jobId=${jobId}`);
}

function toggleSelectAll(): void {
  if (isAllSelected.value) {
    pagedJobs.value.forEach((job) => selectedJobIds.value.delete(job.id));
  } else {
    pagedJobs.value.forEach((job) => selectedJobIds.value.add(job.id));
  }
}

function toggleSelectJob(jobId: string): void {
  if (selectedJobIds.value.has(jobId)) {
    selectedJobIds.value.delete(jobId);
  } else {
    selectedJobIds.value.add(jobId);
  }
}

function openDeleteConfirm(): void {
  if (selectedJobIds.value.size === 0) return;
  showDeleteConfirm.value = true;
}

function closeDeleteConfirm(): void {
  showDeleteConfirm.value = false;
}

async function handleBatchDelete(): Promise<void> {
  if (isDeleting.value || selectedJobIds.value.size === 0) return;

  isDeleting.value = true;
  try {
    const jobIds = Array.from(selectedJobIds.value);
    await batchDeleteJobs(jobIds);
    selectedJobIds.value.clear();
    showDeleteConfirm.value = false;
    await fetchJobs();
  } catch (error) {
    console.error("Failed to delete jobs", error);
  } finally {
    isDeleting.value = false;
  }
}

watch([keyword, departmentFilter, statusFilter, activeTab], () => {
  currentPage.value = 1;
});

watch(totalPages, (value) => {
  if (currentPage.value > value) currentPage.value = value;
});

onMounted(() => {
  fetchJobs();
});
</script>
