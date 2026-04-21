<template>
  <div class="flex min-h-screen bg-surface">
    <aside class="fixed left-0 top-0 z-50 flex h-full w-64 flex-col space-y-2 border-r border-outline-variant/10 bg-surface-container-low px-4 py-6">
      <div class="mb-8 flex items-center gap-3 px-4">
        <div class="flex h-10 w-10 items-center justify-center rounded-full bg-primary-container text-on-primary shadow-sm">
          <span class="material-symbols-outlined material-fill">psychology</span>
        </div>
        <div>
          <h2 class="font-headline text-lg font-bold leading-none tracking-tight text-on-surface">AI-HR</h2>
          <p class="mt-1.5 text-xs font-bold tracking-[0.12em] text-on-surface-variant">智能招聘中枢</p>
        </div>
      </div>

      <nav class="flex-1 space-y-1">
        <router-link
          v-for="item in menuItems"
          :key="item.path"
          :to="item.path"
          class="group flex items-center gap-3 rounded-xl px-4 py-3 transition-all duration-200"
          :class="[
            $route.path === item.path
              ? 'translate-x-1 bg-white font-bold text-primary shadow-sm'
              : 'text-on-surface-variant hover:bg-surface-container-high'
          ]"
        >
          <span class="material-symbols-outlined" :class="{ 'material-fill': $route.path === item.path }">{{ item.icon }}</span>
          <span class="text-sm font-medium">{{ item.label }}</span>
        </router-link>
      </nav>

      <div class="mt-auto rounded-2xl bg-surface-container-high p-5">
        <div class="mb-2 flex items-center gap-2">
          <div class="h-2 w-2 animate-pulse rounded-full bg-green-500"></div>
          <span class="text-xs font-bold tracking-wider text-on-surface-variant">系统在线</span>
        </div>
        <p class="text-[13px] font-medium leading-relaxed text-on-surface-variant opacity-80">AI 智能体当前正在处理 12 场进行中的面试。</p>
      </div>
    </aside>

    <main class="ml-64 flex min-h-screen flex-1 flex-col">
      <header class="fixed left-64 right-0 top-0 z-40 flex h-16 items-center justify-between border-b border-outline-variant/5 bg-surface/80 px-8 backdrop-blur-md">
        <div class="flex flex-1 items-center gap-6">
          <div class="relative w-full max-w-md">
            <span class="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-xl text-on-surface-variant">search</span>
            <input
              type="text"
              placeholder="搜索人才、职位或报告..."
              class="w-full rounded-full border-none bg-surface-container-low py-2 pl-10 pr-4 text-base font-body shadow-inner transition-all focus:ring-2 focus:ring-primary/20"
            />
          </div>
        </div>

        <div class="flex items-center gap-4">
          <router-link
            to="/admin/settings"
            class="hidden items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-bold md:flex"
            :class="credentialBadgeClass"
            :title="credentialTitle"
          >
            <span class="material-symbols-outlined text-base">{{ credentialIcon }}</span>
            <span>{{ credentialText }}</span>
          </router-link>

          <button class="relative rounded-full p-2 transition-colors hover:bg-surface-container-high">
            <span class="material-symbols-outlined text-on-surface-variant">notifications</span>
            <span v-if="isCredentialExpired" class="absolute right-2 top-2 h-2 w-2 rounded-full bg-error"></span>
          </button>

          <router-link to="/admin/settings" class="rounded-full p-2 transition-colors hover:bg-surface-container-high">
            <span class="material-symbols-outlined text-on-surface-variant">settings</span>
          </router-link>

          <div class="mx-2 h-8 w-px bg-outline-variant/20"></div>
          <div class="flex items-center gap-3">
            <div class="h-8 w-8 overflow-hidden rounded-full border border-outline-variant/10 bg-surface-container-high shadow-sm">
              <img
                src="https://lh3.googleusercontent.com/aida-public/AB6AXuBfEMX41MlB8WqPmh-WP1qTQq6jifQSnVFYQke84JX9gPWNZBl05Jj4irlpgSvyqrZuasiKtuTE9REvtVKm-6LMReSuqPGUwrr04EZhUWKG5a8v2Qg8XZRvU86UbFsKvtRF0Y8bVO8T_iZXlwm9XrNiQcTCYQnoTnDnbIJcaMBRVlunHg9hRtNGpS3RpDua80XRU5UpAvOcxyAyjv87og1mpQUfLnrJB0wX1DoucXv8yR7Ks9dcsfz091NtU93jywjRs-j9kf_5S9U"
                alt="Profile"
                class="h-full w-full object-cover"
              >
            </div>
            <span class="text-sm font-bold text-on-surface">张经理</span>
          </div>
        </div>
      </header>

      <div class="mt-16 flex-1 overflow-x-hidden p-8">
        <router-view v-slot="{ Component }">
          <transition name="fade-slide" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue';
import { fetchBossCredential, type CredentialStatus } from '../api';

const credential = ref<CredentialStatus | null>(null);
const credentialFetchFailed = ref(false);
let refreshTimer: number | null = null;

const isCredentialExpired = computed(() => credential.value?.status === 'expired');

const credentialText = computed(() => {
  if (credentialFetchFailed.value) {
    return '凭证状态未知';
  }
  if (!credential.value) {
    return 'Boss凭证未配置';
  }
  if (credential.value.status === 'expired') {
    return 'Boss凭证已过期';
  }
  return 'Boss凭证正常';
});

const credentialIcon = computed(() => {
  if (credentialFetchFailed.value) {
    return 'help';
  }
  if (!credential.value) {
    return 'key_off';
  }
  return credential.value.status === 'expired' ? 'warning' : 'verified';
});

const credentialBadgeClass = computed(() => {
  if (credentialFetchFailed.value) {
    return 'border-outline-variant/40 bg-surface-container-low text-on-surface-variant';
  }
  if (!credential.value) {
    return 'border-outline-variant/30 bg-surface-container-low text-on-surface-variant';
  }
  if (credential.value.status === 'expired') {
    return 'border-rose-200 bg-rose-50 text-rose-700';
  }
  return 'border-emerald-200 bg-emerald-50 text-emerald-700';
});

const credentialTitle = computed(() => {
  if (!credential.value) {
    return '未检测到有效 Boss 凭证，请前往系统设置配置';
  }
  if (credential.value.status === 'expired') {
    return 'Boss Cookie 已失效，请前往系统设置更新';
  }
  return 'Boss 凭证状态正常';
});

async function loadCredentialStatus(): Promise<void> {
  try {
    const data = await fetchBossCredential();
    credential.value = data;
    credentialFetchFailed.value = false;
  } catch (err) {
    const message = String(err ?? '');
    if (message.includes('HTTP 404')) {
      credential.value = null;
      credentialFetchFailed.value = false;
      return;
    }
    credentialFetchFailed.value = true;
    console.error('Failed to fetch boss credentials', err);
  }
}

onMounted(async () => {
  await loadCredentialStatus();
  refreshTimer = window.setInterval(loadCredentialStatus, 60 * 1000);
});

onUnmounted(() => {
  if (refreshTimer) {
    window.clearInterval(refreshTimer);
  }
});

const menuItems = [
  { label: '控制台概览', path: '/admin', icon: 'dashboard' },
  { label: 'Agent 运行中心', path: '/admin/agents', icon: 'support_agent' },
  { label: '职位管理', path: '/admin/jobs', icon: 'work' },
  { label: '面试邀请记录', path: '/admin/interview-history', icon: 'event' },
  { label: '录用决策中心', path: '/admin/hiring', icon: 'person_add' },
  { label: '报表统计', path: '/admin/reports', icon: 'assessment' },
  { label: '系统设置', path: '/admin/settings', icon: 'settings' },
];
</script>

<style scoped>
.fade-slide-enter-active,
.fade-slide-leave-active {
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.fade-slide-enter-from {
  opacity: 0;
  transform: translateY(10px);
}

.fade-slide-leave-to {
  opacity: 0;
  transform: translateY(-10px);
}
</style>
