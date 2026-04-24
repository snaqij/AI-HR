<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import {
  inviteWorkspaceMember,
  listWorkspaceMembers,
  removeWorkspaceMember,
  updateWorkspaceMember,
  type WorkspaceMember,
} from "../../api";
import { useAuthStore } from "../../stores/auth";

const auth = useAuthStore();

const members = ref<WorkspaceMember[]>([]);
const loading = ref(false);
const error = ref("");
const inviteEmail = ref("");
const inviteRole = ref("recruiter");
const inviteSaving = ref(false);
const roleDrafts = ref<Record<string, string>>({});
const savingMemberId = ref("");
const removingMemberId = ref("");
const message = ref<{ type: "success" | "error" | ""; text: string }>({ type: "", text: "" });

const workspaceId = computed(() => auth.currentWorkspaceId || "");
const currentWorkspace = computed(() => {
  return auth.workspaces.find((item) => item.id === workspaceId.value) || null;
});
const canManage = computed(() => currentWorkspace.value?.role === "workspace_owner");

onMounted(() => {
  void loadData();
});

watch(workspaceId, () => {
  void loadData();
});

async function loadData(): Promise<void> {
  if (!workspaceId.value) {
    members.value = [];
    roleDrafts.value = {};
    return;
  }

  loading.value = true;
  error.value = "";
  message.value = { type: "", text: "" };
  try {
    const response = await listWorkspaceMembers(workspaceId.value);
    members.value = response.items || [];
    roleDrafts.value = Object.fromEntries(members.value.map((item) => [item.id, item.role]));
  } catch (err) {
    error.value = String((err as { message?: string } | null)?.message || "加载团队成员失败");
  } finally {
    loading.value = false;
  }
}

async function handleInvite(): Promise<void> {
  if (!workspaceId.value || !canManage.value || inviteSaving.value) {
    return;
  }

  const email = inviteEmail.value.trim();
  if (!email) {
    message.value = { type: "error", text: "请输入成员邮箱" };
    return;
  }

  inviteSaving.value = true;
  message.value = { type: "", text: "" };
  try {
    await inviteWorkspaceMember(workspaceId.value, {
      email,
      role: inviteRole.value,
    });
    inviteEmail.value = "";
    inviteRole.value = "recruiter";
    message.value = { type: "success", text: "成员已加入当前工作区" };
    await loadData();
  } catch (err) {
    message.value = { type: "error", text: String((err as { message?: string } | null)?.message || "添加成员失败") };
  } finally {
    inviteSaving.value = false;
  }
}

async function handleSaveRole(member: WorkspaceMember): Promise<void> {
  if (!workspaceId.value || !canManage.value || member.is_current_user) {
    return;
  }

  const nextRole = roleDrafts.value[member.id] || member.role;
  if (nextRole === member.role) {
    return;
  }

  savingMemberId.value = member.id;
  message.value = { type: "", text: "" };
  try {
    await updateWorkspaceMember(workspaceId.value, member.id, { role: nextRole });
    message.value = { type: "success", text: `${member.display_name} 的角色已更新` };
    await loadData();
  } catch (err) {
    message.value = { type: "error", text: String((err as { message?: string } | null)?.message || "更新角色失败") };
  } finally {
    savingMemberId.value = "";
  }
}

async function handleRemove(member: WorkspaceMember): Promise<void> {
  if (!workspaceId.value || !canManage.value || member.is_current_user || removingMemberId.value) {
    return;
  }

  const confirmed = window.confirm(`确认将 ${member.display_name} 移出当前工作区吗？`);
  if (!confirmed) {
    return;
  }

  removingMemberId.value = member.id;
  message.value = { type: "", text: "" };
  try {
    await removeWorkspaceMember(workspaceId.value, member.id);
    message.value = { type: "success", text: `${member.display_name} 已移出团队` };
    await loadData();
  } catch (err) {
    message.value = { type: "error", text: String((err as { message?: string } | null)?.message || "移除成员失败") };
  } finally {
    removingMemberId.value = "";
  }
}

function roleText(role: string): string {
  if (role === "workspace_owner") return "所有者";
  if (role === "admin") return "管理员";
  if (role === "viewer") return "只读";
  return "招聘成员";
}

function roleBadgeClass(role: string): string {
  if (role === "workspace_owner") return "admin-badge-violet";
  if (role === "admin") return "admin-badge-blue";
  if (role === "viewer") return "admin-badge-orange";
  return "admin-badge-green";
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
      <p class="mt-4 text-sm text-on-surface-variant">正在加载团队成员...</p>
    </section>

    <section v-else-if="error" class="admin-panel px-8 py-12 text-center">
      <p class="text-sm font-semibold text-on-error-container">{{ error }}</p>
      <button class="admin-primary-btn mt-5" @click="loadData">重新加载</button>
    </section>

    <section v-else class="grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,1.6fr)_340px]">
      <article class="admin-panel px-6 py-6">
        <div class="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p class="admin-kicker">Team Members</p>
            <p class="mt-3 text-[22px] font-semibold tracking-tight text-on-surface">
              {{ currentWorkspace?.name || "当前团队" }} · {{ members.length }} 人
            </p>
            <p class="mt-2 text-[13px] leading-6 text-on-surface-variant">
              统一管理工作区成员和角色分工。当前支持添加已注册平台账号、调整角色，以及移出团队。
            </p>
          </div>

          <button class="admin-quiet-btn" @click="loadData">
            <span class="material-symbols-outlined text-[17px]">refresh</span>
            刷新成员
          </button>
        </div>

        <div
          v-if="message.text"
          class="mt-5 rounded-[14px] px-4 py-3 text-[13px] font-medium"
          :class="message.type === 'success' ? 'bg-[#e9f8ef] text-[#42bc7a]' : 'bg-[#fff1ef] text-[#cb4a4a]'"
        >
          {{ message.text }}
        </div>

        <div class="mt-6 admin-table-shell">
          <div class="grid grid-cols-[minmax(220px,2fr)_150px_130px_130px_160px] gap-4 px-6 py-4 admin-table-head">
            <div class="admin-table-label">成员信息</div>
            <div class="admin-table-label">角色</div>
            <div class="admin-table-label">加入时间</div>
            <div class="admin-table-label">最近活跃</div>
            <div class="admin-table-label text-right">操作</div>
          </div>

          <div v-if="members.length === 0" class="admin-empty">
            <div class="flex h-16 w-16 items-center justify-center rounded-full bg-surface-container-low text-on-surface-variant">
              <span class="material-symbols-outlined text-[28px]">group</span>
            </div>
            <p class="mt-4 text-sm font-semibold text-on-surface">团队成员为空</p>
            <p class="mt-1 text-sm text-on-surface-variant">可从右侧添加已注册平台账号到当前工作区。</p>
          </div>

          <div v-else>
            <div
              v-for="member in members"
              :key="member.id"
              class="admin-table-row grid grid-cols-[minmax(220px,2fr)_150px_130px_130px_160px] gap-4 border-b border-[#f0f4fa] px-6 py-5 last:border-b-0"
            >
              <div class="min-w-0">
                <div class="flex items-center gap-2">
                  <p class="truncate text-[14px] font-semibold text-on-surface">{{ member.display_name }}</p>
                  <span v-if="member.is_current_user" class="admin-badge admin-badge-blue">当前账号</span>
                </div>
                <p class="mt-1 truncate text-[12px] text-on-surface-variant">{{ member.email }}</p>
              </div>

              <div class="flex items-center">
                <div v-if="canManage && !member.is_current_user" class="relative w-full">
                  <select v-model="roleDrafts[member.id]" class="admin-select appearance-none pr-9">
                    <option value="workspace_owner">所有者</option>
                    <option value="admin">管理员</option>
                    <option value="recruiter">招聘成员</option>
                    <option value="viewer">只读</option>
                  </select>
                  <span class="pointer-events-none material-symbols-outlined absolute right-3 top-1/2 -translate-y-1/2 text-[18px] text-[#a4afc0]">
                    expand_more
                  </span>
                </div>
                <span v-else class="admin-badge" :class="roleBadgeClass(member.role)">{{ roleText(member.role) }}</span>
              </div>

              <div class="flex items-center text-[13px] text-on-surface-variant">
                {{ formatDate(member.joined_at) }}
              </div>

              <div class="flex items-center text-[13px] text-on-surface-variant">
                {{ formatDate(member.last_active_at) }}
              </div>

              <div class="flex items-center justify-end gap-2">
                <template v-if="canManage && !member.is_current_user">
                  <button
                    class="admin-quiet-btn min-w-[72px]"
                    :disabled="savingMemberId === member.id || removingMemberId === member.id || roleDrafts[member.id] === member.role"
                    @click="handleSaveRole(member)"
                  >
                    <span
                      v-if="savingMemberId === member.id"
                      class="h-4 w-4 animate-spin rounded-full border-2 border-[#b9c9e8] border-t-primary"
                    ></span>
                    {{ savingMemberId === member.id ? "保存中" : "保存" }}
                  </button>
                  <button
                    class="admin-link-btn"
                    :disabled="removingMemberId === member.id"
                    @click="handleRemove(member)"
                  >
                    {{ removingMemberId === member.id ? "移除中..." : "移除" }}
                  </button>
                </template>
                <span v-else class="text-[12px] text-on-surface-variant">--</span>
              </div>
            </div>
          </div>
        </div>
      </article>

      <aside class="space-y-5">
        <article class="admin-panel px-5 py-5">
          <div class="flex items-center justify-between gap-3">
            <p class="admin-section-title">添加团队成员</p>
            <span class="admin-badge" :class="canManage ? 'admin-badge-violet' : 'admin-badge-orange'">
              {{ canManage ? "所有者权限" : "无管理权限" }}
            </span>
          </div>

          <p class="mt-3 text-[13px] leading-7 text-on-surface-variant">
            当前版本支持将已注册平台账号加入工作区，并立即赋予角色。暂不包含邮件邀请和审批流。
          </p>

          <div class="mt-5">
            <label class="admin-label">成员邮箱</label>
            <input
              v-model.trim="inviteEmail"
              type="email"
              class="admin-input mt-2"
              placeholder="请输入已注册账号邮箱"
              :disabled="!canManage"
            >
          </div>

          <div class="mt-4">
            <label class="admin-label">初始角色</label>
            <div class="relative mt-2">
              <select v-model="inviteRole" class="admin-select appearance-none pr-9" :disabled="!canManage">
                <option value="admin">管理员</option>
                <option value="recruiter">招聘成员</option>
                <option value="viewer">只读</option>
              </select>
              <span class="pointer-events-none material-symbols-outlined absolute right-3 top-1/2 -translate-y-1/2 text-[18px] text-[#a4afc0]">
                expand_more
              </span>
            </div>
          </div>

          <button class="admin-primary-btn mt-5 w-full" :disabled="!canManage || inviteSaving" @click="handleInvite">
            <span v-if="inviteSaving" class="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white"></span>
            {{ inviteSaving ? "添加中..." : "添加到团队" }}
          </button>
        </article>

        <article class="admin-panel px-5 py-5">
          <p class="admin-section-title">角色说明</p>
          <div class="mt-4 space-y-3">
            <div class="rounded-[12px] bg-[#f8fbff] px-4 py-3">
              <p class="text-[13px] font-semibold text-on-surface">所有者</p>
              <p class="mt-1 text-[12px] leading-6 text-on-surface-variant">可修改组织配置、添加成员、调整角色和移除成员。</p>
            </div>
            <div class="rounded-[12px] bg-[#f8fbff] px-4 py-3">
              <p class="text-[13px] font-semibold text-on-surface">管理员</p>
              <p class="mt-1 text-[12px] leading-6 text-on-surface-variant">可参与业务使用，适合作为团队负责人协同运营。</p>
            </div>
            <div class="rounded-[12px] bg-[#f8fbff] px-4 py-3">
              <p class="text-[13px] font-semibold text-on-surface">招聘成员 / 只读</p>
              <p class="mt-1 text-[12px] leading-6 text-on-surface-variant">招聘成员可执行日常操作，只读成员适合汇报或旁观角色。</p>
            </div>
          </div>
        </article>
      </aside>
    </section>
  </div>
</template>
