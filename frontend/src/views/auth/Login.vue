<script setup lang="ts">
import { computed, ref } from "vue";
import { useRoute, useRouter } from "vue-router";

import { useAuthStore } from "../../stores/auth";

const auth = useAuthStore();
const route = useRoute();
const router = useRouter();

const email = ref("");
const password = ref("");
const submitting = ref(false);
const formError = ref("");

const redirectPath = computed(() => {
  const candidate = String(route.query.redirect || "").trim();
  if (!candidate.startsWith("/admin")) {
    return "/admin";
  }
  return candidate;
});

async function submitLogin(): Promise<void> {
  if (submitting.value) {
    return;
  }
  formError.value = "";
  submitting.value = true;
  try {
    await auth.loginWithPassword({
      email: email.value.trim(),
      password: password.value,
    });
    await router.replace(redirectPath.value);
  } catch (err) {
    formError.value = String((err as { message?: string } | null)?.message || "登录失败，请检查账号或密码");
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <div class="relative flex min-h-screen items-center overflow-hidden bg-[radial-gradient(1200px_500px_at_10%_0%,#ffffff_0%,rgba(255,255,255,0)_62%),radial-gradient(800px_360px_at_100%_100%,#dcd9ea_0%,rgba(220,217,234,0)_68%),linear-gradient(180deg,#eceaf4_0%,#e8e6f1_100%)] px-4 py-8 sm:px-6 sm:py-10 lg:px-10 lg:py-14">
    <div class="pointer-events-none absolute -left-24 top-20 h-64 w-64 rounded-full bg-white/35 blur-3xl"></div>
    <div class="pointer-events-none absolute right-8 top-10 h-40 w-40 rounded-full bg-[#cdd6ff]/35 blur-2xl"></div>
    <div class="pointer-events-none absolute bottom-6 left-1/3 h-32 w-72 rounded-full bg-[#e3e0f0]/70 blur-xl"></div>

    <div class="relative mx-auto my-auto grid w-full max-w-5xl overflow-hidden rounded-3xl border border-white/70 bg-white/90 shadow-[0_30px_80px_-30px_rgba(35,34,62,0.35)] backdrop-blur-sm lg:h-[660px] lg:grid-cols-[56%_44%] lg:translate-y-2">
      <section class="relative hidden overflow-hidden bg-[#f3f2f8] lg:flex">
        <div class="absolute -left-10 -top-10 h-44 w-44 rounded-full bg-[#dbd8ed]"></div>
        <div class="absolute right-8 top-12 h-8 w-24 rounded-full bg-[#e5e2f2]"></div>
        <div class="absolute left-14 bottom-12 h-24 w-24 rounded-3xl bg-[#e6e3f3]"></div>
        <div class="absolute right-10 bottom-8 h-32 w-40 rounded-[2rem] bg-[#e1deef]"></div>

        <div class="relative z-10 flex h-full w-full flex-col justify-between p-10">
          <div>
            <p class="text-xs font-semibold tracking-[0.3em] text-[#6b6493]">AI-HR PLATFORM</p>
            <h2 class="mt-3 text-3xl font-bold leading-tight text-[#262445]">智能招聘工作台</h2>
          </div>

          <div class="mx-auto w-[82%] max-w-[430px]">
            <div class="relative rounded-[2rem] border border-[#d7d2ea] bg-white p-4 shadow-[0_20px_40px_-20px_rgba(46,41,82,0.45)]">
              <div class="mb-3 flex items-center gap-2">
                <span class="h-2.5 w-2.5 rounded-full bg-[#7f74ff]"></span>
                <span class="h-2.5 w-2.5 rounded-full bg-[#00b7ff]"></span>
                <span class="h-2.5 w-2.5 rounded-full bg-[#9ca3af]"></span>
              </div>
              <div class="grid grid-cols-3 gap-2">
                <div class="col-span-2 h-16 rounded-xl bg-gradient-to-r from-[#6f63ff] to-[#45b6ff]"></div>
                <div class="h-16 rounded-xl bg-[#f1effa]"></div>
                <div class="h-10 rounded-lg bg-[#f5f4fb]"></div>
                <div class="h-10 rounded-lg bg-[#f5f4fb]"></div>
                <div class="h-10 rounded-lg bg-[#f5f4fb]"></div>
              </div>
            </div>
            <div class="mt-4 grid grid-cols-2 gap-3">
              <div class="rounded-2xl border border-[#dcd7ef] bg-white p-3">
                <div class="h-2 w-16 rounded bg-[#d8d4eb]"></div>
                <div class="mt-2 h-6 w-24 rounded bg-[#efeefa]"></div>
              </div>
              <div class="rounded-2xl border border-[#dcd7ef] bg-white p-3">
                <div class="h-2 w-14 rounded bg-[#d8d4eb]"></div>
                <div class="mt-2 h-6 w-20 rounded bg-[#efeefa]"></div>
              </div>
            </div>
          </div>

          <p class="max-w-sm text-sm leading-7 text-[#57527b]">统一管理职位、候选人和面试流程，提升团队招聘效率。</p>
        </div>
      </section>

      <section class="flex h-full w-full items-center justify-center bg-[linear-gradient(145deg,#ffffff_0%,#fbfbff_100%)] px-6 py-8 sm:px-8 lg:px-10">
        <div class="w-full max-w-[300px] lg:translate-y-3">
          <p class="text-center text-xs font-semibold tracking-[0.24em] text-primary/70">欢迎回来</p>
          <h1 class="mt-3 text-center text-3xl font-bold text-on-surface">登录 AI-HR</h1>
          <p class="mt-2 text-center text-sm text-on-surface-variant">请输入账号信息，进入管理后台。</p>

          <form class="mt-6 space-y-4" @submit.prevent="submitLogin">
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

            <label class="block">
              <span class="mb-1.5 block text-sm font-medium text-on-surface">密码</span>
              <input
                v-model="password"
                type="password"
                autocomplete="current-password"
                placeholder="请输入密码"
                required
                class="w-full rounded-xl border border-outline-variant/35 bg-white px-3 py-2 text-sm outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/15"
              />
            </label>

            <p v-if="formError" class="text-sm text-error">{{ formError }}</p>

            <button
              type="submit"
              class="w-full rounded-xl bg-primary py-2 text-sm font-semibold text-white transition hover:opacity-95 disabled:cursor-not-allowed disabled:opacity-60"
              :disabled="submitting"
            >
              {{ submitting ? "登录中..." : "登录" }}
            </button>
          </form>

          <p class="mt-7 text-center text-sm text-on-surface-variant">
            还没有账号？
            <router-link to="/register" class="font-semibold text-primary hover:underline">立即注册</router-link>
          </p>
        </div>
      </section>
    </div>
  </div>
</template>
