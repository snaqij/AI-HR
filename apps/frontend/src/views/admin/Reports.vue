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
        <div v-if="loading" class="mt-6 flex items-center justify-center h-[200px]">
          <p class="text-on-surface-variant">加载中...</p>
        </div>
        <div v-else class="mt-6 grid grid-cols-6 gap-3">
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
        <div v-if="loading" class="mt-5 flex items-center justify-center h-[200px]">
          <p class="text-on-surface-variant">加载中...</p>
        </div>
        <div v-else class="mt-5 space-y-4">
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
import { ref, onMounted } from 'vue'
import { fetchDashboardStatistics, fetchRecruitmentTrends, fetchChannelPerformance } from '../../api'

interface StatCard {
  label: string
  value: string
  delta: string
  deltaClass: string
}

interface TrendBar {
  label: string
  value: string
  height: number
}

interface ChannelCard {
  label: string
  rate: string
  rateClass: string
  desc: string
}

const loading = ref(true)
const statCards = ref<StatCard[]>([])
const trendBars = ref<TrendBar[]>([])
const channelCards = ref<ChannelCard[]>([])

// 获取仪表板统计数据
async function fetchDashboardStats() {
  try {
    const data = await fetchDashboardStatistics()
    
    // 更新统计卡片
    statCards.value = [
      {
        label: '职位总数',
        value: String(data.job_count.total),
        delta: data.job_count.delta_text,
        deltaClass: data.job_count.delta >= 0 ? 'text-[#44bc7d]' : 'text-error'
      },
      {
        label: '候选人总数',
        value: String(data.candidate_count.total).replace(/\B(?=(\d{3})+(?!\d))/g, ','),
        delta: data.candidate_count.delta_text,
        deltaClass: data.candidate_count.delta >= 0 ? 'text-[#44bc7d]' : 'text-error'
      },
      {
        label: '面试完成',
        value: String(data.interview_completed.total),
        delta: data.interview_completed.delta_text,
        deltaClass: data.interview_completed.delta >= 0 ? 'text-[#44bc7d]' : 'text-error'
      },
      {
        label: '录用转化率',
        value: `${data.hire_rate.rate}%`,
        delta: data.hire_rate.delta_text,
        deltaClass: data.hire_rate.delta >= 0 ? 'text-primary' : 'text-error'
      }
    ]
  } catch (error) {
    console.error('获取仪表板统计失败:', error)
    // 使用默认值
    statCards.value = [
      { label: '职位总数', value: '0', delta: '较上周 +0', deltaClass: 'text-[#44bc7d]' },
      { label: '候选人总数', value: '0', delta: '较上周 +0', deltaClass: 'text-[#44bc7d]' },
      { label: '面试完成', value: '0', delta: '较上周 +0', deltaClass: 'text-[#44bc7d]' },
      { label: '录用转化率', value: '0%', delta: '较上周 +0%', deltaClass: 'text-primary' }
    ]
  }
}

// 获取招聘趋势数据
async function fetchTrends() {
  try {
    const data = await fetchRecruitmentTrends(6)
    const trends = data.trends
    
    // 计算最大值用于归一化高度
    const maxValue = Math.max(...trends.map(t => t.value), 1)
    
    // 更新趋势柱状图
    trendBars.value = trends.map(trend => ({
      label: trend.label,
      value: String(trend.value),
      height: Math.max((trend.value / maxValue) * 146, 20) // 最小高度 20px，最大 146px
    }))
  } catch (error) {
    console.error('获取趋势数据失败:', error)
    // 使用默认值
    trendBars.value = [
      { label: '周一', value: '0', height: 20 },
      { label: '周二', value: '0', height: 20 },
      { label: '周三', value: '0', height: 20 },
      { label: '周四', value: '0', height: 20 },
      { label: '周五', value: '0', height: 20 },
      { label: '周六', value: '0', height: 20 }
    ]
  }
}

// 获取渠道表现数据
async function fetchChannels() {
  try {
    const data = await fetchChannelPerformance()
    const channels = data.channels
    
    // 更新渠道卡片
    channelCards.value = channels.map(channel => {
      // 根据转化率设置颜色
      let rateClass = 'text-primary'
      if (channel.rate >= 35) {
        rateClass = 'text-[#19a9a8]'
      } else if (channel.rate >= 25) {
        rateClass = 'text-[#44bc7d]'
      }
      
      return {
        label: channel.label,
        rate: channel.rate_text,
        rateClass,
        desc: channel.desc
      }
    })
    
    // 如果没有渠道数据，使用默认值
    if (channelCards.value.length === 0) {
      channelCards.value = [
        {
          label: 'BOSS 直聘',
          rate: '转化率 0%',
          rateClass: 'text-primary',
          desc: '暂无数据'
        }
      ]
    }
  } catch (error) {
    console.error('获取渠道数据失败:', error)
    // 使用默认值
    channelCards.value = [
      {
        label: 'BOSS 直聘',
        rate: '转化率 0%',
        rateClass: 'text-primary',
        desc: '暂无数据'
      }
    ]
  }
}

// 加载所有数据
async function loadData() {
  loading.value = true
  try {
    await Promise.all([
      fetchDashboardStats(),
      fetchTrends(),
      fetchChannels()
    ])
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadData()
})
</script>
