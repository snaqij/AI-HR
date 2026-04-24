<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { getWorkspaceDetail, updateWorkspace, type WorkspaceDetail } from "../../api";
import { useAuthStore } from "../../stores/auth";

const auth = useAuthStore();

const detail = ref<WorkspaceDetail | null>(null);
const workspaceName = ref("");
const loading = ref(false);
const saving = ref(false);
const error = ref("");
const message = ref<{ type: "success" | "error" | ""; text: string }>({ type: "", text: "" });

const workspaceId = computed(() => auth.currentWorkspaceId || "");
const canEdit = computed(() => detail.value?.role === "workspace_owner");

onMounted(() => {
  void loadData();
});

watch(workspaceId, () => {
  void loadData();
});

async function loadData(): Promise<void> {
  if (!workspaceId.value) {
    detail.value = null;
    workspaceName.value = "";
    return;
  }

  loading.value = true;
  error.value = "";
  message.value = { type: "", text: "" };
  try {
    const response = await getWorkspaceDetail(workspaceId.value);
    detail.value = response;
    workspaceName.value = response.name;
  } catch (err) {
    error.value = String((err as { message?: string } | null)?.message || "加载组织信息失败");
  } finally {
    loading.value = false;
  }
}

async function handleSave(): Promise<void> {
  if (!detail.value || !workspaceId.value || !canEdit.value) {
    return;
  }

  const normalized = workspaceName.value.trim();
  if (!normalized) {
    message.value = { type: "error", text: "请输入组织名称" };
    return;
  }

  saving.value = true;
  message.value = { type: "", text: "" };
  try {
    detail.value = await updateWorkspace(workspaceId.value, { name: normalized });
    workspaceName.value = detail.value.name;
    await auth.reloadProfile();
    message.value = { type: "success", text: "组织信息已更新" };
  } catch (err) {
    message.value = { type: "error", text: String((err as { message?: string } | null)?.message || "保存失败") };
  } finally {
    saving.value = false;
  }
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

function roleText(role?: string): string {
  if (role === "workspace_owner") return "所有者";
  if (role === "admin") return "管理员";
  if (role === "viewer") return "只读成员";
  return "招聘成员";
}
</script>

<template>
  <div class="admin-page">
    <section v-if="loading" class="admin-panel px-8 py-16 text-center">
      <div class="mx-auto h-10 w-10 animate-spin rounded-full border-4 border-primary/20 border-t-primary"></div>
      <p class="mt-4 text-sm text-on-surface-variant">正在加载组织信息...</p>
    </section>

    <section v-else-if="error" class="admin-panel px-8 py-12 text-center">
      <p class="text-sm font-semibold text-on-error-container">{{ error }}</p>
      <button class="admin-primary-btn mt-5" @click="loadData">重新加载</button>
    </section>

    <section v-else class="grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,1.55fr)_320px]">
      <article class="admin-panel px-6 py-6">
        <div class="flex items-start justify-between gap-4">
          <div>
            <p class="admin-kicker">Organization Profile</p>
            <p class="mt-3 text-[22px] font-semibold tracking-tight text-on-surface">维护组织基础信息</p>
            <p class="mt-2 text-[13px] leading-6 text-on-surface-variant">
              当前工作区的名称、负责人和套餐信息会影响全局设置识别。建议先统一命名，再进行多团队协作。
            </p>
          </div>

          <span class="admin-badge" :class="canEdit ? 'admin-badge-violet' : 'admin-badge-blue'">
            {{ canEdit ? "可编辑" : "只读" }}
          </span>
        </div>

        <div class="mt-6 grid grid-cols-1 gap-5 lg:grid-cols-2">
          <div>
            <label class="admin-label">组织名称</label>
            <input
              v-model.trim="workspaceName"
              type="text"
              class="admin-input mt-2"
              placeholder="请输入组织名称"
              :disabled="!canEdit"
            >
          </div>

          <div>
            <label class="admin-label">工作区编码</label>
            <input :value="detail?.workspace_code || '--'" type="text" class="admin-input mt-2 bg-[#f8fbff]" disabled>
          </div>

          <div>
            <label class="admin-label">负责人</label>
            <input :value="detail?.owner_display_name || '--'" type="text" class="admin-input mt-2 bg-[#f8fbff]" disabled>
          </div>

          <div>
            <label class="admin-label">负责人邮箱</label>
            <input :value="detail?.owner_email || '--'" type="text" class="admin-input mt-2 bg-[#f8fbff]" disabled>
          </div>
        </div>

        <div
          v-if="message.text"
          class="mt-5 rounded-[14px] px-4 py-3 text-[13px] font-medium"
          :class="message.type === 'success' ? 'bg-[#e9f8ef] text-[#42bc7a]' : 'bg-[#fff1ef] text-[#cb4a4a]'"
        >
          {{ message.text }}
        </div>

        <div class="mt-6 flex justify-end">
          <button class="admin-primary-btn" :disabled="saving || !canEdit" @click="handleSave">
            <span v-if="saving" class="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white"></span>
            {{ saving ? "保存中..." : "保存组织信息" }}
          </button>
        </div>
      </article>

      <aside class="space-y-5">
        <article class="admin-panel px-5 py-5">
          <p class="admin-section-title">工作区概览</p>
          <div class="mt-4 space-y-3">
            <div class="rounded-[12px] bg-[#f8fbff] px-4 py-3">
              <p class="text-[12px] text-on-surface-variant">当前角色</p>
              <p class="mt-1 text-[13px] font-semibold text-on-surface">{{ roleText(detail?.role) }}</p>
            </div>
            <div class="rounded-[12px] bg-[#f8fbff] px-4 py-3">
              <p class="text-[12px] text-on-surface-variant">套餐版本</p>
              <p class="mt-1 text-[13px] font-semibold uppercase text-on-surface">{{ detail?.plan_code || "--" }}</p>
            </div>
            <div class="rounded-[12px] bg-[#f8fbff] px-4 py-3">
              <p class="text-[12px] text-on-surface-variant">团队规模</p>
              <p class="mt-1 text-[13px] font-semibold text-on-surface">{{ detail?.member_count || 0 }} 人</p>
            </div>
            <div class="rounded-[12px] bg-[#f8fbff] px-4 py-3">
              <p class="text-[12px] text-on-surface-variant">创建时间</p>
              <p class="mt-1 text-[13px] font-semibold text-on-surface">{{ formatDate(detail?.created_at) }}</p>
            </div>
          </div>
        </article>

        <article class="admin-panel px-5 py-5">
          <p class="admin-section-title">权限说明</p>
          <p class="mt-3 text-[13px] leading-7 text-on-surface-variant">
            当前仅工作区所有者可以修改组织名称和成员角色。管理员与招聘成员可继续使用业务功能，但不修改团队主配置。
          </p>
        </article>
      </aside>
    </section>
  </div>
</template>
