<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { getWorkspaceDetail, type WorkspaceDetail } from "../../api";
import { useAuthStore } from "../../stores/auth";
import { useSystemAlertsStore } from "../../stores/systemAlerts";

const auth = useAuthStore();
const systemAlerts = useSystemAlertsStore();

const detail = ref<WorkspaceDetail | null>(null);
const loading = ref(false);
const error = ref("");

const workspaceId = computed(() => auth.currentWorkspaceId || "");
const currentWorkspace = computed(() => {
  return auth.workspaces.find((item) => item.id === workspaceId.value) || null;
});

const cards = computed(() => [
  {
    title: "组织信息",
    description: "维护团队名称、编码、负责人和套餐信息。",
    value: detail.value?.name || currentWorkspace.value?.name || "未命名团队",
    meta: detail.value ? `${detail.value.workspace_code} · ${detail.value.plan_code.toUpperCase()}` : "基础资料",
    to: "/admin/settings/org",
    icon: "apartment",
    iconWrapClass: "bg-[#eef4ff] text-primary",
  },
  {
    title: "团队成员",
    description: "查看成员角色、加入时间，并管理团队权限。",
    value: `${detail.value?.member_count || 0} 人`,
    meta: roleText(detail.value?.role || currentWorkspace.value?.role || ""),
    to: "/admin/settings/members",
    icon: "group",
    iconWrapClass: "bg-[#e9f8ef] text-[#42bc7a]",
  },
  {
    title: "平台凭据",
    description: "管理 BOSS 等平台同步凭据与连接状态。",
    value: systemAlerts.hasBossCredentialExpired ? "待更新" : "BOSS 凭据",
    meta: systemAlerts.hasBossCredentialExpired ? "BOSS 凭据失效，需立即更新" : "渠道接入",
    to: "/admin/settings/credentials",
    icon: "key",
    iconWrapClass: "bg-[#fff4e8] text-[#f5a24a]",
    attention: systemAlerts.hasBossCredentialExpired,
  },
]);

onMounted(() => {
  void loadData();
});

watch(workspaceId, () => {
  void loadData();
});

async function loadData(): Promise<void> {
  if (!workspaceId.value) {
    detail.value = null;
    return;
  }

  loading.value = true;
  error.value = "";
  try {
    detail.value = await getWorkspaceDetail(workspaceId.value);
  } catch (err) {
    error.value = String((err as { message?: string } | null)?.message || "加载设置数据失败");
  } finally {
    loading.value = false;
  }
}

function roleText(role: string): string {
  if (role === "workspace_owner") return "当前角色：所有者";
  if (role === "admin") return "当前角色：管理员";
  if (role === "viewer") return "当前角色：只读成员";
  if (role) return "当前角色：招聘成员";
  return "等待同步";
}

function formatDate(value?: string | null): string {
  if (!value) {
    return "--";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(date);
}
</script>

<template>
  <div class="admin-page">
    <section v-if="loading" class="admin-panel px-8 py-16 text-center">
      <div class="mx-auto h-10 w-10 animate-spin rounded-full border-4 border-primary/20 border-t-primary"></div>
      <p class="mt-4 text-sm text-on-surface-variant">正在加载设置数据...</p>
    </section>

    <section v-else-if="error" class="admin-panel px-8 py-12 text-center">
      <p class="text-sm font-semibold text-on-error-container">{{ error }}</p>
      <button class="admin-primary-btn mt-5" @click="loadData">重新加载</button>
    </section>

    <template v-else>
      <section class="grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,1.55fr)_320px]">
        <article class="admin-panel px-6 py-6">
          <div class="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <p class="admin-kicker">Workspace Overview</p>
              <p class="mt-3 text-[24px] font-semibold tracking-tight text-on-surface">
                {{ detail?.name || currentWorkspace?.name || "未命名团队" }}
              </p>
              <p class="mt-2 text-[13px] leading-6 text-on-surface-variant">
                这里集中管理组织资料、团队成员和平台凭据。先统一工作区设置，再逐步补齐企业级协作能力。
              </p>
            </div>

            <router-link to="/admin/settings/org" class="admin-primary-btn">
              <span class="material-symbols-outlined text-[17px]">edit</span>
              编辑组织信息
            </router-link>
          </div>

          <div class="mt-6 grid grid-cols-1 gap-4 md:grid-cols-3">
            <div class="rounded-[14px] border border-[#e8eef7] bg-[#f8fbff] px-4 py-4">
              <p class="text-[12px] text-on-surface-variant">工作区编码</p>
              <p class="mt-2 text-[15px] font-semibold text-on-surface">{{ detail?.workspace_code || "--" }}</p>
            </div>
            <div class="rounded-[14px] border border-[#e8eef7] bg-[#f8fbff] px-4 py-4">
              <p class="text-[12px] text-on-surface-variant">团队成员</p>
              <p class="mt-2 text-[15px] font-semibold text-on-surface">{{ detail?.member_count || 0 }} 人</p>
            </div>
            <div class="rounded-[14px] border border-[#e8eef7] bg-[#f8fbff] px-4 py-4">
              <p class="text-[12px] text-on-surface-variant">创建时间</p>
              <p class="mt-2 text-[15px] font-semibold text-on-surface">{{ formatDate(detail?.created_at) }}</p>
            </div>
          </div>

          <div class="mt-6 grid grid-cols-1 gap-4 xl:grid-cols-3">
            <router-link
              v-for="card in cards"
              :key="card.title"
              :to="card.to"
              class="group rounded-[16px] border border-[#e7edf7] bg-white px-5 py-5 transition-all hover:-translate-y-[1px] hover:border-[#d8e4f8] hover:shadow-[0_16px_34px_-30px_rgba(61,124,255,0.55)]"
            >
              <div class="flex items-start justify-between gap-4">
                <div class="min-w-0 flex-1">
                  <p class="text-[14px] font-semibold text-on-surface">{{ card.title }}</p>
                  <p class="mt-2 text-[12px] leading-6 text-on-surface-variant">{{ card.description }}</p>
                </div>
                <div class="flex h-10 w-10 items-center justify-center rounded-[12px]" :class="card.iconWrapClass">
                  <span class="material-symbols-outlined text-[18px]">{{ card.icon }}</span>
                </div>
              </div>

              <div class="mt-6">
                <div class="flex items-center gap-2">
                  <p class="truncate text-[18px] font-semibold tracking-tight text-on-surface">{{ card.value }}</p>
                  <span v-if="card.attention" class="admin-badge admin-badge-red">需更新</span>
                </div>
                <p class="mt-2 text-[12px] text-on-surface-variant">{{ card.meta }}</p>
              </div>

              <div class="mt-5 flex items-center gap-2 text-[12px] font-semibold text-primary">
                进入设置
                <span class="material-symbols-outlined text-[16px] transition-transform group-hover:translate-x-0.5">arrow_forward</span>
              </div>
            </router-link>
          </div>
        </article>

        <aside class="space-y-5">
          <article class="admin-panel px-5 py-5">
            <p class="admin-section-title">当前组织资料</p>
            <div class="mt-4 space-y-3">
              <div class="rounded-[12px] bg-[#f8fbff] px-4 py-3">
                <p class="text-[12px] text-on-surface-variant">负责人</p>
                <p class="mt-1 text-[13px] font-semibold text-on-surface">
                  {{ detail?.owner_display_name || "未设置" }}
                </p>
                <p class="mt-1 text-[12px] text-on-surface-variant">{{ detail?.owner_email || "--" }}</p>
              </div>

              <div class="rounded-[12px] bg-[#f8fbff] px-4 py-3">
                <p class="text-[12px] text-on-surface-variant">当前身份</p>
                <p class="mt-1 text-[13px] font-semibold text-on-surface">{{ roleText(detail?.role || currentWorkspace?.role || "") }}</p>
              </div>

              <div class="rounded-[12px] bg-[#f8fbff] px-4 py-3">
                <p class="text-[12px] text-on-surface-variant">套餐版本</p>
                <p class="mt-1 text-[13px] font-semibold uppercase text-on-surface">{{ detail?.plan_code || "--" }}</p>
              </div>
            </div>
          </article>

          <article class="admin-panel px-5 py-5">
            <p class="admin-section-title">下一步建议</p>
            <div class="mt-4 space-y-3">
              <div class="rounded-[12px] border border-[#e7edf7] bg-white px-4 py-3">
                <p class="text-[13px] font-semibold text-on-surface">先统一组织资料</p>
                <p class="mt-1 text-[12px] leading-6 text-on-surface-variant">
                  保持工作区命名规范，便于后续多团队切换和权限治理。
                </p>
              </div>
              <div class="rounded-[12px] border border-[#e7edf7] bg-white px-4 py-3">
                <p class="text-[13px] font-semibold text-on-surface">再配置团队成员</p>
                <p class="mt-1 text-[12px] leading-6 text-on-surface-variant">
                  所有者可添加已注册成员，并分配管理员、招聘成员或只读角色。
                </p>
              </div>
            </div>
          </article>
        </aside>
      </section>
    </template>
  </div>
</template>
