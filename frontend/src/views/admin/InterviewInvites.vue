<template>
  <div class="max-w-7xl mx-auto">
    <!-- Header -->
    <div class="flex justify-between items-center mb-10">
      <div>
        <h1 class="text-3xl font-black tracking-tight text-on-surface">面试邀请记录</h1>
        <p class="text-xs text-on-surface-variant font-bold mt-1 uppercase tracking-widest">跟踪所有 AI 面试邀请的状态与进展</p>
      </div>
      <button class="px-6 py-2.5 rounded-xl ai-gradient text-white text-sm font-black shadow-lg hover-lift">
        发起批量邀请
      </button>
    </div>

    <!-- Filters -->
    <div class="bg-surface-container-lowest p-6 rounded-2xl shadow-sm border border-outline-variant/10 mb-8 flex items-center gap-6">
        <div class="flex-1 flex gap-4">
            <div class="relative flex-1">
                <span class="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-variant text-lg">search</span>
                <input type="text" placeholder="搜索候选人或职位..." class="w-full pl-10 pr-4 py-2 bg-surface-container-low/50 border border-outline-variant/10 rounded-lg text-xs font-medium focus:ring-2 focus:ring-primary/10 outline-none">
            </div>
            <select class="bg-surface-container-low/50 border border-outline-variant/10 rounded-lg px-4 py-2 text-xs font-bold appearance-none cursor-pointer min-w-[120px]">
                <option>邀请状态</option>
                <option>待处理</option>
                <option>已预约</option>
                <option>已完成</option>
            </select>
        </div>
    </div>

    <!-- Invite History Table -->
    <div class="bg-surface-container-lowest rounded-2xl shadow-sm border border-outline-variant/10 overflow-hidden">
        <div class="grid grid-cols-12 bg-surface-container-low/50 px-8 py-4 text-on-surface-variant border-b border-outline-variant/5">
            <div class="col-span-3"><span class="text-[10px] font-black uppercase tracking-widest">候选人</span></div>
            <div class="col-span-3"><span class="text-[10px] font-black uppercase tracking-widest">申请职位</span></div>
            <div class="col-span-2 text-center"><span class="text-[10px] font-black uppercase tracking-widest">邀请时间</span></div>
            <div class="col-span-2 text-center"><span class="text-[10px] font-black uppercase tracking-widest">状态</span></div>
            <div class="col-span-2 text-right"><span class="text-[10px] font-black uppercase tracking-widest">操作</span></div>
        </div>

        <div class="divide-y divide-outline-variant/5">
            <div v-for="invite in invites" :key="invite.id" class="grid grid-cols-12 px-8 py-6 items-center hover:bg-surface/50 transition-colors group cursor-pointer">
                <div class="col-span-3">
                    <p class="font-headline font-black text-sm text-on-surface group-hover:text-primary transition-colors">{{ invite.candidate }}</p>
                    <p class="text-[11px] text-on-surface-variant font-bold mt-1">{{ invite.email }}</p>
                </div>
                <div class="col-span-3 font-bold text-xs text-on-surface-variant">
                    {{ invite.job }}
                </div>
                <div class="col-span-2 text-center">
                    <p class="text-xs font-bold text-on-surface">{{ invite.date }}</p>
                    <p class="text-[10px] text-on-surface-variant opacity-60 mt-0.5">{{ invite.time }}</p>
                </div>
                <div class="col-span-2 text-center">
                    <span class="px-3 py-1 rounded-full text-[9px] font-black tracking-widest uppercase border" :class="invite.statusClass">
                        {{ invite.status }}
                    </span>
                </div>
                <div class="col-span-2 text-right">
                    <button @click="$router.push(`/admin/interview/${invite.id}`)" v-if="invite.status === '已完成'" class="text-xs font-black text-primary hover:underline uppercase tracking-widest">查看分析</button>
                    <button v-else class="text-xs font-black text-on-surface-variant/40 hover:text-primary transition-colors uppercase tracking-widest">重发提醒</button>
                </div>
            </div>
        </div>
    </div>
  </div>
</template>

<script setup lang="ts">
const invites = [
    { id: '1', candidate: '张伟', email: 'zhang.wei@mail.com', job: '后端开发工程师', date: '2023.10.25', time: '14:30', status: '已完成', statusClass: 'bg-green-50 text-green-700 border-green-100' },
    { id: '2', candidate: '李娜', email: 'li.na@mail.com', job: 'UI 设计师', date: '2023.10.25', time: '16:00', status: '进行中', statusClass: 'bg-primary/10 text-primary border-primary/10' },
    { id: '3', candidate: '王刚', email: 'wang.gang@mail.com', job: '产品经理', date: '2023.10.26', time: '10:00', status: '待预约', statusClass: 'bg-surface-container-high text-on-surface-variant/60 border-outline-variant/10' },
];
</script>
