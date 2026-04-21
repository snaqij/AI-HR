<template>
  <div class="max-w-7xl mx-auto">
    <div class="flex justify-between items-center mb-8">
      <h1 class="text-3xl font-black tracking-tight text-on-surface">{{ zh.pageTitle }}</h1>
      <div class="flex items-center gap-4">
        <button
          @click="handleGlobalSync"
          :disabled="isGlobalSyncing"
          class="flex items-center gap-2 px-6 py-2.5 bg-surface-container-low rounded-xl text-[11px] font-black text-primary uppercase tracking-widest hover:bg-primary/10 transition-all disabled:opacity-50"
        >
          <span class="material-symbols-outlined text-sm" :class="{ 'animate-spin': isGlobalSyncing }">cloud_sync</span>
          {{ zh.syncBossJobs }}
        </button>
        <button class="px-6 py-2.5 rounded-xl ai-gradient text-white text-sm font-black shadow-lg hover-lift transition-all">
          {{ zh.publishNewJob }}
        </button>
      </div>
    </div>

    <div class="bg-surface-container-lowest p-6 rounded-2xl shadow-sm border border-outline-variant/10 mb-8 flex items-center gap-6">
      <div class="flex items-center gap-3 border-r border-outline-variant/20 pr-6 shrink-0">
        <span class="material-symbols-outlined text-primary font-black">smart_button</span>
        <span class="text-sm font-black text-on-surface">{{ zh.smartFilter }}</span>
      </div>

      <div class="flex-1 flex gap-4 items-center">
        <div class="relative min-w-[140px]">
          <label class="absolute -top-2 left-3 bg-white px-1 text-[9px] font-black text-on-surface-variant uppercase tracking-widest z-10">{{ zh.platform }}</label>
          <select v-model="platformFilter" class="w-full bg-surface-container-low/50 border border-outline-variant/10 rounded-lg px-3 py-2 text-xs font-bold appearance-none cursor-pointer focus:ring-2 focus:ring-primary/10 outline-none">
            <option value="">{{ zh.all }}</option>
            <option v-for="platform in platformOptions" :key="platform" :value="platform">{{ platform }}</option>
          </select>
          <span class="material-symbols-outlined absolute right-2 top-1/2 -translate-y-1/2 pointer-events-none text-base text-on-surface-variant">expand_more</span>
        </div>

        <div class="relative flex-1">
          <span class="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-variant text-lg">search</span>
          <input v-model.trim="nameFilter" type="text" :placeholder="zh.searchJobs" class="w-full pl-10 pr-4 py-2 bg-surface-container-low/50 border border-outline-variant/10 rounded-lg text-xs font-medium focus:ring-2 focus:ring-primary/10 outline-none">
        </div>

        <div class="relative min-w-[120px]">
          <label class="absolute -top-2 left-3 bg-white px-1 text-[9px] font-black text-on-surface-variant uppercase tracking-widest z-10">{{ zh.type }}</label>
          <select v-model="typeFilter" class="w-full bg-surface-container-low/50 border border-outline-variant/10 rounded-lg px-3 py-2 text-xs font-bold appearance-none cursor-pointer focus:ring-2 focus:ring-primary/10 outline-none">
            <option value="">{{ zh.all }}</option>
            <option value="intern">{{ zh.intern }}</option>
            <option value="social">{{ zh.social }}</option>
          </select>
          <span class="material-symbols-outlined absolute right-2 top-1/2 -translate-y-1/2 pointer-events-none text-base text-on-surface-variant">expand_more</span>
        </div>

        <div class="relative min-w-[160px]">
          <label class="absolute -top-2 left-3 bg-white px-1 text-[9px] font-black text-on-surface-variant uppercase tracking-widest z-10">{{ zh.salary }}</label>
          <input v-model.trim="salaryFilter" type="text" :placeholder="zh.salaryPlaceholder" class="w-full bg-surface-container-low/50 border border-outline-variant/10 rounded-lg px-3 py-2 text-xs font-medium focus:ring-2 focus:ring-primary/10 outline-none">
          <span class="material-symbols-outlined absolute right-2 top-1/2 -translate-y-1/2 pointer-events-none text-base text-on-surface-variant">expand_more</span>
        </div>
      </div>

      <div class="flex items-center gap-2">
        <button @click="resetFilters" class="px-5 py-2.5 bg-surface-container-high rounded-xl text-[11px] font-black text-on-surface-variant hover:bg-outline-variant/20 transition-all">{{ zh.reset }}</button>
      </div>
    </div>

    <div class="mb-10">
      <div class="flex justify-between items-center mb-6">
        <div>
          <h2 class="text-2xl font-black text-on-surface">{{ zh.activeJobs }}</h2>
          <p class="text-xs text-on-surface-variant font-bold mt-1 uppercase tracking-widest">
            {{ zh.currentTotalPrefix }} <span class="text-primary">{{ filteredJobs.length }}</span> {{ zh.currentTotalSuffix }}
          </p>
        </div>
        <div class="flex items-center gap-3">
          <button
            @click="handleBatchDelete"
            :disabled="selectedJobIds.length === 0"
            class="px-4 py-2 rounded-xl bg-rose-50 text-rose-700 text-xs font-black border border-rose-200 disabled:opacity-50"
          >
            {{ zh.batchDelete }} ({{ selectedJobIds.length }})
          </button>
          <div class="flex bg-surface-container-low p-1 rounded-xl border border-outline-variant/10 shadow-inner">
            <button class="p-2 rounded-lg transition-all" :class="viewMode === 'grid' ? 'bg-white shadow-sm text-primary' : 'text-on-surface-variant/50'" @click="viewMode = 'grid'">
              <span class="material-symbols-outlined">grid_view</span>
            </button>
            <button class="p-2 rounded-lg transition-all" :class="viewMode === 'list' ? 'bg-white shadow-sm text-primary' : 'text-on-surface-variant/50'" @click="viewMode = 'list'">
              <span class="material-symbols-outlined">list</span>
            </button>
          </div>
        </div>
      </div>

      <div class="bg-surface-container-lowest rounded-2xl shadow-sm border border-outline-variant/10 overflow-hidden">
        <div class="grid grid-cols-12 bg-surface-container-low/50 px-8 py-4 text-on-surface-variant border-b border-outline-variant/5">
          <div class="col-span-1 text-center"><input type="checkbox" :checked="allVisibleSelected" @change="toggleSelectAllVisible" /></div>
          <div class="col-span-2"><span class="text-xs font-black uppercase tracking-widest">{{ zh.jobName }}</span></div>
          <div class="col-span-2 text-center"><span class="text-xs font-black uppercase tracking-widest">{{ zh.salaryRange }}</span></div>
          <div class="col-span-2 text-center"><span class="text-xs font-black uppercase tracking-widest">{{ zh.status }}</span></div>
          <div class="col-span-3 text-center"><span class="text-xs font-black uppercase tracking-widest">{{ zh.overview }}</span></div>
          <div class="col-span-2 text-right"><span class="text-xs font-black uppercase tracking-widest">{{ zh.actions }}</span></div>
        </div>

        <div class="divide-y divide-outline-variant/5" v-if="!isLoading">
          <div v-for="job in filteredJobs" :key="job.id" class="grid grid-cols-12 px-8 py-6 items-center hover:bg-surface/50 transition-colors group cursor-pointer" @click="$router.push(`/admin/candidates?jobId=${job.id}`)">
            <div class="col-span-1 text-center">
              <input type="checkbox" :checked="selectedJobIds.includes(job.id)" @click.stop @change="toggleJobSelection(job.id)" />
            </div>
            <div class="col-span-2">
              <p class="font-headline font-black text-base text-on-surface group-hover:text-primary transition-colors">{{ job.title }}</p>
              <p class="text-xs text-on-surface-variant font-bold mt-1 uppercase tracking-widest">{{ job.department }} · {{ job.city }}</p>
            </div>
            <div class="col-span-2 text-center text-sm font-black text-on-surface-variant">
              {{ job.salary_range }}
            </div>
            <div class="col-span-2 text-center">
              <div class="flex flex-col items-center gap-2">
                <span class="px-3 py-1.5 rounded-full text-[10px] font-black tracking-widest uppercase border" :class="getStatusBadge(job.status)">
                  {{ getStatusText(job.status) }}
                </span>
                <span v-if="job.auto_request_resume" class="flex items-center gap-1 text-[8px] font-black text-primary uppercase tracking-tighter bg-primary/5 px-2 py-0.5 rounded-md border border-primary/10">
                  <span class="material-symbols-outlined text-[10px] animate-pulse">robot_2</span> {{ zh.autoResumeOn }}
                </span>
              </div>
            </div>
            <div class="col-span-3 grid grid-cols-2 gap-4 px-4 items-center">
              <div class="text-center">
                <p class="text-sm font-black text-on-surface leading-tight">{{ job.candidate_count || 0 }}</p>
                <p class="text-[10px] font-bold text-on-surface-variant/50 uppercase tracking-tighter">{{ zh.candidates }}</p>
              </div>
              <div class="text-center">
                <p class="text-sm font-black text-on-surface leading-tight">{{ job.publications?.length || 0 }}</p>
                <p class="text-[10px] font-bold text-on-surface-variant/50 uppercase tracking-tighter">{{ zh.channels }}</p>
              </div>
            </div>
            <div class="col-span-2 flex justify-end items-center">
              <button @click.stop="openAutomationSettings(job)" class="w-10 h-10 rounded-xl hover:bg-surface-container-high text-on-surface-variant hover:text-primary transition-all flex items-center justify-center mr-1" :title="zh.automationConfig">
                <span class="material-symbols-outlined text-xl">settings_input_composite</span>
              </button>
              <button @click.stop="handleSync(job.id)" class="w-10 h-10 rounded-xl hover:bg-primary/10 text-on-surface-variant hover:text-primary transition-all flex items-center justify-center group/btn">
                <span class="material-symbols-outlined text-xl group-active/btn:rotate-180 transition-transform">sync</span>
              </button>
            </div>
          </div>
        </div>

        <div v-else-if="!isLoading && filteredJobs.length === 0" class="p-20 text-center">
          <p class="text-xs font-bold text-on-surface-variant mt-4 uppercase tracking-widest">{{ zh.noJobs }}</p>
        </div>

        <div v-else class="p-20 text-center">
          <div class="inline-block w-8 h-8 border-4 border-primary/20 border-t-primary rounded-full animate-spin"></div>
          <p class="text-xs font-bold text-on-surface-variant mt-4 uppercase tracking-widest">{{ zh.loadingJobs }}</p>
        </div>
      </div>
    </div>

    <div v-if="syncLog.length > 0" class="mt-8 bg-surface-container-low p-6 rounded-2xl border border-outline-variant/10">
      <h3 class="text-xs font-black text-on-surface-variant uppercase tracking-widest mb-4">{{ zh.syncLog }}</h3>
      <div class="space-y-2 font-mono text-[10px] text-on-surface-variant/70">
        <p v-for="(log, i) in syncLog.slice(0, 5)" :key="i">{{ log }}</p>
      </div>
    </div>

    <div class="bg-surface-container-lowest p-8 rounded-2xl shadow-sm border border-outline-variant/10 border-l-[4px] border-primary-container relative overflow-hidden group">
      <div class="flex items-start gap-6 relative z-10">
        <div class="w-12 h-12 bg-primary/5 rounded-2xl flex items-center justify-center shrink-0 border border-primary/10">
          <span class="material-symbols-outlined text-primary text-2xl material-fill">lightbulb</span>
        </div>
        <div class="flex-1">
          <h3 class="text-lg font-black text-on-surface mb-2">{{ zh.aiInsightTitle }}</h3>
          <p class="text-xs text-on-surface-variant leading-relaxed font-medium opacity-80">{{ zh.aiInsightText }}</p>
        </div>
      </div>
      <div class="absolute -right-12 -bottom-12 w-48 h-48 bg-primary/5 rounded-full blur-3xl group-hover:bg-primary/10 transition-colors"></div>
    </div>

    <div class="fixed bottom-10 right-10">
      <button class="w-14 h-14 rounded-full ai-gradient text-white shadow-2xl flex items-center justify-center hover:scale-110 active:scale-90 transition-all group">
        <span class="material-symbols-outlined text-2xl">add</span>
        <div class="absolute right-full mr-4 px-4 py-2 bg-on-surface text-white text-[10px] font-black rounded-xl opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap shadow-xl uppercase tracking-widest">
          {{ zh.publishNewJob }}
        </div>
      </button>
    </div>

    <div v-if="showAutomationModal && currentJob" class="fixed inset-0 z-[60] flex items-center justify-center p-4">
      <div class="absolute inset-0 bg-on-surface/40 backdrop-blur-sm" @click="showAutomationModal = false"></div>
      <div class="relative bg-surface-container-lowest w-full max-w-xl rounded-[40px] shadow-2xl overflow-hidden border border-outline-variant/10 animate-in fade-in zoom-in duration-300">
        <div class="px-10 pt-10 pb-8">
          <div class="flex items-center gap-6 mb-8">
            <div class="w-16 h-16 rounded-[24px] ai-gradient flex items-center justify-center shadow-lg shadow-primary/20">
              <span class="material-symbols-outlined text-white text-3xl">robot_2</span>
            </div>
            <div>
              <h3 class="text-2xl font-black text-on-surface tracking-tight">{{ currentJob.title }}</h3>
              <p class="text-[11px] font-bold text-on-surface-variant uppercase tracking-widest">{{ zh.pipelineConfig }}</p>
            </div>
          </div>

          <div class="space-y-8">
            <div class="flex items-center justify-between p-6 bg-surface-container-low rounded-[24px] border border-outline-variant/5">
              <div>
                <p class="text-base font-black text-on-surface">{{ zh.autoResumeTitle }}</p>
                <p class="text-xs text-on-surface-variant font-medium">{{ zh.autoResumeDesc }}</p>
              </div>
              <label class="relative inline-flex items-center cursor-pointer scale-110">
                <input type="checkbox" v-model="currentJob.auto_request_resume" class="sr-only peer">
                <div class="w-12 h-6.5 bg-outline-variant/30 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full rtl:peer-checked:after:-translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:start-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5.5 after:w-5.5 after:transition-all peer-checked:bg-primary"></div>
              </label>
            </div>

            <div class="grid grid-cols-2 gap-6" :class="{ 'opacity-40 pointer-events-none grayscale': !currentJob.auto_request_resume }">
              <div class="relative">
                <label class="absolute -top-2.5 left-4 bg-surface-container-lowest px-1.5 text-[10px] font-black text-primary uppercase tracking-widest z-10">{{ zh.minDegree }}</label>
                <select v-model="currentJob.min_degree" class="w-full bg-surface-container-low/50 border border-outline-variant/10 rounded-2xl px-5 py-4 text-sm font-bold appearance-none cursor-pointer focus:ring-2 focus:ring-primary/20 outline-none">
                  <option v-for="opt in degreeOptions" :key="opt" :value="opt === zh.unlimited ? null : opt">{{ opt }}</option>
                </select>
                <span class="material-symbols-outlined absolute right-4 top-1/2 -translate-y-1/2 pointer-events-none text-on-surface-variant">expand_more</span>
              </div>

              <div class="relative">
                <label class="absolute -top-2.5 left-4 bg-surface-container-lowest px-1.5 text-[10px] font-black text-primary uppercase tracking-widest z-10">{{ zh.minExperience }}</label>
                <input type="number" v-model="currentJob.min_experience_years" placeholder="0" class="w-full bg-surface-container-low/50 border border-outline-variant/10 rounded-2xl px-5 py-4 text-sm font-bold focus:ring-2 focus:ring-primary/20 outline-none">
                <span class="absolute right-5 top-1/2 -translate-y-1/2 text-xs font-black text-on-surface-variant/40">YRS</span>
              </div>
            </div>

            <div class="relative" :class="{ 'opacity-40 pointer-events-none grayscale': !currentJob.auto_request_resume }">
              <label class="absolute -top-2.5 left-4 bg-surface-container-lowest px-1.5 text-[10px] font-black text-primary uppercase tracking-widest z-10">{{ zh.dailyLimit }}</label>
              <input type="number" v-model="currentJob.max_daily_resume_requests" placeholder="10" class="w-full bg-surface-container-low/50 border border-outline-variant/10 rounded-2xl px-5 py-4 text-sm font-bold focus:ring-2 focus:ring-primary/20 outline-none">
              <p class="mt-3 text-[10px] text-on-surface-variant/60 font-medium px-2 flex items-center gap-1.5">
                <span class="material-symbols-outlined text-sm">info</span> {{ zh.dailyLimitTip }}
              </p>
            </div>
          </div>
        </div>

        <div class="px-10 py-8 bg-surface-container-low/50 flex items-center justify-between gap-6">
          <button @click="showAutomationModal = false" class="flex-1 px-8 py-4 rounded-2xl bg-surface-container-high text-sm font-black text-on-surface-variant uppercase tracking-widest hover:bg-outline-variant/20 transition-all">{{ zh.cancel }}</button>
          <button @click="handleSaveSettings" :disabled="isSavingSettings" class="flex-[2] px-8 py-4 rounded-2xl ai-gradient text-white text-sm font-black shadow-lg hover-lift transition-all disabled:opacity-50 flex items-center justify-center gap-2">
            <span v-if="isSavingSettings" class="material-symbols-outlined text-base animate-spin">refresh</span>
            {{ isSavingSettings ? zh.saving : zh.saveAutomation }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { batchDeleteJobs, listJobs, syncJobCandidates, importRemoteJobs, updateJobSettings, type Job } from '../../api';

const zh = {
  pageTitle: '\u804C\u4F4D\u53D1\u5E03\u5217\u8868',
  syncBossJobs: '\u540C\u6B65 BOSS \u804C\u4F4D',
  publishNewJob: '\u53D1\u5E03\u65B0\u804C\u4F4D',
  smartFilter: '\u667A\u80FD\u7B5B\u9009',
  platform: '\u62DB\u8058\u5E73\u53F0',
  all: '\u5168\u90E8',
  searchJobs: '\u641C\u7D22\u804C\u4F4D\u540D\u79F0...',
  type: '\u7C7B\u578B',
  intern: '\u5B9E\u4E60',
  social: '\u793E\u62DB',
  salary: '\u85AA\u8D44\u5F85\u9047',
  salaryPlaceholder: '\u5982 20k-40k',
  reset: '\u91CD\u7F6E',
  activeJobs: '\u5728\u62DB\u804C\u4F4D\u7EDF\u8BA1',
  currentTotalPrefix: '\u5F53\u524D\u5171\u6709',
  currentTotalSuffix: '\u4E2A\u6709\u6548\u5C97\u4F4D\u6B63\u5728\u63A5\u6536\u6295\u9012',
  batchDelete: '\u6279\u91CF\u5220\u9664',
  jobName: '\u804C\u4F4D\u540D\u79F0',
  salaryRange: '\u85AA\u8D44\u8303\u56F4',
  status: '\u72B6\u6001',
  overview: '\u6570\u636E\u6982\u89C8',
  actions: '\u64CD\u4F5C',
  autoResumeOn: '\u667A\u80FD\u83B7\u53D6\u5DF2\u5F00\u542F',
  candidates: '\u5019\u9009\u4EBA',
  channels: '\u6E20\u9053',
  automationConfig: '\u81EA\u52A8\u5316\u914D\u7F6E',
  noJobs: '\u5F53\u524D\u7B5B\u9009\u6761\u4EF6\u4E0B\u6682\u65E0\u5C97\u4F4D\u3002',
  loadingJobs: '\u6B63\u5728\u52A0\u8F7D\u804C\u4F4D\u6570\u636E...',
  syncLog: '\u540C\u6B65\u65E5\u5FD7',
  aiInsightTitle: 'AI \u6E20\u9053\u6D1E\u5BDF',
  aiInsightText: '\u6839\u636E\u76EE\u524D\u7684\u62DB\u8058\u8D8B\u52BF\u5206\u6790\uff0cBOSS \u76F4\u8058\u5728\u6280\u672F\u7C7B\u5C97\u4F4D\uff08AI\u3001\u524D\u7AEF\uff09\u7684\u6295\u9012\u8F6C\u5316\u7387\u66F4\u9AD8\uff0c\u5EFA\u8BAE\u5C06\u91CD\u70B9\u9884\u7B97\u5411\u8BE5\u6E20\u9053\u503E\u659C\u3002',
  pipelineConfig: '\u667A\u80FD\u83B7\u53D6\u6D41\u6C34\u7EBF\u914D\u7F6E',
  autoResumeTitle: '\u5F00\u542F\u81EA\u52A8\u83B7\u53D6\u7B80\u5386',
  autoResumeDesc: '\u7CFB\u7EDF\u5C06\u6309\u8BBE\u5B9A\u9891\u7387\u81EA\u52A8\u7533\u8BF7\u7B26\u5408\u6761\u4EF6\u7684\u7B80\u5386',
  minDegree: '\u6700\u4F4E\u5B66\u5386\u8981\u6C42',
  minExperience: '\u5DE5\u4F5C\u5E74\u9650\u8981\u6C42',
  dailyLimit: '\u6BCF\u65E5\u83B7\u53D6\u4E0A\u9650 (BOSS\u70B9\u6570)',
  dailyLimitTip: '\u5EFA\u8BAE\u8BBE\u7F6E\u4E3A 10-20\uff0c\u4EE5\u4FDD\u8BC1\u70B9\u6570\u53EF\u6301\u7EED\u6D88\u8017\u3002',
  cancel: '\u53D6\u6D88',
  saving: '\u6B63\u5728\u4FDD\u5B58...',
  saveAutomation: '\u4FDD\u5B58\u81EA\u52A8\u5316\u914D\u7F6E',
  unknownError: '\u672A\u77E5\u9519\u8BEF',
  unlimited: '\u4E0D\u9650',
  syncBossAllStart: '\u6B63\u5728\u540C\u6B65 BOSS \u5E73\u53F0\u5168\u91CF\u804C\u4F4D...',
  syncBossAllSuccess: '\u5168\u91CF\u540C\u6B65\u6210\u529F',
  syncBossAllFail: '\u5168\u91CF\u540C\u6B65\u5931\u8D25',
  syncJobStart: '\u6B63\u5728\u540C\u6B65\u804C\u4F4D',
  syncJobSuccess: '\u540C\u6B65\u6210\u529F',
  syncFail: '\u540C\u6B65\u5931\u8D25',
  batchDeleteFail: '\u6279\u91CF\u5220\u9664\u5931\u8D25',
  confirmDeletePrefix: '\u786E\u8BA4\u5220\u9664\u9009\u4E2D\u7684',
  confirmDeleteSuffix: '\u4E2A\u5C97\u4F4D\u5417\uff1F',
  saveFail: '\u4FDD\u5B58\u5931\u8D25',
  statusPublished: '\u5DF2\u53D1\u5E03',
  statusDraft: '\u8349\u7A3F',
  statusActive: '\u8FDB\u884C\u4E2D',
};

const viewMode = ref<'grid' | 'list'>('list');
const jobs = ref<Job[]>([]);
const selectedJobIds = ref<string[]>([]);
const isLoading = ref(true);
const isGlobalSyncing = ref(false);
const syncLog = ref<string[]>([]);
const platformFilter = ref('');
const nameFilter = ref('');
const typeFilter = ref('');
const salaryFilter = ref('');

const platformOptions = computed(() => {
  const channels = new Set<string>();
  for (const job of jobs.value) {
    for (const publication of job.publications || []) {
      if (publication.channel) channels.add(publication.channel);
    }
  }
  return Array.from(channels).sort();
});

const filteredJobs = computed(() => {
  return jobs.value.filter((job) => {
    if (platformFilter.value) {
      const matched = (job.publications || []).some((publication) => publication.channel === platformFilter.value);
      if (!matched) return false;
    }
    if (nameFilter.value && !job.title.toLowerCase().includes(nameFilter.value.toLowerCase())) return false;
    if (typeFilter.value && inferJobType(job) !== typeFilter.value) return false;
    if (salaryFilter.value) {
      const normalizedSalary = (job.salary_range || '').toLowerCase().replace(/\s+/g, '');
      const query = salaryFilter.value.toLowerCase().replace(/\s+/g, '');
      if (!normalizedSalary.includes(query)) return false;
    }
    return true;
  });
});

const allVisibleSelected = computed(() => {
  if (filteredJobs.value.length === 0) return false;
  return filteredJobs.value.every((job) => selectedJobIds.value.includes(job.id));
});

const fetchJobs = async () => {
  isLoading.value = true;
  try {
    jobs.value = await listJobs();
    selectedJobIds.value = selectedJobIds.value.filter((id) => jobs.value.some((job) => job.id === id));
  } catch (e) {
    console.error('Failed to fetch jobs', e);
  } finally {
    isLoading.value = false;
  }
};

const resetFilters = () => {
  platformFilter.value = '';
  nameFilter.value = '';
  typeFilter.value = '';
  salaryFilter.value = '';
};

onMounted(fetchJobs);

const cleanErrorMessage = (err: any) => {
  let msg = String(err || zh.unknownError);
  if (msg.includes('{')) {
    try {
      const jsonStr = msg.substring(msg.indexOf('{'));
      const errData = JSON.parse(jsonStr);
      if (errData?.error?.message) msg = errData.error.message;
    } catch {
      // ignore
    }
  }
  return msg.replace(/\s*\(.*\)\s*/, '').replace(/^.*:\s*/, '').trim();
};

const handleGlobalSync = async () => {
  isGlobalSyncing.value = true;
  syncLog.value.unshift(`[${new Date().toLocaleTimeString()}] ${zh.syncBossAllStart}`);
  try {
    const result = await importRemoteJobs('boss');
    syncLog.value.unshift(`[${new Date().toLocaleTimeString()}] ${zh.syncBossAllSuccess}: +${result.created_count}, ~${result.updated_count}`);
    await fetchJobs();
  } catch (e) {
    syncLog.value.unshift(`[${new Date().toLocaleTimeString()}] ${zh.syncBossAllFail}: ${cleanErrorMessage(e)}`);
  } finally {
    isGlobalSyncing.value = false;
  }
};

const handleSync = async (jobId: string) => {
  syncLog.value.unshift(`[${new Date().toLocaleTimeString()}] ${zh.syncJobStart} ${jobId}...`);
  try {
    await syncJobCandidates(jobId);
    syncLog.value.unshift(`[${new Date().toLocaleTimeString()}] ${zh.syncJobStart} ${jobId} ${zh.syncJobSuccess}`);
    await fetchJobs();
  } catch (e) {
    syncLog.value.unshift(`[${new Date().toLocaleTimeString()}] ${zh.syncFail}: ${cleanErrorMessage(e)}`);
  }
};

const toggleJobSelection = (jobId: string) => {
  if (selectedJobIds.value.includes(jobId)) {
    selectedJobIds.value = selectedJobIds.value.filter((id) => id !== jobId);
    return;
  }
  selectedJobIds.value = [...selectedJobIds.value, jobId];
};

const toggleSelectAllVisible = () => {
  if (allVisibleSelected.value) {
    const visibleIds = new Set(filteredJobs.value.map((job) => job.id));
    selectedJobIds.value = selectedJobIds.value.filter((id) => !visibleIds.has(id));
    return;
  }
  const merged = new Set(selectedJobIds.value);
  for (const job of filteredJobs.value) merged.add(job.id);
  selectedJobIds.value = Array.from(merged);
};

const handleBatchDelete = async () => {
  if (selectedJobIds.value.length === 0) return;
  const confirmed = window.confirm(`${zh.confirmDeletePrefix} ${selectedJobIds.value.length} ${zh.confirmDeleteSuffix}`);
  if (!confirmed) return;
  try {
    await batchDeleteJobs(selectedJobIds.value);
    selectedJobIds.value = [];
    await fetchJobs();
  } catch (e) {
    console.error('Failed to batch delete jobs', e);
    alert(`${zh.batchDeleteFail}: ${e}`);
  }
};

const inferJobType = (job: Job): 'intern' | 'social' => {
  const text = `${job.title || ''} ${job.department || ''} ${job.requirements || ''}`.toLowerCase();
  const internshipKeywords = ['\u5B9E\u4E60', 'intern', '\u5E94\u5C4A', '\u6821\u62DB', '\u6821\u56ED'];
  if (internshipKeywords.some((keyword) => text.includes(keyword))) return 'intern';
  return 'social';
};

const getStatusBadge = (status: string) => {
  switch (status) {
    case 'published': return 'bg-green-50 text-green-700 border-green-100';
    case 'draft': return 'bg-surface-container-high text-on-surface-variant/60 border-outline-variant/10';
    default: return 'bg-primary/10 text-primary border-primary/10';
  }
};

const getStatusText = (status: string) => {
  switch (status) {
    case 'published': return zh.statusPublished;
    case 'draft': return zh.statusDraft;
    default: return zh.statusActive;
  }
};

const showAutomationModal = ref(false);
const currentJob = ref<Job | null>(null);
const isSavingSettings = ref(false);

const openAutomationSettings = (job: Job) => {
  currentJob.value = { ...job };
  showAutomationModal.value = true;
};

const handleSaveSettings = async () => {
  if (!currentJob.value) return;
  isSavingSettings.value = true;
  try {
    const updated = await updateJobSettings(currentJob.value.id, {
      auto_request_resume: currentJob.value.auto_request_resume,
      min_degree: currentJob.value.min_degree,
      min_experience_years: currentJob.value.min_experience_years,
      max_daily_resume_requests: currentJob.value.max_daily_resume_requests,
    });
    const idx = jobs.value.findIndex((j) => j.id === updated.id);
    if (idx !== -1) jobs.value[idx] = updated;
    showAutomationModal.value = false;
  } catch (e) {
    console.error('Failed to save job settings', e);
    alert(`${zh.saveFail}: ${e}`);
  } finally {
    isSavingSettings.value = false;
  }
};

const degreeOptions = [zh.unlimited, '\u5DE5\u4F5C\u7ECF\u9A8C', '\u5927\u4E13', '\u672C\u79D1', '\u7855\u58EB', '\u535A\u58EB'];
</script>
