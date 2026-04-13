<template>
  <div class="max-w-7xl mx-auto">
    <!-- Header -->
    <div class="flex justify-between items-center mb-10">
      <h1 class="text-3xl font-black tracking-tight text-on-surface">录用决策中心</h1>
    </div>

    <!-- Summary Stats -->
    <div class="grid grid-cols-4 gap-6 mb-12">
      <div v-for="stat in summaryStats" :key="stat.label" class="bg-surface-container-lowest p-6 rounded-2xl shadow-sm border border-outline-variant/10">
        <p class="text-on-surface-variant text-[10px] font-black uppercase tracking-wider mb-2">{{ stat.label }}</p>
        <div class="flex items-baseline gap-2">
            <span class="text-3xl font-black text-on-surface">{{ stat.value }}</span>
            <span v-if="stat.subValue" class="text-[10px] font-bold" :class="stat.subValueColor">{{ stat.subValue }}</span>
        </div>
      </div>
    </div>

    <!-- Main Decision Cards Grid -->
    <div class="grid grid-cols-3 gap-8 mb-16">
      <div v-for="card in decisionCards" :key="card.name" class="bg-surface-container-lowest rounded-3xl shadow-sm border border-outline-variant/10 overflow-hidden flex flex-col group hover-lift">
        <!-- Card Content -->
        <div class="p-8 pb-4">
            <div class="flex justify-between items-start mb-6">
                <div class="flex items-center gap-4">
                    <img :src="card.avatar" class="w-16 h-16 rounded-2xl object-cover shadow-sm border-2 border-surface-container-high" :alt="card.name">
                    <div>
                        <h3 class="text-lg font-black text-on-surface group-hover:text-primary transition-colors">{{ card.name }}</h3>
                        <p class="text-xs text-on-surface-variant font-bold mt-0.5">{{ card.title }}</p>
                        <div class="mt-2 flex gap-2">
                            <span v-for="tag in card.tags" :key="tag" class="px-2 py-0.5 rounded-md text-[9px] font-black tracking-widest uppercase shadow-sm" :class="tag.bg">
                                {{ tag.label }}
                            </span>
                        </div>
                    </div>
                </div>
                <button class="text-on-surface-variant/40 hover:text-on-surface transition-colors">
                    <span class="material-symbols-outlined">more_horiz</span>
                </button>
            </div>

            <!-- AI Insight Box -->
            <div class="bg-primary/5 rounded-2xl p-5 border border-primary/10 mb-6 relative">
                <div class="flex items-center gap-2 mb-3 text-primary">
                    <span class="material-symbols-outlined text-sm material-fill">auto_awesome</span>
                    <span class="text-[10px] font-black uppercase tracking-widest">AI 决策洞察</span>
                </div>
                <p class="text-[11px] text-on-surface leading-relaxed font-medium">
                    {{ card.aiInsight }}
                </p>
            </div>

            <!-- Hiring Progress Stepper -->
            <div class="mb-8">
                <p class="text-[10px] font-black text-on-surface-variant uppercase tracking-widest mb-4">录用流程进度</p>
                <div class="flex items-center justify-between relative px-2">
                    <div class="absolute top-1/2 left-4 right-4 h-0.5 bg-surface-container-high -translate-y-1/2 -z-0"></div>
                    <div 
                        class="absolute top-1/2 left-4 h-0.5 bg-green-500 -translate-y-1/2 transition-all duration-1000" 
                        :style="{ width: card.progressWidth }"
                    ></div>
                    <div v-for="(step, idx) in card.steps" :key="idx" class="relative z-10 flex flex-col items-center gap-2">
                        <div 
                            class="w-3.5 h-3.5 rounded-full border-2 flex items-center justify-center transition-all duration-500"
                            :class="[
                                step.status === 'completed' ? 'bg-green-500 border-green-500 text-white' : 
                                step.status === 'active' ? 'bg-white border-primary shadow-[0_0_8px_rgba(0,58,162,0.3)]' : 
                                'bg-white border-outline-variant'
                            ]"
                        >
                            <span v-if="step.status === 'completed'" class="material-symbols-outlined text-[10px] font-black">check</span>
                            <div v-if="step.status === 'active'" class="w-1.5 h-1.5 bg-primary rounded-full animate-pulse"></div>
                        </div>
                        <span class="text-[8px] font-black uppercase tracking-tighter" :class="step.status === 'completed' ? 'text-green-600' : 'text-on-surface-variant opacity-60'">{{ step.label }}</span>
                    </div>
                </div>
            </div>

            <!-- Detailed Metrics -->
            <div class="grid grid-cols-2 gap-6 mb-8 border-t border-b border-outline-variant/5 py-6">
                <div>
                    <p class="text-[9px] font-black text-on-surface-variant uppercase tracking-widest mb-1">预估薪资</p>
                    <p class="text-sm font-black text-on-surface">¥{{ card.salary }}/年</p>
                </div>
                <div>
                    <p class="text-[9px] font-black text-on-surface-variant uppercase tracking-widest mb-1">预计到岗日期</p>
                    <p class="text-sm font-black text-on-surface">{{ card.date }}</p>
                </div>
            </div>

            <!-- Collaboration Note -->
            <div class="bg-surface p-4 rounded-xl mb-8 border border-outline-variant/10 italic">
                <p class="text-[10px] text-on-surface-variant leading-relaxed">
                    "{{ card.note }}" <span class="not-italic font-bold ml-1 opacity-60">- {{ card.noteAuthor }}</span>
                </p>
            </div>
        </div>

        <!-- Action Buttons Footer -->
        <div class="mt-auto p-8 pt-0 space-y-3">
            <button class="w-full py-3.5 rounded-xl bg-primary text-white text-xs font-black shadow-lg shadow-primary/20 hover:brightness-110 active:scale-95 transition-all">
                {{ card.primaryAction }}
            </button>
            <div class="grid grid-cols-2 gap-3">
                <button class="py-2.5 rounded-xl bg-surface-container-high text-on-surface-variant text-[10px] font-black hover:bg-outline-variant/30 transition-all uppercase tracking-widest">
                    {{ card.secondaryAction }}
                </button>
                <button class="py-2.5 rounded-xl bg-surface-container-high text-on-surface-variant text-[10px] font-black hover:bg-outline-variant/30 transition-all uppercase tracking-widest">
                    查看完整报告
                </button>
            </div>
        </div>
      </div>
    </div>

    <!-- Wait Decision Queue -->
    <div class="bg-surface-container-lowest rounded-3xl p-8 shadow-sm border border-outline-variant/10">
        <div class="flex justify-between items-center mb-8">
            <div>
                <h3 class="text-xl font-black text-on-surface">待处理决策队列</h3>
                <p class="text-xs text-on-surface-variant font-bold mt-1">系统自动筛选出待高层最终签署的优秀人选。</p>
            </div>
            <div class="flex gap-3">
                <button class="px-5 py-2.5 bg-surface-container-high rounded-xl text-[11px] font-black text-on-surface-variant flex items-center gap-2">
                    <span class="material-symbols-outlined text-base">filter_list</span> 筛选
                </button>
                <button class="px-5 py-2.5 bg-surface-container-high rounded-xl text-[11px] font-black text-on-surface-variant flex items-center gap-2">
                    <span class="material-symbols-outlined text-base">ios_share</span> 导出报告
                </button>
            </div>
        </div>

        <div class="overflow-x-auto">
            <table class="w-full text-left">
                <thead>
                    <tr class="bg-surface-container-low/50 text-on-surface-variant border-b border-outline-variant/10">
                        <th class="px-6 py-4 text-[10px] font-black uppercase tracking-widest">候选人</th>
                        <th class="px-6 py-4 text-[10px] font-black uppercase tracking-widest">职位</th>
                        <th class="px-6 py-4 text-[10px] font-black uppercase tracking-widest">预估薪资</th>
                        <th class="px-6 py-4 text-[10px] font-black uppercase tracking-widest">AI 情感分析评分</th>
                        <th class="px-6 py-4 text-[10px] font-black uppercase tracking-widest text-right">操作</th>
                    </tr>
                </thead>
                <tbody class="text-sm divide-y divide-outline-variant/5">
                    <tr v-for="item in decisionQueue" :key="item.name" class="group hover:bg-surface transition-colors">
                        <td class="px-6 py-5 flex items-center gap-3">
                            <div class="w-10 h-10 rounded-xl bg-surface-container-high flex items-center justify-center font-black text-xs text-on-surface-variant border border-outline-variant/10">
                                {{ item.initials }}
                            </div>
                            <span class="font-black text-on-surface">{{ item.name }}</span>
                        </td>
                        <td class="px-6 py-5 font-bold text-on-surface-variant">{{ item.job }}</td>
                        <td class="px-6 py-5 font-black text-on-surface">¥{{ item.salary.toLocaleString() }}</td>
                        <td class="px-6 py-5">
                            <div class="flex items-center gap-4">
                                <div class="flex items-center gap-1 text-primary">
                                    <span v-for="i in 5" :key="i" class="material-symbols-outlined text-base" :class="{ 'material-fill': i <= item.rating }">star</span>
                                </div>
                                <span class="px-2 py-0.5 bg-primary/5 text-primary text-[10px] font-black rounded border border-primary/10 tracking-widest uppercase">{{ item.analysis }}</span>
                            </div>
                        </td>
                        <td class="px-6 py-5 text-right">
                            <button class="text-xs font-black text-primary hover:underline tracking-widest uppercase">最终审批</button>
                        </td>
                    </tr>
                </tbody>
            </table>
        </div>
    </div>
  </div>
</template>

<script setup lang="ts">
const summaryStats = [
    { label: '待审批人选', value: '08', subValue: '+2 本周', subValueColor: 'text-primary' },
    { label: '已发录用信', value: '14', subValue: '10 已查看', subValueColor: 'text-green-600' },
    { label: '待入职', value: '06', subValue: '预计本月', subValueColor: 'text-on-surface-variant/50' },
    { label: '入职转化率', value: '92.4%', subValue: '↗', subValueColor: 'text-green-600' },
];

const decisionCards = [
    {
        name: 'Elena Vance',
        title: '资深 UI 架构师',
        avatar: 'https://lh3.googleusercontent.com/aida-public/AB6AXuBfEMX41MlB8WqPmh-WP1qTQq6jifQSnVFYQke84JX9gPWNZBl05Jj4irlpgSvyqrZuasiKtuTE9REvtVKm-6LMReSuqPGUwrr04EZhUWKG5a8v2Qg8XZRvU86UbFsKvtRF0Y8bVO8T_iZXlwm9XrNiQcTCYQnoTnDnbIJcaMBRVlunHg9hRtNGpS3RpDua80XRU5UpAvOcxyAyjv87og1mpQUfLnrJB0wX1DoucXv8yR7Ks9dcsfz091NtU93jywjRs-j9kf_5S9U',
        tags: [{ label: '首选', bg: 'bg-primary/10 text-primary' }],
        aiInsight: '核心技能匹配度 98%。具备卓越的空间推理能力与组件生命周期管理经验，高度契合团队技术栈。',
        progressWidth: '33%',
        steps: [
            { label: '已准备', status: 'completed' },
            { label: '待批准', status: 'active' },
            { label: '已发送', status: 'pending' },
            { label: '背景调查', status: 'pending' },
        ],
        salary: '14.5万',
        date: '2023.10.12',
        note: '候选人在系统架构方面有独到见解，建议重点关注其领导力潜质。',
        noteAuthor: 'David',
        primaryAction: '批准并发送录用信',
        secondaryAction: '请求复核'
    },
    {
        name: 'Marcus Thorne',
        title: '首席数据科学家',
        avatar: 'https://lh3.googleusercontent.com/aida-public/AB6AXuAAfPi283ykI0rH0Fd8Xr7b2LsyFWoegl-wsov0asEgLV-K6lmQH5QDsZyVkTg3yttWa0Y1oHWc_2T4xeCUU7SPa0R0AMdQbKCrCY3U1PkwhBbN8g3iQJA5VKaEosIAGsJdtOoCfw-x3Res-4cZgVRYfPGuxB8g3PoPy2rlOOQWv0OGdyJxpD25pAdlti3aA60f_iSds57HtazqhU3KDPZQa1N_MpIJ8Xm-U70Pz9mo61UwErI6Og_d8lAW5it9Okd9OdPmSI1v4sg',
        tags: [{ label: '强烈推荐', bg: 'bg-green-100 text-green-700' }],
        aiInsight: '卓越的数据建模经验。薪资期望与内部对标职级完全一致，具备极强的跨部门协作能力潜力。',
        progressWidth: '66%',
        steps: [
            { label: '已准备', status: 'completed' },
            { label: '已批准', status: 'completed' },
            { label: '待接受', status: 'active' },
            { label: '背景调查', status: 'pending' },
        ],
        salary: '16.8万',
        date: '2023.11.01',
        note: '候选人对行业动态非常敏锐，期待其能为团队带来新的增长视角。',
        noteAuthor: 'Sarah',
        primaryAction: '等待候选人确认',
        secondaryAction: '重新议薪'
    },
    {
        name: 'Sienna Lopez',
        title: '产品策略师',
        avatar: 'https://lh3.googleusercontent.com/aida-public/AB6AXuBWR2dFtuX6JwTTsX5DG6i2J9RuBh23XThA_OhX3S9E6gmN5qNdekhTJ2PnUAAfa0TKuCWUw2OkynpJpXaExVyhoPLpWbA0Zh46yUZSGzP_0iqIJFZEupt-HV1ghfrmlunRS8kl1PtcGDLAg8XfEdEGSKMxkSFH37Zh4SgJ_TSk44sMfvGB2KXL4puHNEad2RBg-4ik4HA42niHi2Y3HnRkTiWATjfi_CfFzA69cdakeNynAH2HNlyl1RSF_z8xQBI5gEDO7G_0GhY',
        tags: [{ label: '首选', bg: 'bg-primary/10 text-primary' }],
        aiInsight: '合同签署完成。背景调查无误。软硬件配置已寄出，入职就绪度 100%。',
        progressWidth: '100%',
        steps: [
            { label: '已批准', status: 'completed' },
            { label: '已接受', status: 'completed' },
            { label: '背景调查', status: 'completed' },
            { label: '待入职', status: 'active' },
        ],
        salary: '预计报到',
        date: '下周一 (10.09)',
        note: '导师已安排首次面谈，欢迎礼包准备就绪。',
        noteAuthor: 'HR Admin',
        primaryAction: '准备欢迎仪式',
        secondaryAction: '更新档案'
    }
];

const decisionQueue = [
    { name: 'Jordan Davis', initials: 'JD', job: '后端工程师 (Golang)', salary: 138000, rating: 5, analysis: '核心推荐' },
    { name: 'Aria Lane', initials: 'AL', job: '市场部负责人', salary: 122500, rating: 5, analysis: '完美契合' },
];
</script>
