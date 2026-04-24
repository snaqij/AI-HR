import { computed, ref } from "vue";
import { defineStore } from "pinia";
import {
  clearClientAuthState,
  createWorkspace,
  fetchCurrentUser,
  getActiveWorkspaceId,
  login,
  logout,
  refreshSession,
  register,
  selectWorkspace,
  type AuthLoginRequest,
  type AuthMeResponse,
  type AuthRegisterRequest,
  type AuthWorkspaceSummary,
} from "../api";

function formatErrorMessage(err: unknown, fallback = "Request failed"): string {
  const message = String((err as { message?: string } | null)?.message || "").trim();
  return message || fallback;
}

export const useAuthStore = defineStore("auth", () => {
  const ready = ref(false);
  const loading = ref(false);
  const userId = ref<string | null>(null);
  const email = ref<string | null>(null);
  const displayName = ref<string | null>(null);
  const status = ref<string>("anonymous");
  const workspaces = ref<AuthWorkspaceSummary[]>([]);
  const currentWorkspaceId = ref<string | null>(getActiveWorkspaceId());
  const lastError = ref<string>("");

  const isAuthenticated = computed(() => Boolean(userId.value));

  function resetIdentityState(): void {
    userId.value = null;
    email.value = null;
    displayName.value = null;
    status.value = "anonymous";
    workspaces.value = [];
    currentWorkspaceId.value = null;
    clearClientAuthState();
  }

  function applyProfile(me: AuthMeResponse): void {
    userId.value = me.user_id;
    email.value = me.email;
    displayName.value = me.display_name;
    status.value = me.status;
    workspaces.value = Array.isArray(me.workspaces) ? me.workspaces : [];

    const workspaceIds = new Set(workspaces.value.map((item) => item.id));
    const preferredWorkspaceId = String(getActiveWorkspaceId() || "").trim();
    const fallbackWorkspaceId = String(me.current_workspace_id || "").trim() || String(workspaces.value[0]?.id || "").trim();
    const selectedWorkspaceId = workspaceIds.has(preferredWorkspaceId) ? preferredWorkspaceId : fallbackWorkspaceId;
    if (selectedWorkspaceId) {
      selectWorkspace(selectedWorkspaceId);
      currentWorkspaceId.value = selectedWorkspaceId;
    } else {
      currentWorkspaceId.value = null;
    }
  }

  async function reloadProfile(): Promise<void> {
    const me = await fetchCurrentUser();
    applyProfile(me);
  }

  async function bootstrap(): Promise<void> {
    if (ready.value || loading.value) {
      return;
    }
    loading.value = true;
    lastError.value = "";
    try {
      try {
        await refreshSession();
      } catch {
        // Ignore refresh failures and fall back to direct profile probing.
      }
      await reloadProfile();
    } catch {
      resetIdentityState();
    } finally {
      ready.value = true;
      loading.value = false;
    }
  }

  async function loginWithPassword(payload: AuthLoginRequest): Promise<void> {
    loading.value = true;
    lastError.value = "";
    try {
      await login(payload);
      await reloadProfile();
      ready.value = true;
    } catch (err) {
      resetIdentityState();
      lastError.value = formatErrorMessage(err, "Login failed");
      throw err;
    } finally {
      loading.value = false;
    }
  }

  async function registerAccount(payload: AuthRegisterRequest): Promise<void> {
    loading.value = true;
    lastError.value = "";
    try {
      await register(payload);
      await reloadProfile();
      ready.value = true;
    } catch (err) {
      resetIdentityState();
      lastError.value = formatErrorMessage(err, "Registration failed");
      throw err;
    } finally {
      loading.value = false;
    }
  }

  async function logoutCurrentUser(): Promise<void> {
    loading.value = true;
    lastError.value = "";
    try {
      await logout();
    } finally {
      resetIdentityState();
      ready.value = true;
      loading.value = false;
    }
  }

  async function switchWorkspace(workspaceId: string): Promise<void> {
    const normalized = String(workspaceId || "").trim();
    if (!normalized) {
      throw new Error("Workspace id is required");
    }
    const previousWorkspaceId = currentWorkspaceId.value;
    selectWorkspace(normalized);
    currentWorkspaceId.value = normalized;
    try {
      await reloadProfile();
    } catch (err) {
      if (previousWorkspaceId) {
        selectWorkspace(previousWorkspaceId);
        currentWorkspaceId.value = previousWorkspaceId;
      }
      lastError.value = formatErrorMessage(err, "Switch workspace failed");
      throw err;
    }
  }

  async function createWorkspaceAndSwitch(name: string): Promise<void> {
    const normalized = String(name || "").trim();
    if (!normalized) {
      throw new Error("Workspace name is required");
    }
    const created = await createWorkspace({ name: normalized });
    await switchWorkspace(created.workspace.id);
  }

  return {
    ready,
    loading,
    userId,
    email,
    displayName,
    status,
    workspaces,
    currentWorkspaceId,
    lastError,
    isAuthenticated,
    bootstrap,
    reloadProfile,
    loginWithPassword,
    registerAccount,
    logoutCurrentUser,
    switchWorkspace,
    createWorkspaceAndSwitch,
  };
});
