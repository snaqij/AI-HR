<template>
  <div class="flex min-h-screen bg-surface">
    <!-- Sidebar -->
    <aside class="fixed left-0 top-0 h-full w-64 z-50 bg-surface-container-low flex flex-col py-6 px-4 space-y-2 border-r border-outline-variant/10">
      <div class="flex items-center px-4 mb-8 gap-3">
        <div class="w-10 h-10 rounded-full bg-primary-container flex items-center justify-center text-on-primary shadow-sm">
          <span class="material-symbols-outlined material-fill">psychology</span>
        </div>
        <div>
          <h2 class="text-on-surface font-headline font-bold leading-none tracking-tight text-lg">Intelligence</h2>
          <p class="text-on-surface-variant text-xs uppercase tracking-[0.2em] mt-1.5 font-bold">Precision Curator</p>
        </div>
      </div>

      <nav class="flex-1 space-y-1">
        <router-link 
          v-for="item in menuItems" 
          :key="item.path"
          :to="item.path"
          class="flex items-center gap-3 px-4 py-3 rounded-xl transition-all duration-200 group"
          :class="[
            $route.path === item.path 
              ? 'bg-white text-primary font-bold shadow-sm translate-x-1' 
              : 'text-on-surface-variant hover:bg-surface-container-high'
          ]"
        >
          <span class="material-symbols-outlined" :class="{ 'material-fill': $route.path === item.path }">{{ item.icon }}</span>
          <span class="text-sm font-medium">{{ item.label }}</span>
        </router-link>
      </nav>

      <div class="mt-auto p-5 bg-surface-container-high rounded-2xl">
        <div class="flex items-center gap-2 mb-2">
          <div class="w-2 h-2 rounded-full bg-green-500 animate-pulse"></div>
          <span class="text-xs font-bold text-on-surface-variant tracking-wider uppercase">System Online</span>
        </div>
        <p class="text-[13px] text-on-surface-variant leading-relaxed opacity-80 font-medium">AI Agents are currently processing 12 active interviews.</p>
      </div>
    </aside>

    <!-- Main Content -->
    <main class="ml-64 flex-1 flex flex-col min-h-screen">
      <!-- Navbar -->
      <header class="fixed top-0 right-0 left-64 z-40 bg-surface/80 backdrop-blur-md flex justify-between items-center h-16 px-8 border-b border-outline-variant/5">
        <div class="flex items-center gap-6 flex-1">
          <div class="relative w-full max-w-md">
            <span class="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-variant text-xl">search</span>
            <input 
              type="text" 
              placeholder="搜索人才、职位或报告..." 
              class="w-full pl-10 pr-4 py-2 bg-surface-container-low border-none rounded-full text-base focus:ring-2 focus:ring-primary/20 transition-all font-body shadow-inner"
            />
          </div>
        </div>
        
        <div class="flex items-center gap-4">
          <button class="p-2 rounded-full hover:bg-surface-container-high transition-colors relative">
            <span class="material-symbols-outlined text-on-surface-variant">notifications</span>
            <span class="absolute top-2 right-2 w-2 h-2 bg-error rounded-full"></span>
          </button>
          <button class="p-2 rounded-full hover:bg-surface-container-high transition-colors">
            <span class="material-symbols-outlined text-on-surface-variant">settings</span>
          </button>
          <div class="h-8 w-[1px] bg-outline-variant/20 mx-2"></div>
          <div class="flex items-center gap-3">
            <div class="w-8 h-8 rounded-full bg-surface-container-high overflow-hidden border border-outline-variant/10 shadow-sm">
                <img src="https://lh3.googleusercontent.com/aida-public/AB6AXuBfEMX41MlB8WqPmh-WP1qTQq6jifQSnVFYQke84JX9gPWNZBl05Jj4irlpgSvyqrZuasiKtuTE9REvtVKm-6LMReSuqPGUwrr04EZhUWKG5a8v2Qg8XZRvU86UbFsKvtRF0Y8bVO8T_iZXlwm9XrNiQcTCYQnoTnDnbIJcaMBRVlunHg9hRtNGpS3RpDua80XRU5UpAvOcxyAyjv87og1mpQUfLnrJB0wX1DoucXv8yR7Ks9dcsfz091NtU93jywjRs-j9kf_5S9U" alt="Profile" class="w-full h-full object-cover">
            </div>
            <span class="text-sm font-bold text-on-surface">张经理</span>
          </div>
        </div>
      </header>

      <!-- View Content -->
      <div class="mt-16 p-8 flex-1 overflow-x-hidden">
        <router-view v-slot="{ Component }">
          <transition 
            name="fade-slide" 
            mode="out-in"
          >
            <component :is="Component" />
          </transition>
        </router-view>
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
const menuItems = [
  { label: '控制台概览', path: '/admin', icon: 'dashboard' },
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
