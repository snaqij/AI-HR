<template>
  <div class="max-w-7xl mx-auto">
    <!-- Top Navigation -->
    <div class="flex items-center gap-6 mb-10">
      <button @click="$router.back()" class="w-10 h-10 rounded-full hover:bg-surface-container-high transition-colors flex items-center justify-center">
        <span class="material-symbols-outlined text-on-surface-variant font-black">arrow_back</span>
      </button>
      <div class="flex items-center gap-4">
        <h1 class="text-2xl font-black text-on-surface">面试详情与 AI 分析</h1>
        <div class="flex bg-surface-container-low p-1 rounded-lg border border-outline-variant/10 text-[10px] font-black uppercase tracking-widest">
            <button class="px-3 py-1 bg-white shadow-sm rounded-md text-primary">所有记录</button>
            <button class="px-3 py-1 text-on-surface-variant/50">进行中的会话</button>
        </div>
      </div>
      <div class="flex-1"></div>
      <div class="relative w-64">
        <span class="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-variant text-lg">search</span>
        <input type="text" placeholder="搜索面试记录..." class="w-full pl-10 pr-4 py-2 bg-surface-container-low border-none rounded-full text-xs font-medium focus:ring-2 focus:ring-primary/20 transition-all font-body shadow-inner">
      </div>
    </div>

    <!-- Candidate Header Card -->
    <div class="bg-surface-container-lowest rounded-3xl p-8 shadow-sm border border-outline-variant/10 mb-8 flex justify-between items-center relative overflow-hidden">
        <div class="flex items-center gap-8 relative z-10">
            <div class="relative">
                <div class="w-24 h-24 rounded-3xl overflow-hidden border-2 border-surface-container-high bg-blue-50 shadow-sm relative">
                    <img src="https://lh3.googleusercontent.com/aida-public/AB6AXuBWR2dFtuX6JwTTsX5DG6i2J9RuBh23XThA_OhX3S9E6gmN5qNdekhTJ2PnUAAfa0TKuCWUw2OkynpJpXaExVyhoPLpWbA0Zh46yUZSGzP_0iqIJFZEupt-HV1ghfrmlunRS8kl1PtcGDLAg8XfEdEGSKMxkSFH37Zh4SgJ_TSk44sMfvGB2KXL4puHNEad2RBg-4ik4HA42niHi2Y3HnRkTiWATjfi_CfFzA69cdakeNynAH2HNlyl1RSF_z8xQBI5gEDO7G_0GhY" alt="李华" class="w-full h-full object-cover">
                </div>
                <div class="absolute -bottom-2 -right-2 bg-primary text-white text-[9px] font-black px-2 py-0.5 rounded-full border-2 border-white shadow-sm uppercase tracking-widest">Pro</div>
            </div>
            <div>
                <div class="flex items-center gap-3 mb-2">
                    <h2 class="text-3xl font-black text-on-surface">李华 (Li Hua)</h2>
                    <span class="px-2 py-0.5 bg-green-50 text-green-700 text-[10px] font-black rounded-lg border border-green-100 uppercase tracking-widest">在职</span>
                </div>
                <p class="text-sm font-bold text-on-surface-variant/80">高级资深后端开发工程师 | <span class="text-on-surface">8年经验</span></p>
                <div class="flex items-center gap-6 mt-4 text-[10px] font-black text-on-surface-variant/60 uppercase tracking-widest">
                    <div class="flex items-center gap-1.5"><span class="material-symbols-outlined text-base">location_on</span> 上海, 中国</div>
                    <div class="flex items-center gap-1.5"><span class="material-symbols-outlined text-base">mail</span> LI.HUA@EXAMPLE.COM</div>
                </div>
            </div>
        </div>
        <div class="flex items-center gap-12 relative z-10">
            <div class="flex flex-col items-center gap-2">
                <p class="text-[9px] font-black text-on-surface-variant uppercase tracking-[0.2em]">总体匹配度</p>
                <div class="w-20 h-20 rounded-full border-[6px] border-primary/10 flex items-center justify-center relative">
                    <span class="text-2xl font-black text-on-surface">92</span>
                    <!-- Progress ring would go here -->
                    <svg class="absolute inset-0 w-full h-full -rotate-90">
                        <circle cx="40" cy="40" r="34" stroke="currentColor" stroke-width="6" fill="transparent" class="text-primary" stroke-dasharray="213" stroke-dashoffset="17" />
                    </svg>
                </div>
            </div>
            <div class="text-center min-w-[120px]">
                <p class="text-[9px] font-black text-on-surface-variant uppercase tracking-[0.2em] mb-2">最终评估</p>
                <p class="text-xl font-black text-primary mb-4 leading-none">强烈推荐</p>
                <button class="px-4 py-2 bg-primary rounded-xl text-white text-[10px] font-black shadow-lg shadow-primary/20 hover:brightness-110 active:scale-95 transition-all">安排技术终面</button>
            </div>
        </div>
        <!-- Decoration -->
        <div class="absolute -left-12 -bottom-12 w-48 h-48 bg-primary/2 rounded-full blur-3xl"></div>
    </div>

    <!-- Main Content Area -->
    <div class="grid grid-cols-12 gap-8 mb-16">
        <!-- Dialogue History (7 cols) -->
        <section class="col-span-12 lg:col-span-7 bg-surface-container-lowest rounded-3xl p-8 shadow-sm border border-outline-variant/10">
            <div class="flex justify-between items-center mb-10">
                <div class="flex items-center gap-3">
                    <span class="material-symbols-outlined text-primary font-black material-fill">chat_bubble</span>
                    <h3 class="text-lg font-black text-on-surface">面试对话记录</h3>
                </div>
                <span class="text-[10px] font-bold text-on-surface-variant opacity-50 uppercase tracking-widest">时长: 42 分钟</span>
            </div>

            <div class="space-y-12 relative before:absolute before:left-3 before:top-4 before:bottom-4 before:w-px before:bg-surface-container-high">
                <div v-for="(turn, idx) in dialogue" :key="idx" class="space-y-6">
                    <!-- AI Question -->
                    <div class="relative pl-10 group">
                        <div class="absolute left-0 top-1 w-6 h-6 rounded-lg bg-primary flex items-center justify-center text-white shadow-md shadow-primary/20">
                            <span class="material-symbols-outlined text-xs material-fill">psychology</span>
                        </div>
                        <div class="bg-surface-container-low/50 rounded-2xl p-6 border border-outline-variant/5">
                            <p class="text-[10px] font-black text-primary uppercase tracking-[0.2em] mb-3">AI 提问:</p>
                            <p class="text-xs font-bold text-on-surface leading-loose">{{ turn.question }}</p>
                        </div>
                    </div>
                    <!-- Candidate Answer -->
                    <div class="relative pl-10 group">
                        <div class="absolute left-0 top-1 w-6 h-6 rounded-lg bg-surface-container-high flex items-center justify-center text-on-surface-variant border border-outline-variant/20 shadow-sm">
                            <span class="material-symbols-outlined text-xs material-fill">person</span>
                        </div>
                        <div class="bg-white rounded-2xl p-6 shadow-sm border border-outline-variant/10 relative overflow-hidden group-hover:border-primary/10 transition-colors">
                            <p class="text-[10px] font-black text-on-surface-variant uppercase tracking-[0.2em] mb-3">李华 回答:</p>
                            <p class="text-xs font-medium text-on-surface leading-loose opacity-90">{{ turn.answer }}</p>
                        </div>
                    </div>
                </div>
            </div>
        </section>

        <!-- Analysis Sidebar (5 cols) -->
        <section class="col-span-12 lg:col-span-5 space-y-8">
            <!-- AI Depth Analysis -->
            <div class="bg-surface-container-lowest rounded-3xl p-8 shadow-sm border border-outline-variant/10 overflow-hidden relative group">
                <div class="flex items-center gap-3 mb-8">
                    <span class="material-symbols-outlined text-primary font-black">analytics</span>
                    <h3 class="text-lg font-black text-on-surface">AI 深度分析</h3>
                </div>

                <div class="space-y-10">
                    <div>
                        <div class="flex justify-between items-end mb-3">
                            <span class="text-[11px] font-black text-on-surface uppercase tracking-widest">技术专业度</span>
                            <span class="text-lg font-black text-primary">95/100</span>
                        </div>
                        <div class="w-full h-1.5 bg-surface-container-low rounded-full overflow-hidden shadow-inner">
                            <div class="h-full ai-gradient w-[95%]"></div>
                        </div>
                        <p class="text-[11px] text-on-surface-variant mt-4 leading-relaxed font-medium">
                            展现了极强的分布式架构理解力。不仅能描述解决方案，还能深入到底层锁机制和索引原理。对性能瓶颈的敏感度极高。
                        </p>
                    </div>

                    <div>
                        <div class="flex justify-between items-end mb-3">
                            <span class="text-[11px] font-black text-on-surface uppercase tracking-widest">行为表现 / 软素质</span>
                            <span class="text-lg font-black text-primary">88/100</span>
                        </div>
                        <div class="w-full h-1.5 bg-surface-container-low rounded-full overflow-hidden shadow-inner">
                            <div class="h-full bg-primary w-[88%]"></div>
                        </div>
                        <div class="flex gap-2 mt-4">
                            <span class="px-3 py-1 bg-surface-container-low text-[9px] font-black text-on-surface-variant rounded-full border border-outline-variant/5 uppercase tracking-widest">理性沟通</span>
                            <span class="px-3 py-1 bg-surface-container-low text-[9px] font-black text-on-surface-variant rounded-full border border-outline-variant/5 uppercase tracking-widest">极强韧性</span>
                            <span class="px-3 py-1 bg-surface-container-low text-[9px] font-black text-on-surface-variant rounded-full border border-outline-variant/5 uppercase tracking-widest">逻辑严密</span>
                        </div>
                    </div>
                </div>

                <!-- Decorative graph shadow -->
                <div class="absolute right-0 top-0 w-32 h-32 opacity-5 -scale-x-100 translate-x-10 pointer-events-none">
                    <svg viewBox="0 0 100 100" class="w-full h-full fill-primary">
                        <path d="M0 80 L20 60 L40 70 L60 40 L80 50 L100 20 L100 100 L0 100 Z" />
                    </svg>
                </div>
            </div>

            <!-- AI Key Insights -->
            <div class="bg-surface-container-lowest rounded-3xl p-8 shadow-sm border border-outline-variant/10 border-l-[4px] border-primary relative overflow-hidden">
                <h3 class="text-lg font-black text-on-surface mb-8">AI 关键洞察</h3>
                <div class="space-y-8 relative">
                    <div class="flex items-start gap-4">
                        <div class="w-8 h-8 rounded-xl bg-green-50 flex items-center justify-center shrink-0 border border-green-100">
                            <span class="material-symbols-outlined text-green-600 text-base material-fill">verified</span>
                        </div>
                        <div>
                            <p class="text-[10px] font-black text-green-700 uppercase tracking-widest mb-1">高确定性:</p>
                            <p class="text-[11px] text-on-surface font-medium leading-relaxed">候选人在描述 MySQL 调优时的技术细节高度一致，排除背诵面试题的可能。</p>
                        </div>
                    </div>
                    <div class="flex items-start gap-4">
                        <div class="w-8 h-8 rounded-xl bg-blue-50 flex items-center justify-center shrink-0 border border-blue-100">
                            <span class="material-symbols-outlined text-blue-600 text-base material-fill">help</span>
                        </div>
                        <div>
                            <p class="text-[10px] font-black text-blue-700 uppercase tracking-widest mb-1">领导潜力:</p>
                            <p class="text-[11px] text-on-surface font-medium leading-relaxed">在处理冲突的回答中，展现了成熟的冲突协调能力和架构师思维。</p>
                        </div>
                    </div>
                    <div class="flex items-start gap-4">
                        <div class="w-8 h-8 rounded-xl bg-error-container/20 flex items-center justify-center shrink-0 border border-error-container/10">
                            <span class="material-symbols-outlined text-error text-base material-fill">warning</span>
                        </div>
                        <div>
                            <p class="text-[10px] font-black text-error uppercase tracking-widest mb-1">潜在风险:</p>
                            <p class="text-[11px] text-on-surface font-medium leading-relaxed">薪资预期略高于当前部门平均水平 (约高出 15%)，建议确认预算空间。</p>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Team Culture Fit -->
            <div class="bg-primary/90 rounded-3xl p-8 shadow-xl relative overflow-hidden group">
                <div class="flex items-center justify-between relative z-10">
                    <div>
                        <p class="text-[9px] font-black text-white/60 uppercase tracking-[0.2em] mb-1">团队文化匹配</p>
                        <h3 class="text-2xl font-black text-white tracking-tight">极高 (高度匹配)</h3>
                    </div>
                    <div class="w-14 h-14 bg-white/20 rounded-2xl flex items-center justify-center backdrop-blur-md border border-white/10 group-hover:scale-110 transition-transform">
                        <span class="material-symbols-outlined text-white text-3xl material-fill">groups</span>
                    </div>
                </div>
                <!-- Decoration -->
                <div class="absolute -right-12 -bottom-12 w-48 h-48 bg-white/10 rounded-full blur-3xl"></div>
            </div>
        </section>
    </div>

    <!-- Bottom Actions Toolbar -->
    <div class="fixed bottom-0 left-64 right-0 h-24 bg-surface/90 backdrop-blur-xl border-t border-outline-variant/10 px-12 flex items-center justify-between z-40">
        <div class="flex gap-8">
            <button class="flex items-center gap-2 text-[10px] font-black text-on-surface-variant hover:text-primary transition-all uppercase tracking-widest group">
                <span class="material-symbols-outlined text-lg group-hover:scale-110 transition-transform">picture_as_pdf</span>
                下载面试报告 (PDF)
            </button>
            <button class="flex items-center gap-2 text-[10px] font-black text-on-surface-variant hover:text-primary transition-all uppercase tracking-widest group">
                <span class="material-symbols-outlined text-lg group-hover:scale-110 transition-transform">ios_share</span>
                分享给 HR
            </button>
        </div>
        <div class="flex gap-4">
            <button class="px-6 py-3 rounded-xl bg-surface-container-high text-on-surface-variant text-[11px] font-black hover:bg-outline-variant/30 transition-all uppercase tracking-[0.2em]">标记为不合适</button>
            <button class="px-8 py-3 rounded-xl bg-primary text-white text-[11px] font-black shadow-lg shadow-primary/20 hover:brightness-110 active:scale-95 transition-all uppercase tracking-[0.2em]">推进至下一轮</button>
        </div>
    </div>
  </div>
</template>

<script setup lang="ts">
const dialogue = [
    {
        question: '请描述您在处理高并发分布式系统时，如何解决数据库死锁问题的具体案例？',
        answer: '在之前处理一个每秒 50k QPS 的电商下单系统时，我们遇到了因事务更新顺序不一致导致的间隙锁死锁。我首先通过分析 MySQL InnoDB Monitor 的日志定位了加锁链路。随后，我们将更新操作标准化，确保所有事务按相同的主键顺序获取锁。同时，我们引入了 Redis 预减库存来降低数据库层面的直接并发竞争...'
    },
    {
        question: '在团队协作中，如果你的架构建议被大多数同事反对，你会如何处理？',
        answer: '我会先审视反对意见的核心逻辑。如果是因为我没表达清楚成本和收益，我会准备一份更详尽的数据对比报告。如果反对是因为现有的系统的维护压力，我会建议先做一个小规模的 PoC 验证。我更倾向于通过共识而非权力驱动决策，确保团队每个人都能在最终方案中找到价值点。'
    }
];
</script>
