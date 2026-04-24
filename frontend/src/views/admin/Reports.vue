<template>
  <div class="admin-page">
    <section class="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
      <article v-for="card in statCards" :key="card.label" class="admin-panel px-5 py-5">
        <p class="text-[12px] text-on-surface-variant">{{ card.label }}</p>
        <p class="mt-2 text-[30px] font-bold tracking-tight text-on-surface">{{ card.value }}</p>
        <p class="mt-2 text-[12px]" :class="card.deltaClass">{{ card.delta }}</p>
      </article>
    </section>

    <section class="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1.5fr)_minmax(320px,1fr)]">
      <article class="admin-panel px-6 py-5">
        <div class="flex items-center justify-between">
          <h2 class="admin-section-title">招聘趋势概览</h2>
          <span class="admin-badge admin-badge-blue">近 30 天</span>
        </div>
        <div class="mt-6 grid grid-cols-6 gap-3">
          <div
            v-for="item in trendBars"
            :key="item.label"
            class="flex flex-col items-center gap-3 rounded-[16px] bg-[#f8fbff] px-3 py-4"
          >
            <div class="flex h-[160px] items-end">
              <div class="w-7 rounded-t-[10px] bg-[#c9dcff]" :style="{ height: `${item.height}px` }"></div>
            </div>
            <div class="text-center">
              <p class="text-[13px] font-semibold text-on-surface">{{ item.value }}</p>
              <p class="mt-1 text-[12px] text-on-surface-variant">{{ item.label }}</p>
            </div>
          </div>
        </div>
      </article>

      <article class="admin-panel px-6 py-5">
        <div class="flex items-center justify-between">
          <h2 class="admin-section-title">渠道表现</h2>
          <span class="text-[12px] text-on-surface-variant">本周数据</span>
        </div>
        <div class="mt-5 space-y-4">
          <div v-for="item in channelCards" :key="item.label" class="rounded-[16px] bg-[#f8fbff] px-4 py-4">
            <div class="flex items-center justify-between">
              <p class="text-[14px] font-semibold text-on-surface">{{ item.label }}</p>
              <span class="text-[13px] font-semibold" :class="item.rateClass">{{ item.rate }}</span>
            </div>
            <p class="mt-2 text-[13px] text-on-surface-variant">{{ item.desc }}</p>
          </div>
        </div>
      </article>
    </section>
  </div>
</template>

<script setup lang="ts">
const statCards = [
  { label: "职位总数", value: "32", delta: "较上周 +4", deltaClass: "text-[#44bc7d]" },
  { label: "候选人总数", value: "1,268", delta: "较上周 +86", deltaClass: "text-[#44bc7d]" },
  { label: "面试完成", value: "128", delta: "较上周 +11", deltaClass: "text-[#44bc7d]" },
  { label: "录用转化率", value: "18.3%", delta: "较上周 +2.4%", deltaClass: "text-primary" },
];

const trendBars = [
  { label: "周一", value: "122", height: 92 },
  { label: "周二", value: "148", height: 124 },
  { label: "周三", value: "130", height: 110 },
  { label: "周四", value: "168", height: 146 },
  { label: "周五", value: "142", height: 120 },
  { label: "周六", value: "95", height: 74 },
];

const channelCards = [
  { label: "BOSS 直聘", rate: "转化率 32%", rateClass: "text-primary", desc: "投递量持续增长，技术岗位的候选人质量稳定。" },
  { label: "猎聘", rate: "转化率 24%", rateClass: "text-[#44bc7d]", desc: "高年限岗位表现较优，建议继续保留预算。" },
  { label: "内推渠道", rate: "转化率 41%", rateClass: "text-[#19a9a8]", desc: "质量最高，适合重点岗位优先曝光与跟进。" },
];
</script>
