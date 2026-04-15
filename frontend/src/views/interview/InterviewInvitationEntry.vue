<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { activateInterviewInvitation } from "../../api";

const route = useRoute();
const router = useRouter();
const loading = ref(true);
const errorText = ref("");

onMounted(async () => {
  const token = String(route.params.token || "").trim();
  if (!token) {
    loading.value = false;
    errorText.value = "缺少邀请 token。";
    return;
  }

  try {
    const session = await activateInterviewInvitation(token);
    await router.replace({
      path: `/interview/${session.id}`,
      query: {
        session_id: session.id,
        token: session.join_token
      }
    });
  } catch (err: any) {
    errorText.value = err?.message || "激活邀请失败，请稍后重试。";
    loading.value = false;
  }
});
</script>

<template>
  <div class="min-h-screen bg-slate-50 flex items-center justify-center px-6">
    <div class="w-full max-w-lg bg-white rounded-xl border border-slate-200 shadow-sm p-8 text-center">
      <div v-if="loading" class="space-y-3">
        <h1 class="text-lg font-semibold text-slate-900">正在进入面试房间</h1>
        <p class="text-sm text-slate-600">正在激活邀请链接并创建会话，请稍候...</p>
      </div>
      <div v-else class="space-y-3">
        <h1 class="text-lg font-semibold text-red-600">进入失败</h1>
        <p class="text-sm text-slate-700 break-all">{{ errorText }}</p>
      </div>
    </div>
  </div>
</template>

