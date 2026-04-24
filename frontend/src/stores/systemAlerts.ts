import { computed, ref } from "vue";
import { defineStore } from "pinia";
import { fetchBossCredential, type CredentialStatus, validateBossCredential } from "../api";
import { useAuthStore } from "./auth";

function formatErrorMessage(err: unknown, fallback = "Request failed"): string {
  const message = String((err as { message?: string } | null)?.message || "").trim();
  return message || fallback;
}

function normalizeCredentialStatus(status: string | null | undefined): string {
  return String(status || "").trim().toLowerCase();
}

export const useSystemAlertsStore = defineStore("system-alerts", () => {
  const bossCredential = ref<CredentialStatus | null>(null);
  const bossCredentialLoading = ref(false);
  const bossCredentialError = ref("");
  const lastWorkspaceId = ref("");

  const hasBossCredentialExpired = computed(() => {
    const credential = bossCredential.value;
    if (!credential) {
      return false;
    }
    const status = normalizeCredentialStatus(credential.status);
    return credential.is_active === false || (Boolean(status) && status !== "normal");
  });

  async function refreshBossCredentialStatus(force = false, validate = false): Promise<void> {
    const auth = useAuthStore();
    const workspaceId = String(auth.currentWorkspaceId || "").trim();

    if (!workspaceId) {
      clearBossCredentialStatus();
      return;
    }

    if (!force && bossCredentialLoading.value && lastWorkspaceId.value === workspaceId) {
      return;
    }

    bossCredentialLoading.value = true;
    bossCredentialError.value = "";

    try {
      bossCredential.value = validate ? await validateBossCredential() : await fetchBossCredential();
    } catch (err) {
      const text = formatErrorMessage(err, "加载 BOSS 凭证状态失败");
      if (text.includes("No active credential found") || text.includes("HTTP 404")) {
        bossCredential.value = null;
        bossCredentialError.value = "";
      } else {
        if (validate) {
          try {
            bossCredential.value = await fetchBossCredential();
            bossCredentialError.value = text;
          } catch {
            bossCredential.value = null;
            bossCredentialError.value = text;
          }
        } else {
          bossCredential.value = null;
          bossCredentialError.value = text;
        }
      }
    } finally {
      lastWorkspaceId.value = workspaceId;
      bossCredentialLoading.value = false;
    }
  }

  function clearBossCredentialStatus(): void {
    bossCredential.value = null;
    bossCredentialLoading.value = false;
    bossCredentialError.value = "";
    lastWorkspaceId.value = "";
  }

  return {
    bossCredential,
    bossCredentialLoading,
    bossCredentialError,
    hasBossCredentialExpired,
    refreshBossCredentialStatus,
    clearBossCredentialStatus,
  };
});
