<template>
  <div class="min-h-screen bg-background text-on-surface">
    <div
      v-if="workspaceSwitcherOpen"
      class="fixed inset-0 z-40 bg-transparent"
      @click="workspaceSwitcherOpen = false"
    ></div>

    <aside class="fixed inset-y-0 left-0 z-50 flex w-[196px] flex-col border-r border-[#edf2fa] bg-white px-3 py-4">
      <div class="mb-5 flex items-center gap-3 px-2">
        <div class="flex h-9 w-9 items-center justify-center rounded-[12px] bg-[#edf4ff] shadow-[0_12px_24px_-18px_rgba(61,124,255,0.95)]">
          <svg viewBox="0 0 28 28" class="h-5 w-5 text-primary" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M7 20.4V7.6h4.3c3.6 0 5.8 1.7 5.8 4.8 0 3.2-2.2 4.9-5.8 4.9H9.6v3.1" stroke-linecap="round" stroke-linejoin="round" />
            <path d="M19.2 8.1v12" stroke-linecap="round" />
            <path d="M16.6 20.1h5.2" stroke-linecap="round" />
          </svg>
        </div>
        <div class="min-w-0">
          <p class="truncate text-[22px] font-semibold tracking-tight text-on-surface">AI-HR</p>
          <p class="truncate text-[10px] text-[#8b97a8]">智能招聘工作台</p>
        </div>
      </div>

      <nav class="flex-1 space-y-1">
        <router-link
          v-for="item in menuItems"
          :key="item.path"
          :to="item.path"
          class="group flex h-11 items-center gap-3 rounded-[10px] px-3 text-[14px] font-medium transition-all duration-150"
          :class="
            isActive(item.path)
              ? 'bg-[#edf4ff] text-primary shadow-[inset_0_0_0_1px_rgba(61,124,255,0.05)]'
              : 'text-[#667486] hover:bg-[#f6f9fd] hover:text-[#47648f]'
          "
        >
          <span
            class="material-symbols-outlined text-[20px] leading-none"
            :class="{ 'material-fill': isActive(item.path) }"
          >
            {{ item.icon }}
          </span>
          <span class="truncate">{{ item.label }}</span>
          <span
            v-if="item.path === '/admin/settings' && systemAlerts.hasBossCredentialExpired"
            class="ml-auto h-2.5 w-2.5 shrink-0 rounded-full bg-[#ff6767] shadow-[0_0_0_3px_rgba(255,103,103,0.12)]"
          ></span>
        </router-link>
      </nav>

      <div class="relative mt-5 border-t border-[#eef2f7] px-2 pt-4">
        <div
          v-if="workspaceSwitcherOpen"
          class="absolute bottom-[calc(100%+16px)] left-0 right-0 z-[60]"
          @click.stop
        >
          <div class="admin-panel rounded-[18px] px-4 py-4">
            <div class="flex items-center justify-between gap-3">
              <div>
                <p class="text-[11px] font-semibold uppercase tracking-[0.12em] text-primary">Workspace</p>
                <p class="mt-1 text-[15px] font-semibold text-on-surface">切换团队空间</p>
              </div>
              <button
                type="button"
                class="flex h-8 w-8 items-center justify-center rounded-full text-[#7b8798] transition-colors hover:bg-[#f5f8fd] hover:text-primary"
                @click="workspaceSwitcherOpen = false"
              >
                <span class="material-symbols-outlined text-[18px]">close</span>
              </button>
            </div>

            <div class="mt-4 max-h-[240px] space-y-2 overflow-y-auto pr-1">
              <button
                v-for="item in auth.workspaces"
                :key="item.id"
                type="button"
                class="flex w-full items-center justify-between gap-3 rounded-[12px] border px-3 py-3 text-left transition-all"
                :class="
                  item.id === auth.currentWorkspaceId
                    ? 'border-[#d9e7ff] bg-[#f7fbff]'
                    : 'border-[#edf2fa] bg-white hover:border-[#dce8fb] hover:bg-[#fbfdff]'
                "
                :disabled="workspaceActionPending"
                @click="handleWorkspaceSwitch(item.id)"
              >
                <div class="min-w-0">
                  <p class="truncate text-[13px] font-semibold text-on-surface">{{ item.name }}</p>
                  <p class="mt-1 truncate text-[11px] text-on-surface-variant">{{ item.workspace_code }}</p>
                </div>
                <div class="flex items-center gap-2">
                  <span class="admin-badge" :class="workspaceRoleBadgeClass(item.role)">
                    {{ workspaceRoleText(item.role) }}
                  </span>
                  <span
                    v-if="item.id === auth.currentWorkspaceId"
                    class="material-symbols-outlined text-[18px] text-primary"
                  >
                    check_circle
                  </span>
                </div>
              </button>
            </div>

            <form class="mt-4 border-t border-[#eef2f7] pt-4" @submit.prevent="handleCreateWorkspace">
              <label class="admin-label">新建团队空间</label>
              <input
                v-model.trim="newWorkspaceName"
                type="text"
                placeholder="例如：华东招聘团队"
                class="admin-input mt-2"
              >

              <p v-if="workspaceError" class="mt-2 text-[12px] text-[#d25555]">{{ workspaceError }}</p>

              <button
                type="submit"
                class="admin-primary-btn mt-3 w-full"
                :disabled="workspaceActionPending || !newWorkspaceName"
              >
                <span
                  v-if="workspaceActionPending"
                  class="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white"
                ></span>
                {{ workspaceActionPending ? "处理中..." : "创建并切换" }}
              </button>
            </form>

            <router-link
              to="/admin/settings"
              class="mt-3 flex h-9 items-center justify-center rounded-[10px] border border-[#e7edf7] text-[12px] font-semibold text-[#5f6d81] transition-colors hover:border-[#d8e4f8] hover:bg-[#f8fbff] hover:text-primary"
              @click="workspaceSwitcherOpen = false"
            >
              打开组织设置
            </router-link>
          </div>
        </div>

        <button
          type="button"
          class="flex w-full items-center gap-3 rounded-[12px] border border-[#eaf0f8] bg-[#f8fbff] px-3 py-3 text-left transition-colors hover:border-[#dbe7f8] hover:bg-white"
          @click="workspaceSwitcherOpen = !workspaceSwitcherOpen"
        >
          <div class="flex h-9 w-9 items-center justify-center rounded-full bg-white text-[11px] font-semibold text-on-surface shadow-[0_8px_20px_-18px_rgba(31,45,61,0.9)]">
            {{ userInitials }}
          </div>
          <div class="min-w-0 flex-1">
            <p class="truncate text-[12px] font-semibold text-on-surface">{{ displayName }}</p>
            <p class="truncate text-[11px] text-on-surface-variant">{{ workspaceName }}</p>
          </div>
          <span class="material-symbols-outlined text-[18px] text-[#93a0b2]">
            {{ workspaceSwitcherOpen ? "expand_more" : "chevron_right" }}
          </span>
        </button>

        <button
          type="button"
          class="mt-2 flex w-full items-center justify-center gap-2 rounded-[10px] border border-transparent px-3 py-2 text-[12px] font-medium text-[#6d7a8d] transition-colors hover:bg-[#f6f9fd] hover:text-primary"
          @click="handleLogout"
        >
          <span class="material-symbols-outlined text-[17px]">logout</span>
          退出登录
        </button>
      </div>
    </aside>

    <main class="ml-[196px] min-h-screen">
      <header class="glass-panel fixed left-[196px] right-0 top-0 z-40 flex h-16 items-center border-b border-[#edf2fa] px-5">
        <div class="flex w-full items-center gap-5">
          <h1 class="min-w-[88px] text-[16px] font-semibold text-on-surface">{{ pageTitle }}</h1>

          <div class="relative hidden w-[300px] shrink-0 xl:block">
            <span class="pointer-events-none material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-[15px] text-[#b2bccb]">
              search
            </span>
            <input
              type="text"
              placeholder="搜索职位、候选人、面试记录"
              class="admin-input admin-search-input rounded-[10px] border-[#ecf1f8] bg-white pr-3"
            >
          </div>

          <div class="ml-auto flex items-center gap-2">
            <button
              type="button"
              class="relative flex h-9 w-9 items-center justify-center rounded-full text-[#7c889a] transition-colors hover:bg-white hover:text-primary"
            >
              <span class="material-symbols-outlined text-[18px]">notifications</span>
              <span class="absolute right-[8px] top-[8px] h-2 w-2 rounded-full bg-[#ff6767]"></span>
            </button>

            <router-link
              to="/admin/settings"
              class="relative flex h-9 w-9 items-center justify-center rounded-full text-[#7c889a] transition-colors hover:bg-white hover:text-primary"
            >
              <span class="material-symbols-outlined text-[18px]">settings</span>
              <span
                v-if="systemAlerts.hasBossCredentialExpired"
                class="absolute right-[7px] top-[7px] h-2.5 w-2.5 rounded-full bg-[#ff6767] shadow-[0_0_0_3px_rgba(255,103,103,0.12)]"
              ></span>
            </router-link>
          </div>
        </div>
      </header>

      <div class="px-5 pb-8 pt-20">
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
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useAuthStore } from "../stores/auth";
import { useSystemAlertsStore } from "../stores/systemAlerts";

const auth = useAuthStore();
const systemAlerts = useSystemAlertsStore();
const route = useRoute();
const router = useRouter();

const workspaceSwitcherOpen = ref(false);
const workspaceActionPending = ref(false);
const workspaceError = ref("");
const newWorkspaceName = ref("");

const displayName = computed(() => auth.displayName || auth.email || "管理员");
const workspaceName = computed(() => {
  const current = (auth.workspaces || []).find((item) => item.id === auth.currentWorkspaceId);
  return current?.name || "未命名团队";
});
const userInitials = computed(() => {
  const value = String(displayName.value || "").trim();
  return value ? value.slice(0, 2).toUpperCase() : "AI";
});

const menuItems = [
  { label: "首页", path: "/admin", icon: "home" },
  { label: "职位管理", path: "/admin/jobs", icon: "work_outline" },
  { label: "面试管理", path: "/admin/interview-history", icon: "event_note" },
  { label: "录用决策", path: "/admin/hiring", icon: "assignment_turned_in" },
  { label: "AI Agent 工作台", path: "/admin/agents", icon: "smart_toy" },
  { label: "报表中心", path: "/admin/reports", icon: "bar_chart" },
  { label: "设置", path: "/admin/settings", icon: "settings" },
];

const pageTitle = computed(() => {
  const path = route.path;
  if (path === "/admin") return "首页";
  if (path.startsWith("/admin/jobs")) return "职位管理";
  if (path.startsWith("/admin/candidate-detail")) return "候选人详情";
  if (path.startsWith("/admin/candidates")) return "岗位候选人";
  if (path.startsWith("/admin/interview-history")) return "面试管理";
  if (path.startsWith("/admin/interview/")) return "面试详情";
  if (path.startsWith("/admin/hiring")) return "录用决策";
  if (path.startsWith("/admin/agents")) return "AI Agent 工作台";
  if (path.startsWith("/admin/reports")) return "报表中心";
  if (path === "/admin/settings") return "设置总览";
  if (path.startsWith("/admin/settings/org")) return "组织信息";
  if (path.startsWith("/admin/settings/members")) return "团队成员";
  if (path.startsWith("/admin/settings/credentials")) return "平台凭据";
  return "首页";
});

watch(
  () => route.fullPath,
  () => {
    workspaceSwitcherOpen.value = false;
    workspaceError.value = "";
    newWorkspaceName.value = "";
  },
);

watch(
  () => auth.currentWorkspaceId,
  () => {
    void systemAlerts.refreshBossCredentialStatus(true, true);
  },
);

onMounted(() => {
  void systemAlerts.refreshBossCredentialStatus(true, true);
});

function isActive(path: string): boolean {
  if (path === "/admin") {
    return route.path === "/admin";
  }
  return route.path.startsWith(path);
}

function workspaceRoleText(role: string): string {
  if (role === "workspace_owner") return "所有者";
  if (role === "admin") return "管理员";
  if (role === "viewer") return "只读";
  return "招聘成员";
}

function workspaceRoleBadgeClass(role: string): string {
  if (role === "workspace_owner") return "admin-badge-violet";
  if (role === "admin") return "admin-badge-blue";
  if (role === "viewer") return "admin-badge-orange";
  return "admin-badge-green";
}

async function handleWorkspaceSwitch(workspaceId: string): Promise<void> {
  if (workspaceActionPending.value || workspaceId === auth.currentWorkspaceId) {
    workspaceSwitcherOpen.value = false;
    return;
  }

  workspaceActionPending.value = true;
  workspaceError.value = "";
  try {
    await auth.switchWorkspace(workspaceId);
    workspaceSwitcherOpen.value = false;
  } catch (error) {
    workspaceError.value = String((error as { message?: string } | null)?.message || "切换工作区失败");
  } finally {
    workspaceActionPending.value = false;
  }
}

async function handleCreateWorkspace(): Promise<void> {
  const normalized = newWorkspaceName.value.trim();
  if (!normalized || workspaceActionPending.value) {
    return;
  }

  workspaceActionPending.value = true;
  workspaceError.value = "";
  try {
    await auth.createWorkspaceAndSwitch(normalized);
    newWorkspaceName.value = "";
    workspaceSwitcherOpen.value = false;
    if (!route.path.startsWith("/admin/settings")) {
      await router.replace("/admin/settings");
    }
  } catch (error) {
    workspaceError.value = String((error as { message?: string } | null)?.message || "创建工作区失败");
  } finally {
    workspaceActionPending.value = false;
  }
}

async function handleLogout(): Promise<void> {
  workspaceSwitcherOpen.value = false;
  systemAlerts.clearBossCredentialStatus();
  await auth.logoutCurrentUser();
  await router.replace("/login");
}
</script>

<style scoped>
.fade-slide-enter-active,
.fade-slide-leave-active {
  transition: all 0.2s ease;
}

.fade-slide-enter-from {
  opacity: 0;
  transform: translateY(8px);
}

.fade-slide-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}
</style>
