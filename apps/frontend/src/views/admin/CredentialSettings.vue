<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { updateBossCredential } from "../../api";
import { useAuthStore } from "../../stores/auth";
import { useSystemAlertsStore } from "../../stores/systemAlerts";

const auth = useAuthStore();
const alerts = useSystemAlertsStore();

const cookieInput = ref("");
const saving = ref(false);
const message = ref<{ text: string; type: "success" | "error" | "" }>({ text: "", type: "" });

const workspaceId = computed(() => auth.currentWorkspaceId || "");
const credential = computed(() => alerts.bossCredential);
const loading = computed(() => alerts.bossCredentialLoading);
const error = computed(() => alerts.bossCredentialError);
const hasExpiredAlert = computed(() => alerts.hasBossCredentialExpired && Boolean(credential.value));

onMounted(() => {
  void loadData();
});

watch(workspaceId, () => {
  void loadData();
});

async function loadData(): Promise<void> {
  message.value = { text: "", type: "" };
  await alerts.refreshBossCredentialStatus(true, true);
}

async function handleSaveCookie(): Promise<void> {
  if (!cookieInput.value.trim()) {
    message.value = { text: "请输入有效的 Cookie 字符串", type: "error" };
    return;
  }

  saving.value = true;
  message.value = { text: "", type: "" };
  try {
    await updateBossCredential(cookieInput.value.trim());
    cookieInput.value = "";
    await alerts.refreshBossCredentialStatus(true, true);
    message.value = { text: "BOSS 凭据已更新并安全保存", type: "success" };
  } catch (err) {
    message.value = { text: String((err as { message?: string } | null)?.message || "更新凭据失败"), type: "error" };
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

function statusText(status?: string | null): string {
  return String(status || "").trim().toLowerCase() === "normal" ? "连接正常" : "凭据失效";
}

function statusBadgeClass(status?: string | null): string {
  return String(status || "").trim().toLowerCase() === "normal" ? "admin-badge-green" : "admin-badge-red";
}
</script>

<template>
  <div class="admin-page">
    <section class="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1.55fr)_360px]">
      <article class="admin-panel px-6 py-6">
        <div class="flex items-center justify-between gap-4">
          <div>
            <p class="admin-kicker">Platform Credentials</p>
            <p class="mt-3 text-[22px] font-semibold tracking-tight text-on-surface">管理招聘平台接入凭据</p>
            <p class="mt-2 text-[13px] leading-6 text-on-surface-variant">
              系统会以加密方式保存当前工作区的 BOSS Cookie，用于职位、候选人和状态同步。
            </p>
          </div>

          <button class="admin-quiet-btn" :disabled="loading" @click="loadData">
            <span class="material-symbols-outlined text-[17px]" :class="{ 'animate-spin': loading }">refresh</span>
            刷新状态
          </button>
        </div>

        <div
          v-if="hasExpiredAlert"
          class="mt-5 rounded-[18px] border border-[#ffd9d4] bg-[#fff4f2] px-5 py-4"
        >
          <div class="flex items-start gap-3">
            <div class="flex h-10 w-10 items-center justify-center rounded-full bg-[#ffe5e1] text-[#d25555]">
              <span class="material-symbols-outlined text-[18px]">warning</span>
            </div>
            <div class="min-w-0 flex-1">
              <p class="text-[14px] font-semibold text-[#c94d4d]">BOSS 凭据已失效</p>
              <p class="mt-2 text-[13px] leading-6 text-[#b35a5a]">
                请尽快更新 BOSS Cookie，否则职位同步、候选人同步和相关自动化流程会暂停。
              </p>
              <p class="mt-2 text-[12px] text-[#b35a5a]">
                最近失败时间：{{ formatDate(credential?.last_failure_at) }}
              </p>
            </div>
          </div>
        </div>

        <div v-if="error" class="mt-5 rounded-[14px] bg-[#fff1ef] px-4 py-3 text-[13px] font-medium text-[#cb4a4a]">
          {{ error }}
        </div>

        <div v-if="credential" class="mt-6 rounded-[18px] border border-[#e7edf6] bg-[#f8fbff] px-5 py-4">
          <div class="flex items-start gap-4">
            <div
              class="flex h-10 w-10 items-center justify-center rounded-full"
              :class="hasExpiredAlert ? 'bg-[#ffe5e1] text-[#d25555]' : 'bg-[#edf4ff] text-primary'"
            >
              <span class="material-symbols-outlined text-[18px]">key</span>
            </div>
            <div class="min-w-0 flex-1">
              <div class="flex flex-wrap items-center gap-2">
                <p class="text-[15px] font-semibold text-on-surface">{{ credential.account_name }}</p>
                <span class="admin-badge" :class="statusBadgeClass(credential.status)">
                  {{ statusText(credential.status) }}
                </span>
              </div>
              <p class="mt-2 text-[13px] text-on-surface-variant">
                最近失败时间：{{ formatDate(credential.last_failure_at) }} · 失败次数：{{ credential.failure_count }}
              </p>
            </div>
          </div>
        </div>

        <div v-else class="mt-6 rounded-[18px] border border-dashed border-[#dbe6f8] bg-[#fbfdff] px-5 py-6">
          <p class="text-[14px] font-semibold text-on-surface">尚未配置 BOSS 凭据</p>
          <p class="mt-2 text-[13px] leading-6 text-on-surface-variant">
            粘贴最新 Cookie 后即可启用招聘平台同步。
          </p>
        </div>

        <div class="mt-6">
          <label class="mb-2 block text-[13px] font-semibold text-on-surface">BOSS Cookie</label>
          <textarea
            v-model="cookieInput"
            rows="6"
            placeholder="请粘贴完整的 Cookie 字符串"
            class="admin-textarea font-mono"
          ></textarea>
        </div>

        <div
          v-if="message.text"
          class="mt-4 rounded-[14px] px-4 py-3 text-[13px] font-medium"
          :class="message.type === 'success' ? 'bg-[#e9f8ef] text-[#42bc7a]' : 'bg-[#fff1ef] text-[#cb4a4a]'"
        >
          {{ message.text }}
        </div>

        <div class="mt-5 flex justify-end">
          <button class="admin-primary-btn" :disabled="saving" @click="handleSaveCookie">
            <span v-if="saving" class="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white"></span>
            {{ saving ? "更新中..." : "保存凭据" }}
          </button>
        </div>
      </article>

      <aside class="space-y-6">
        <article class="admin-panel px-6 py-6">
          <p class="admin-section-title">安全说明</p>
          <p class="mt-3 text-[13px] leading-7 text-on-surface-variant">
            当前版本按工作区隔离保存平台凭据，不会复用其他团队的登录状态。建议更新后立即执行一次职位同步验证结果。
          </p>
        </article>

        <article class="admin-panel px-6 py-6">
          <p class="admin-section-title">更新建议</p>
          <div class="mt-4 space-y-3">
            <div class="rounded-[14px] bg-[#f8fbff] px-4 py-3">
              <p class="text-[13px] font-semibold text-on-surface">失效后立即更新</p>
              <p class="mt-1 text-[12px] text-on-surface-variant">一旦 BOSS 登录态失效，建议马上替换最新 Cookie。</p>
            </div>
            <div class="rounded-[14px] bg-[#f8fbff] px-4 py-3">
              <p class="text-[13px] font-semibold text-on-surface">更新后主动刷新</p>
              <p class="mt-1 text-[12px] text-on-surface-variant">保存凭据后，可点击上方“刷新状态”确认恢复正常。</p>
            </div>
            <div class="rounded-[14px] bg-[#f8fbff] px-4 py-3">
              <p class="text-[13px] font-semibold text-on-surface">避免同步中断</p>
              <p class="mt-1 text-[12px] text-on-surface-variant">凭据有效时，职位同步、候选人同步和自动流程才会持续工作。</p>
            </div>
          </div>
        </article>
      </aside>
    </section>
  </div>
</template>
