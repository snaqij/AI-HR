<template>
  <div class="max-w-7xl mx-auto">
    <!-- Page Header -->
    <div class="flex justify-between items-center mb-8">
      <h1 class="text-3xl font-black tracking-tight text-on-surface">岗位发布列表</h1>
      <div class="flex items-center gap-4">
        <button @click="handleGlobalSync" :disabled="isGlobalSyncing" class="flex items-center gap-2 px-6 py-2.5 bg-surface-container-low rounded-xl text-[11px] font-black text-primary uppercase tracking-widest hover:bg-primary/10 transition-all disabled:opacity-50">
            <span class="material-symbols-outlined text-sm" :class="{ 'animate-spin': isGlobalSyncing }">cloud_sync</span> 同步 BOSS 职位
        </button>
        <button class="px-6 py-2.5 rounded-xl ai-gradient text-white text-sm font-black shadow-lg hover-lift transition-all">
          发布新职位
        </button>
      </div>
    </div>

    <!-- Smart Filter Bar -->
    <div class="bg-surface-container-lowest p-6 rounded-2xl shadow-sm border border-outline-variant/10 mb-8 flex items-center gap-6">
        <div class="flex items-center gap-3 border-r border-outline-variant/20 pr-6 shrink-0">
            <span class="material-symbols-outlined text-primary font-black">smart_button</span>
            <span class="text-sm font-black text-on-surface">智能筛选</span>
        </div>
        
        <div class="flex-1 flex gap-4 items-center">
            <div class="relative min-w-[140px]">
                <label class="absolute -top-2 left-3 bg-white px-1 text-[9px] font-black text-on-surface-variant uppercase tracking-widest z-10">招聘平台</label>
                <select class="w-full bg-surface-container-low/50 border border-outline-variant/10 rounded-lg px-3 py-2 text-xs font-bold appearance-none cursor-pointer focus:ring-2 focus:ring-primary/10 outline-none">
                    <option>全部平台</option>
                    <option>BOSS 直聘</option>
                    <option>LinkedIn</option>
                    <option>猎聘</option>
                </select>
                <span class="material-symbols-outlined absolute right-2 top-1/2 -translate-y-1/2 pointer-events-none text-base text-on-surface-variant">expand_more</span>
            </div>

            <div class="relative flex-1">
                <span class="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-variant text-lg">search</span>
                <input type="text" placeholder="搜索岗位名称..." class="w-full pl-10 pr-4 py-2 bg-surface-container-low/50 border border-outline-variant/10 rounded-lg text-xs font-medium focus:ring-2 focus:ring-primary/10 outline-none">
            </div>

            <div class="relative min-w-[160px]">
                <label class="absolute -top-2 left-3 bg-white px-1 text-[9px] font-black text-on-surface-variant uppercase tracking-widest z-10">薪资待遇</label>
                <select class="w-full bg-surface-container-low/50 border border-outline-variant/10 rounded-lg px-3 py-2 text-xs font-bold appearance-none cursor-pointer focus:ring-2 focus:ring-primary/10 outline-none">
                    <option>不限</option>
                    <option>10k-20k</option>
                    <option>20k-40k</option>
                    <option>40k-70k</option>
                </select>
                <span class="material-symbols-outlined absolute right-2 top-1/2 -translate-y-1/2 pointer-events-none text-base text-on-surface-variant">expand_more</span>
            </div>
        </div>

        <div class="flex items-center gap-2">
            <button class="px-5 py-2.5 bg-surface-container-high rounded-xl text-[11px] font-black text-on-surface-variant hover:bg-outline-variant/20 transition-all">重置</button>
        </div>
    </div>

    <!-- Active Jobs Section -->
    <div class="mb-10">
        <div class="flex justify-between items-center mb-6">
            <div>
                <h2 class="text-2xl font-black text-on-surface">在招岗位统计</h2>
                <p class="text-xs text-on-surface-variant font-bold mt-1 uppercase tracking-widest">当前共有 <span class="text-primary">{{ jobs.length }}</span> 个有效岗位正在接收投递</p>
            </div>
            <div class="flex bg-surface-container-low p-1 rounded-xl border border-outline-variant/10 shadow-inner">
                <button class="p-2 rounded-lg transition-all" :class="viewMode === 'grid' ? 'bg-white shadow-sm text-primary' : 'text-on-surface-variant/50'" @click="viewMode = 'grid'">
                    <span class="material-symbols-outlined">grid_view</span>
                </button>
                <button class="p-2 rounded-lg transition-all" :class="viewMode === 'list' ? 'bg-white shadow-sm text-primary' : 'text-on-surface-variant/50'" @click="viewMode = 'list'">
                    <span class="material-symbols-outlined">list</span>
                </button>
            </div>
        </div>

        <!-- Job List -->
        <div class="bg-surface-container-lowest rounded-2xl shadow-sm border border-outline-variant/10 overflow-hidden">
            <div class="grid grid-cols-12 bg-surface-container-low/50 px-8 py-4 text-on-surface-variant border-b border-outline-variant/5">
                <div class="col-span-3"><span class="text-xs font-black uppercase tracking-widest">岗位名称</span></div>
                <div class="col-span-2 text-center"><span class="text-xs font-black uppercase tracking-widest">薪资范围</span></div>
                <div class="col-span-2 text-center"><span class="text-xs font-black uppercase tracking-widest">状态</span></div>
                <div class="col-span-3 text-center"><span class="text-xs font-black uppercase tracking-widest">数据概览</span></div>
                <div class="col-span-2 text-right"><span class="text-xs font-black uppercase tracking-widest">操作</span></div>
            </div>

            <div class="divide-y divide-outline-variant/5" v-if="!isLoading">
                <div v-for="job in jobs" :key="job.id" class="grid grid-cols-12 px-8 py-6 items-center hover:bg-surface/50 transition-colors group cursor-pointer" @click="$router.push(`/admin/candidates?jobId=${job.id}`)">
                    <div class="col-span-3">
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
                                <span class="material-symbols-outlined text-[10px] animate-pulse">robot_2</span> 智能伯乐开启
                            </span>
                        </div>
                    </div>
                    <div class="col-span-3 grid grid-cols-2 gap-4 px-4 items-center">
                        <div class="text-center">
                            <p class="text-sm font-black text-on-surface leading-tight">{{ job.candidate_count || 0 }}</p>
                            <p class="text-[10px] font-bold text-on-surface-variant/50 uppercase tracking-tighter">候选人</p>
                        </div>
                        <div class="text-center">
                            <p class="text-sm font-black text-on-surface leading-tight">{{ job.publications?.length || 0 }}</p>
                            <p class="text-[10px] font-bold text-on-surface-variant/50 uppercase tracking-tighter">渠道</p>
                        </div>
                    </div>
                    <div class="col-span-2 flex justify-end items-center">
                        <button @click.stop="openAutomationSettings(job)" class="w-10 h-10 rounded-xl hover:bg-surface-container-high text-on-surface-variant hover:text-primary transition-all flex items-center justify-center mr-1" title="自动化配置">
                            <span class="material-symbols-outlined text-xl">settings_input_composite</span>
                        </button>
                        <button @click.stop="handleSync(job.id)" class="w-10 h-10 rounded-xl hover:bg-primary/10 text-on-surface-variant hover:text-primary transition-all flex items-center justify-center group/btn">
                            <span class="material-symbols-outlined text-xl group-active/btn:rotate-180 transition-transform">sync</span>
                        </button>
                    </div>
                </div>
            </div>
            <div v-else class="p-20 text-center">
                <div class="inline-block w-8 h-8 border-4 border-primary/20 border-t-primary rounded-full animate-spin"></div>
                <p class="text-xs font-bold text-on-surface-variant mt-4 uppercase tracking-widest">正在加载岗位数据...</p>
            </div>
        </div>
    </div>

    <!-- Sync Log (Debug/Status) -->
    <div v-if="syncLog.length > 0" class="mt-8 bg-surface-container-low p-6 rounded-2xl border border-outline-variant/10">
        <h3 class="text-xs font-black text-on-surface-variant uppercase tracking-widest mb-4">同步日志</h3>
        <div class="space-y-2 font-mono text-[10px] text-on-surface-variant/70">
            <p v-for="(log, i) in syncLog.slice(0, 5)" :key="i">{{ log }}</p>
        </div>
    </div>

    <!-- AI Channel Insights -->
    <div class="bg-surface-container-lowest p-8 rounded-2xl shadow-sm border border-outline-variant/10 border-l-[4px] border-primary-container relative overflow-hidden group">
        <div class="flex items-start gap-6 relative z-10">
            <div class="w-12 h-12 bg-primary/5 rounded-2xl flex items-center justify-center shrink-0 border border-primary/10">
                <span class="material-symbols-outlined text-primary text-2xl material-fill">lightbulb</span>
            </div>
            <div class="flex-1">
                <h3 class="text-lg font-black text-on-surface mb-2">AI 渠道洞察</h3>
                <p class="text-xs text-on-surface-variant leading-relaxed font-medium opacity-80">
                    根据目前的招聘趋势分析，<span class="text-primary font-bold">BOSS 直聘</span> 在技术类岗位 ( AI, 前端 ) 的投递转化率比 LinkedIn 高出 24%。建议将本周重点预算向该渠道倾斜。同时，“首席产品经理”岗位的简历质量目前处于平台领先水平，建议延长目前置顶曝光时间。
                </p>
            </div>
            <div class="hidden lg:flex flex-col items-center justify-center pl-8 ml-6 border-l border-outline-variant/10 h-full">
                <span class="text-[10px] font-black text-on-surface-variant uppercase tracking-widest mb-1">置信度评分</span>
                <span class="text-2xl font-black text-primary">94%</span>
                <div class="w-12 h-1.5 bg-surface-container-low rounded-full mt-2 overflow-hidden shrink-0">
                    <div class="h-full bg-primary w-[94%]"></div>
                </div>
            </div>
        </div>
        <!-- Decorative blob -->
        <div class="absolute -right-12 -bottom-12 w-48 h-48 bg-primary/5 rounded-full blur-3xl group-hover:bg-primary/10 transition-colors"></div>
    </div>

    <!-- Floating Action Button -->
    <div class="fixed bottom-10 right-10">
        <button class="w-14 h-14 rounded-full ai-gradient text-white shadow-2xl flex items-center justify-center hover:scale-110 active:scale-90 transition-all group">
            <span class="material-symbols-outlined text-2xl">add</span>
            <div class="absolute right-full mr-4 px-4 py-2 bg-on-surface text-white text-[10px] font-black rounded-xl opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap shadow-xl uppercase tracking-widest">
                发布新职位
            </div>
        </button>
    </div>
    
    <!-- Automation Settings Modal -->
    <div v-if="showAutomationModal && currentJob" class="fixed inset-0 z-[60] flex items-center justify-center p-4">
        <!-- Backdrop -->
        <div class="absolute inset-0 bg-on-surface/40 backdrop-blur-sm" @click="showAutomationModal = false"></div>
        
        <!-- Modal Content -->
        <div class="relative bg-surface-container-lowest w-full max-w-xl rounded-[40px] shadow-2xl overflow-hidden border border-outline-variant/10 animate-in fade-in zoom-in duration-300">
            <div class="px-10 pt-10 pb-8">
                <div class="flex items-center gap-6 mb-8">
                    <div class="w-16 h-16 rounded-[24px] ai-gradient flex items-center justify-center shadow-lg shadow-primary/20">
                        <span class="material-symbols-outlined text-white text-3xl">robot_2</span>
                    </div>
                    <div>
                        <h3 class="text-2xl font-black text-on-surface tracking-tight">{{ currentJob.title }}</h3>
                        <p class="text-[11px] font-bold text-on-surface-variant uppercase tracking-widest">智能伯乐流水线配置</p>
                    </div>
                </div>

                <div class="space-y-8">
                    <!-- Toggle Switch -->
                    <div class="flex items-center justify-between p-6 bg-surface-container-low rounded-[24px] border border-outline-variant/5">
                        <div>
                            <p class="text-base font-black text-on-surface">开启自动获取简历</p>
                            <p class="text-xs text-on-surface-variant font-medium">系统将按设定的频率自动申请符合条件的简历</p>
                        </div>
                        <label class="relative inline-flex items-center cursor-pointer scale-110">
                            <input type="checkbox" v-model="currentJob.auto_request_resume" class="sr-only peer">
                            <div class="w-12 h-6.5 bg-outline-variant/30 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full rtl:peer-checked:after:-translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:start-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5.5 after:w-5.5 after:transition-all peer-checked:bg-primary"></div>
                        </label>
                    </div>

                    <!-- Filter Thresholds -->
                    <div class="grid grid-cols-2 gap-6" :class="{ 'opacity-40 pointer-events-none grayscale': !currentJob.auto_request_resume }">
                        <div class="relative">
                            <label class="absolute -top-2.5 left-4 bg-surface-container-lowest px-1.5 text-[10px] font-black text-primary uppercase tracking-widest z-10">最低学历要求</label>
                            <select v-model="currentJob.min_degree" class="w-full bg-surface-container-low/50 border border-outline-variant/10 rounded-2xl px-5 py-4 text-sm font-bold appearance-none cursor-pointer focus:ring-2 focus:ring-primary/20 outline-none">
                                <option v-for="opt in degreeOptions" :key="opt" :value="opt === '不限' ? null : opt">{{ opt }}</option>
                            </select>
                            <span class="material-symbols-outlined absolute right-4 top-1/2 -translate-y-1/2 pointer-events-none text-on-surface-variant">expand_more</span>
                        </div>
                        
                        <div class="relative">
                            <label class="absolute -top-2.5 left-4 bg-surface-container-lowest px-1.5 text-[10px] font-black text-primary uppercase tracking-widest z-10">工作年限要求</label>
                            <input type="number" v-model="currentJob.min_experience_years" placeholder="0" class="w-full bg-surface-container-low/50 border border-outline-variant/10 rounded-2xl px-5 py-4 text-sm font-bold focus:ring-2 focus:ring-primary/20 outline-none">
                            <span class="absolute right-5 top-1/2 -translate-y-1/2 text-xs font-black text-on-surface-variant/40">YRS</span>
                        </div>
                    </div>

                    <!-- Daily Limit -->
                    <div class="relative" :class="{ 'opacity-40 pointer-events-none grayscale': !currentJob.auto_request_resume }">
                        <label class="absolute -top-2.5 left-4 bg-surface-container-lowest px-1.5 text-[10px] font-black text-primary uppercase tracking-widest z-10">每日获取上限 (BOSS点数)</label>
                        <input type="number" v-model="currentJob.max_daily_resume_requests" placeholder="10" class="w-full bg-surface-container-low/50 border border-outline-variant/10 rounded-2xl px-5 py-4 text-sm font-bold focus:ring-2 focus:ring-primary/20 outline-none">
                        <p class="mt-3 text-[10px] text-on-surface-variant/60 font-medium px-2 flex items-center gap-1.5">
                            <span class="material-symbols-outlined text-sm">info</span> 建议设为 10-20，以保证点数可持续消耗。
                        </p>
                    </div>
                </div>
            </div>

            <!-- Footer -->
            <div class="px-10 py-8 bg-surface-container-low/50 flex items-center justify-between gap-6">
                <button @click="showAutomationModal = false" class="flex-1 px-8 py-4 rounded-2xl bg-surface-container-high text-sm font-black text-on-surface-variant uppercase tracking-widest hover:bg-outline-variant/20 transition-all">取消</button>
                <button @click="handleSaveSettings" :disabled="isSavingSettings" class="flex-[2] px-8 py-4 rounded-2xl ai-gradient text-white text-sm font-black shadow-lg hover-lift transition-all disabled:opacity-50 flex items-center justify-center gap-2">
                    <span v-if="isSavingSettings" class="material-symbols-outlined text-base animate-spin">refresh</span>
                    {{ isSavingSettings ? '正在保存...' : '保存自动化策略' }}
                </button>
            </div>
        </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { listJobs, syncJobCandidates, importRemoteJobs, type Job } from '../../api';

const viewMode = ref<'grid' | 'list'>('list');
const jobs = ref<Job[]>([]);
const isLoading = ref(true);
const isGlobalSyncing = ref(false);
const syncLog = ref<string[]>([]);

const fetchJobs = async () => {
    isLoading.value = true;
    try {
        jobs.value = await listJobs();
    } catch (e) {
        console.error("Failed to fetch jobs", e);
    } finally {
        isLoading.value = false;
    }
};

onMounted(fetchJobs);

const handleGlobalSync = async () => {
    isGlobalSyncing.value = true;
    syncLog.value.unshift(`[${new Date().toLocaleTimeString()}] 正在同步 BOSS 平台全量岗位...`);
    try {
        const result = await importRemoteJobs("boss");
        syncLog.value.unshift(`[${new Date().toLocaleTimeString()}] 全量同步成功: 新增 ${result.created_count} 个，更新 ${result.updated_count} 个`);
        await fetchJobs();
    } catch (e) {
        syncLog.value.unshift(`[${new Date().toLocaleTimeString()}] 全量同步失败: ${e}`);
    } finally {
        isGlobalSyncing.value = false;
    }
};

const handleSync = async (jobId: string) => {
    syncLog.value.unshift(`[${new Date().toLocaleTimeString()}] 正在同步岗位 ${jobId}...`);
    try {
        await syncJobCandidates(jobId);
        syncLog.value.unshift(`[${new Date().toLocaleTimeString()}] 岗位 ${jobId} 同步成功`);
        await fetchJobs(); // Refresh list to see updated counts
    } catch (e) {
        syncLog.value.unshift(`[${new Date().toLocaleTimeString()}] 同步失败: ${e}`);
    }
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
        case 'published': return '已发布';
        case 'draft': return '草稿';
        default: return '进行中';
    }
};

// Automation Settings Modal
import { updateJobSettings } from '../../api';

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
        // Update local state
        const idx = jobs.value.findIndex(j => j.id === updated.id);
        if (idx !== -1) jobs.value[idx] = updated;
        showAutomationModal.value = false;
    } catch (e) {
        console.error("Failed to save job settings", e);
        alert("保存失败: " + e);
    } finally {
        isSavingSettings.value = false;
    }
};

const degreeOptions = ['不限', '工作经验', '大专', '本科', '硕士', '博士'];
</script>
