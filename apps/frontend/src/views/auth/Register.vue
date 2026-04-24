<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from "vue";
import { useRouter } from "vue-router";

import { sendRegisterEmailCode } from "../../api";
import { useAuthStore } from "../../stores/auth";

const auth = useAuthStore();
const router = useRouter();

const displayName = ref("");
const email = ref("");
const verificationCode = ref("");
const password = ref("");
const confirmPassword = ref("");
const workspaceName = ref("我的团队");
const submitting = ref(false);
const sendingCode = ref(false);
const formError = ref("");
const codeMessage = ref("");
const cooldownSeconds = ref(0);

let cooldownTimer: ReturnType<typeof setInterval> | null = null;

const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

const emailFormatValid = computed(() => {
  const normalized = email.value.trim();
  if (!normalized) {
    return true;
  }
  return emailPattern.test(normalized);
});

const passwordMismatch = computed(() => {
  if (!confirmPassword.value) {
    return false;
  }
  return password.value !== confirmPassword.value;
});

function clearCooldownTimer(): void {
  if (cooldownTimer) {
    clearInterval(cooldownTimer);
    cooldownTimer = null;
  }
}

function startCooldown(seconds: number): void {
  clearCooldownTimer();
  cooldownSeconds.value = Math.max(0, Math.floor(seconds));
  if (cooldownSeconds.value <= 0) {
    return;
  }
  cooldownTimer = setInterval(() => {
    if (cooldownSeconds.value <= 1) {
      cooldownSeconds.value = 0;
      clearCooldownTimer();
      return;
    }
    cooldownSeconds.value -= 1;
  }, 1000);
}

async function handleSendCode(): Promise<void> {
  if (sendingCode.value || cooldownSeconds.value > 0) {
    return;
  }

  const normalizedEmail = email.value.trim();
  if (!normalizedEmail || !emailPattern.test(normalizedEmail)) {
    formError.value = "请输入正确的邮箱地址";
    codeMessage.value = "";
    return;
  }

  sendingCode.value = true;
  formError.value = "";
  codeMessage.value = "";
  try {
    const result = await sendRegisterEmailCode({ email: normalizedEmail });
    codeMessage.value = `验证码已发送到 ${result.email}`;
    startCooldown(result.resend_cooldown_seconds || 60);
  } catch (err) {
    formError.value = String((err as { message?: string } | null)?.message || "验证码发送失败，请稍后重试");
  } finally {
    sendingCode.value = false;
  }
}

async function submitRegister(): Promise<void> {
  if (submitting.value) {
    return;
  }
  if (!emailPattern.test(email.value.trim())) {
    formError.value = "请输入正确的邮箱地址";
    return;
  }
  if (!verificationCode.value.trim()) {
    formError.value = "请输入邮箱验证码";
    return;
  }
  if (passwordMismatch.value) {
    formError.value = "两次输入的密码不一致";
    return;
  }

  formError.value = "";
  submitting.value = true;
  try {
    await auth.registerAccount({
      display_name: displayName.value.trim(),
      email: email.value.trim(),
      verification_code: verificationCode.value.trim(),
      password: password.value,
      workspace_name: workspaceName.value.trim() || "我的团队",
    });
    await router.replace("/admin");
  } catch (err) {
    formError.value = String((err as { message?: string } | null)?.message || "注册失败，请稍后再试");
  } finally {
    submitting.value = false;
  }
}

onBeforeUnmount(() => {
  clearCooldownTimer();
});
</script>

<template>
  <div class="relative flex min-h-screen items-center overflow-x-hidden bg-[radial-gradient(1200px_500px_at_10%_0%,#ffffff_0%,rgba(255,255,255,0)_62%),radial-gradient(800px_360px_at_100%_100%,#dcd9ea_0%,rgba(220,217,234,0)_68%),linear-gradient(180deg,#eceaf4_0%,#e8e6f1_100%)] px-4 py-8 sm:px-6 sm:py-10 lg:px-10 lg:py-14">
    <div class="pointer-events-none absolute -left-24 top-20 h-64 w-64 rounded-full bg-white/35 blur-3xl"></div>
    <div class="pointer-events-none absolute right-8 top-10 h-40 w-40 rounded-full bg-[#cdd6ff]/35 blur-2xl"></div>
    <div class="pointer-events-none absolute bottom-6 left-1/3 h-32 w-72 rounded-full bg-[#e3e0f0]/70 blur-xl"></div>

    <div class="relative mx-auto my-auto grid w-full max-w-5xl overflow-hidden rounded-3xl border border-white/70 bg-white/90 shadow-[0_30px_80px_-30px_rgba(35,34,62,0.35)] backdrop-blur-sm lg:min-h-[660px] lg:grid-cols-[56%_44%] lg:translate-y-2">
      <section class="relative hidden overflow-hidden bg-[#f3f2f8] lg:flex">
        <div class="absolute -left-10 -top-10 h-44 w-44 rounded-full bg-[#dbd8ed]"></div>
        <div class="absolute right-8 top-12 h-8 w-24 rounded-full bg-[#e5e2f2]"></div>
        <div class="absolute left-14 bottom-12 h-24 w-24 rounded-3xl bg-[#e6e3f3]"></div>
        <div class="absolute right-10 bottom-8 h-32 w-40 rounded-[2rem] bg-[#e1deef]"></div>

        <div class="relative z-10 flex h-full w-full flex-col justify-between p-10">
          <div>
            <p class="text-xs font-semibold tracking-[0.3em] text-[#6b6493]">AI-HR WORKSPACE</p>
            <h2 class="mt-3 text-3xl font-bold leading-tight text-[#262445]">创建企业招聘空间</h2>
          </div>

          <div class="mx-auto w-[82%] max-w-[430px]">
            <div class="relative rounded-[2rem] border border-[#d7d2ea] bg-white p-4 shadow-[0_20px_40px_-20px_rgba(46,41,82,0.45)]">
              <div class="mb-3 flex items-center gap-2">
                <span class="h-2.5 w-2.5 rounded-full bg-[#7f74ff]"></span>
                <span class="h-2.5 w-2.5 rounded-full bg-[#00b7ff]"></span>
                <span class="h-2.5 w-2.5 rounded-full bg-[#9ca3af]"></span>
              </div>
              <div class="grid grid-cols-4 gap-2">
                <div class="col-span-4 h-14 rounded-xl bg-gradient-to-r from-[#6f63ff] to-[#45b6ff]"></div>
                <div class="col-span-2 h-10 rounded-lg bg-[#f5f4fb]"></div>
                <div class="col-span-2 h-10 rounded-lg bg-[#f5f4fb]"></div>
                <div class="h-8 rounded-lg bg-[#efeefa]"></div>
                <div class="h-8 rounded-lg bg-[#efeefa]"></div>
                <div class="h-8 rounded-lg bg-[#efeefa]"></div>
                <div class="h-8 rounded-lg bg-[#efeefa]"></div>
              </div>
            </div>
            <div class="mt-4 grid grid-cols-3 gap-3">
              <div class="rounded-2xl border border-[#dcd7ef] bg-white p-3">
                <div class="h-2 w-10 rounded bg-[#d8d4eb]"></div>
                <div class="mt-2 h-5 w-full rounded bg-[#efeefa]"></div>
              </div>
              <div class="rounded-2xl border border-[#dcd7ef] bg-white p-3">
                <div class="h-2 w-10 rounded bg-[#d8d4eb]"></div>
                <div class="mt-2 h-5 w-full rounded bg-[#efeefa]"></div>
              </div>
              <div class="rounded-2xl border border-[#dcd7ef] bg-white p-3">
                <div class="h-2 w-10 rounded bg-[#d8d4eb]"></div>
                <div class="mt-2 h-5 w-full rounded bg-[#efeefa]"></div>
              </div>
            </div>
          </div>

          <p class="max-w-sm text-sm leading-7 text-[#57527b]">注册后即可在团队空间中管理职位、候选人和评估策略。</p>
        </div>
      </section>

      <section class="flex h-full w-full items-center justify-center bg-[linear-gradient(145deg,#ffffff_0%,#fbfbff_100%)] px-6 py-8 sm:px-8 lg:px-10">
        <div class="w-full max-w-[320px] lg:max-w-[340px] lg:py-6">
          <p class="text-center text-xs font-semibold tracking-[0.24em] text-primary/70">创建账号</p>
          <h1 class="mt-3 text-center text-3xl font-bold text-on-surface">注册 AI-HR</h1>
          <p class="mt-2 text-center text-sm text-on-surface-variant">填写以下信息，创建你的企业招聘空间。</p>

          <form class="mt-6 space-y-4" @submit.prevent="submitRegister">
            <label class="block">
              <span class="mb-1.5 block text-sm font-medium text-on-surface">姓名</span>
              <input
                v-model="displayName"
                type="text"
                autocomplete="name"
                placeholder="请输入姓名"
                required
                class="w-full rounded-xl border border-outline-variant/35 bg-white px-3 py-2 text-sm outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/15"
              />
            </label>

            <label class="block">
              <span class="mb-1.5 block text-sm font-medium text-on-surface">团队名称</span>
              <input
                v-model="workspaceName"
                type="text"
                autocomplete="organization"
                placeholder="例如：招聘一组"
                required
                class="w-full rounded-xl border border-outline-variant/35 bg-white px-3 py-2 text-sm outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/15"
              />
            </label>

            <label class="block">
              <span class="mb-1.5 block text-sm font-medium text-on-surface">邮箱</span>
              <input
                v-model="email"
                type="email"
                autocomplete="email"
                placeholder="请输入邮箱"
                required
                class="w-full rounded-xl border border-outline-variant/35 bg-white px-3 py-2 text-sm outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/15"
              />
            </label>

            <p v-if="!emailFormatValid" class="text-sm text-error">请输入正确的邮箱地址</p>

            <label class="block">
              <span class="mb-1.5 block text-sm font-medium text-on-surface">邮箱验证码</span>
              <div class="flex gap-2">
                <input
                  v-model="verificationCode"
                  type="text"
                  inputmode="numeric"
                  maxlength="6"
                  placeholder="输入验证码"
                  required
                  class="min-w-0 flex-1 rounded-xl border border-outline-variant/35 bg-white px-3 py-2 text-sm outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/15"
                />
                <button
                  type="button"
                  class="shrink-0 rounded-xl border border-primary/25 px-3 py-2 text-sm font-semibold text-primary transition hover:bg-primary/5 disabled:cursor-not-allowed disabled:opacity-60"
                  :disabled="sendingCode || cooldownSeconds > 0"
                  @click="handleSendCode"
                >
                  {{ cooldownSeconds > 0 ? `${cooldownSeconds}s 后重发` : (sendingCode ? "发送中..." : "发送验证码") }}
                </button>
              </div>
            </label>

            <p v-if="codeMessage" class="text-sm text-emerald-600">{{ codeMessage }}</p>

            <label class="block">
              <span class="mb-1.5 block text-sm font-medium text-on-surface">密码</span>
              <input
                v-model="password"
                type="password"
                autocomplete="new-password"
                placeholder="至少 8 位"
                required
                minlength="8"
                class="w-full rounded-xl border border-outline-variant/35 bg-white px-3 py-2 text-sm outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/15"
              />
            </label>

            <label class="block">
              <span class="mb-1.5 block text-sm font-medium text-on-surface">确认密码</span>
              <input
                v-model="confirmPassword"
                type="password"
                autocomplete="new-password"
                placeholder="请再次输入密码"
                required
                minlength="8"
                class="w-full rounded-xl border border-outline-variant/35 bg-white px-3 py-2 text-sm outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/15"
              />
            </label>

            <p v-if="passwordMismatch" class="text-sm text-error">两次输入的密码不一致</p>
            <p v-if="formError" class="text-sm text-error">{{ formError }}</p>

            <button
              type="submit"
              class="w-full rounded-xl bg-primary py-2 text-sm font-semibold text-white transition hover:opacity-95 disabled:cursor-not-allowed disabled:opacity-60"
              :disabled="submitting || passwordMismatch"
            >
              {{ submitting ? "注册中..." : "注册并进入系统" }}
            </button>
          </form>

          <p class="mt-7 text-center text-sm text-on-surface-variant">
            已有账号？
            <router-link to="/login" class="font-semibold text-primary hover:underline">返回登录</router-link>
          </p>
        </div>
      </section>
    </div>
  </div>
</template>
