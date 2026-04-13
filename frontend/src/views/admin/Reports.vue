<template>
  <div class="max-w-7xl mx-auto">
    <div class="mb-10">
      <span class="text-[10px] font-bold tracking-[0.2em] text-primary uppercase">Analytics Center</span>
      <h1 class="text-3xl font-black text-on-surface">报表统计</h1>
    </div>

    <div class="grid grid-cols-3 gap-8">
      <div v-for="i in 6" :key="i" class="h-64 bg-surface-container-low rounded-3xl border border-outline-variant/10 flex items-center justify-center">
        <span class="text-xs font-bold text-on-surface-variant/40 uppercase tracking-widest">报表图表占位 {{ i }}</span>
      </div>
    </div>
  </div>
</template>
