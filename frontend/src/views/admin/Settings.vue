<template>
  <div class="max-w-7xl mx-auto">
    <div class="mb-10">
      <span class="text-[10px] font-bold tracking-[0.2em] text-primary uppercase">Configuration</span>
      <h1 class="text-3xl font-black text-on-surface">系统设置</h1>
    </div>

    <div class="bg-surface-container-lowest rounded-3xl p-8 border border-outline-variant/10 shadow-sm max-w-2xl">
      <div class="space-y-8">
        <div v-for="section in ['常规设置', 'AI 配置', '通知设置', '团队权限']" :key="section" class="border-b border-outline-variant/5 pb-8">
           <h3 class="font-black text-sm text-on-surface mb-4">{{ section }}</h3>
           <div class="flex items-center justify-between p-4 bg-surface rounded-xl border border-outline-variant/5">
              <span class="text-xs font-bold text-on-surface-variant">演示设置项</span>
              <div class="w-10 h-5 bg-primary rounded-full relative">
                <div class="absolute right-1 top-1 w-3 h-3 bg-white rounded-full"></div>
              </div>
           </div>
        </div>
      </div>
    </div>
  </div>
</template>
