<template>
  <div class="admin-page">
    <section class="flex flex-wrap items-center justify-between gap-4">
      <button class="admin-quiet-btn" @click="$router.back()">
        <span class="material-symbols-outlined text-[16px]">arrow_back</span>
        返回面试管理
      </button>

      <div class="flex items-center gap-3">
        <button class="admin-quiet-btn">下载报告</button>
        <button class="admin-primary-btn">推进至下一轮</button>
      </div>
    </section>

    <section class="admin-panel px-6 py-5">
      <div class="flex flex-wrap items-start justify-between gap-4">
        <div class="flex items-center gap-4">
          <div class="flex h-16 w-16 items-center justify-center rounded-full bg-[#edf3fb] text-lg font-semibold text-[#62708c]">
            李
          </div>
          <div>
            <p class="text-[22px] font-semibold tracking-tight text-on-surface">李华</p>
            <p class="mt-1 text-[13px] text-on-surface-variant">高级资深后端开发工程师 · 8 年经验 · 上海</p>
            <div class="mt-3 flex flex-wrap gap-2">
              <span class="admin-badge admin-badge-green">强烈推荐</span>
              <span class="admin-badge bg-[#f5f8fd] text-on-surface-variant">技术终面建议</span>
            </div>
          </div>
        </div>

        <div class="grid grid-cols-2 gap-3 sm:grid-cols-3">
          <div class="rounded-[12px] border border-[#eef2f7] bg-[#fafcff] px-4 py-3 text-center">
            <p class="text-[12px] text-on-surface-variant">总体匹配度</p>
            <p class="mt-1 text-[24px] font-semibold text-on-surface">92</p>
          </div>
          <div class="rounded-[12px] border border-[#eef2f7] bg-[#fafcff] px-4 py-3 text-center">
            <p class="text-[12px] text-on-surface-variant">技术专业度</p>
            <p class="mt-1 text-[24px] font-semibold text-on-surface">95</p>
          </div>
          <div class="rounded-[12px] border border-[#eef2f7] bg-[#fafcff] px-4 py-3 text-center">
            <p class="text-[12px] text-on-surface-variant">软素质</p>
            <p class="mt-1 text-[24px] font-semibold text-on-surface">88</p>
          </div>
        </div>
      </div>
    </section>

    <div class="grid grid-cols-12 gap-5">
      <section class="col-span-12 admin-panel px-6 py-5 xl:col-span-7">
        <div class="mb-5 flex items-center justify-between gap-3">
          <h3 class="admin-section-title">面试对话记录</h3>
          <span class="text-[12px] text-on-surface-variant">时长 42 分钟</span>
        </div>

        <div class="space-y-5">
          <article v-for="(turn, idx) in dialogue" :key="idx" class="space-y-3 rounded-[14px] border border-[#eef2f7] bg-[#fafcff] p-4">
            <div class="rounded-[12px] bg-[#eef4ff] px-4 py-3">
              <p class="mb-2 text-[11px] font-semibold text-primary">AI 提问</p>
              <p class="text-[13px] leading-7 text-on-surface">{{ turn.question }}</p>
            </div>
            <div class="rounded-[12px] bg-white px-4 py-3">
              <p class="mb-2 text-[11px] font-semibold text-on-surface-variant">候选人回答</p>
              <p class="text-[13px] leading-7 text-on-surface">{{ turn.answer }}</p>
            </div>
          </article>
        </div>
      </section>

      <aside class="col-span-12 space-y-5 xl:col-span-5">
        <section class="admin-panel px-6 py-5">
          <h3 class="admin-section-title">AI 深度分析</h3>
          <div class="mt-5 space-y-5">
            <div>
              <div class="mb-2 flex items-center justify-between">
                <span class="text-[12px] text-on-surface-variant">技术专业度</span>
                <span class="text-[14px] font-semibold text-primary">95/100</span>
              </div>
              <div class="h-2 w-full overflow-hidden rounded-full bg-surface-container-high">
                <div class="h-full w-[95%] rounded-full bg-primary"></div>
              </div>
              <p class="mt-3 text-[13px] leading-7 text-on-surface-variant">
                展现了较强的分布式架构理解能力，能够结合底层原理解释高并发场景的处理思路。
              </p>
            </div>

            <div>
              <div class="mb-2 flex items-center justify-between">
                <span class="text-[12px] text-on-surface-variant">行为表现 / 软素质</span>
                <span class="text-[14px] font-semibold text-primary">88/100</span>
              </div>
              <div class="h-2 w-full overflow-hidden rounded-full bg-surface-container-high">
                <div class="h-full w-[88%] rounded-full bg-primary"></div>
              </div>
              <div class="mt-3 flex flex-wrap gap-2">
                <span class="admin-badge bg-[#f5f8fd] text-on-surface-variant">理性沟通</span>
                <span class="admin-badge bg-[#f5f8fd] text-on-surface-variant">逻辑严密</span>
                <span class="admin-badge bg-[#f5f8fd] text-on-surface-variant">抗压稳定</span>
              </div>
            </div>
          </div>
        </section>

        <section class="admin-panel px-6 py-5">
          <h3 class="admin-section-title">AI 关键洞察</h3>
          <div class="mt-4 space-y-4">
            <article class="rounded-[12px] bg-[#f8fbff] px-4 py-4">
              <p class="text-[12px] font-semibold text-[#42bc7a]">高确定性</p>
              <p class="mt-1 text-[13px] leading-7 text-on-surface-variant">候选人在描述数据库调优与锁冲突时，细节完整且前后一致。</p>
            </article>
            <article class="rounded-[12px] bg-[#f8fbff] px-4 py-4">
              <p class="text-[12px] font-semibold text-primary">领导潜力</p>
              <p class="mt-1 text-[13px] leading-7 text-on-surface-variant">回答中体现出较强的共识推动能力和架构思维。</p>
            </article>
            <article class="rounded-[12px] bg-[#fff6f3] px-4 py-4">
              <p class="text-[12px] font-semibold text-[#ef6a6a]">潜在风险</p>
              <p class="mt-1 text-[13px] leading-7 text-on-surface-variant">薪资预期高于当前团队平均水平，建议确认预算空间。</p>
            </article>
          </div>
        </section>

        <section class="admin-panel bg-primary px-6 py-5 text-white">
          <div class="flex items-center justify-between gap-4">
            <div>
              <p class="text-[11px] text-white/70">团队文化匹配</p>
              <p class="mt-1 text-[24px] font-semibold">极高</p>
            </div>
            <div class="flex h-12 w-12 items-center justify-center rounded-[14px] bg-white/16">
              <span class="material-symbols-outlined text-[24px]">groups</span>
            </div>
          </div>
        </section>
      </aside>
    </div>
  </div>
</template>

<script setup lang="ts">
const dialogue = [
  {
    question: "请描述您在处理高并发分布式系统时，如何解决数据库死锁问题的具体案例？",
    answer:
      "在之前处理一个每秒 50k QPS 的电商下单系统时，我们遇到了因事务更新顺序不一致导致的间隙锁死锁。我先通过分析 InnoDB Monitor 日志定位加锁链路，然后统一事务的更新顺序，并引入 Redis 预减库存来降低数据库直接竞争。",
  },
  {
    question: "在团队协作中，如果你的架构建议被大多数同事反对，你会如何处理？",
    answer:
      "我会先判断反对意见背后的核心逻辑。如果是信息不充分，我会准备一份数据对比和风险说明；如果是改造成本过高，我会建议做 PoC 验证。我更倾向于通过共识驱动而不是强推方案。",
  },
];
</script>
