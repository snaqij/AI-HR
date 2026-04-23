<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { fetchBossCredential, updateBossCredential, type CredentialStatus } from '../../api';

const credential = ref<CredentialStatus | null>(null);
const cookieInput = ref('');
const loading = ref(false);
const saving = ref(false);
const message = ref({ text: '', type: '' });

const loadData = async () => {
  loading.value = true;
  try {
    credential.value = await fetchBossCredential();
  } catch (err) {
    console.error('Failed to fetch boss credentials', err);
  } finally {
    loading.value = false;
  }
};

const handleSaveCookie = async () => {
  if (!cookieInput.value.trim()) {
    message.value = { text: '请输入有效的 Cookie 字符串', type: 'error' };
    return;
  }

  saving.value = true;
  message.value = { text: '', type: '' };
  try {
    await updateBossCredential(cookieInput.value);
    message.value = { text: 'Cookie 已成功更新并加密存储', type: 'success' };
    cookieInput.value = '';
    await loadData();
  } catch (err) {
    message.value = { text: '更新失败，请检查网络连接或后端服务状态', type: 'error' };
    console.error(err);
  } finally {
    saving.value = false;
  }
};

onMounted(loadData);
</script>

<template>
  <div class="max-w-7xl mx-auto">
    <div class="mb-10">
      <span class="text-[10px] font-bold tracking-[0.2em] text-primary uppercase">Configuration</span>
      <h1 class="text-3xl font-black text-on-surface">系统设置</h1>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-3 gap-8">
      <div class="lg:col-span-2 space-y-8">
        <!-- 核心设置区块 -->
        <div class="bg-surface-container-lowest rounded-3xl p-8 border border-outline-variant/10 shadow-sm">
          <div class="mb-8">
             <h2 class="text-xl font-black text-on-surface mb-2">招聘平台凭据</h2>
             <p class="text-sm text-on-surface-variant">在此更新当前登录用户自己的直聘渠道登录凭据。Cookie 将经过 AES-256 加密后安全存储。</p>
          </div>

          <div v-if="credential" class="mb-6 flex items-center gap-4 p-4 bg-surface-container-low rounded-2xl border border-outline-variant/5">
            <div class="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center">
              <span class="material-symbols-outlined text-primary">key</span>
            </div>
            <div class="flex-1">
              <div class="flex items-center gap-2">
                <span class="text-sm font-bold text-on-surface">{{ credential.account_name }}</span>
                <span 
                  :class="[
                    'px-2 py-0.5 rounded-full text-[10px] font-black uppercase tracking-wider',
                    credential.status === 'normal' ? 'bg-success-container text-success' : 'bg-error-container text-error'
                  ]"
                >
                  {{ credential.status === 'normal' ? 'Active' : 'Expired/Error' }}
                </span>
              </div>
              <p class="text-[10px] text-on-surface-variant mt-0.5">
                最后失效时间: {{ credential.last_failure_at || '无' }} | 失败计数: {{ credential.failure_count }}
              </p>
            </div>
          </div>

          <div class="space-y-4">
             <div class="flex flex-col gap-2">
                <label class="text-xs font-bold text-on-surface-variant ml-1">BOSS Cookie 补充</label>
                <textarea 
                  v-model="cookieInput"
                  rows="4"
                  placeholder="在此处粘贴从浏览器抓取的完整 Cookie 字符串..."
                  class="w-full bg-surface-container-high rounded-2xl p-4 text-sm text-on-surface border border-outline-variant/10 focus:outline-none focus:border-primary/50 transition-colors resize-none font-mono"
                ></textarea>
             </div>

             <div v-if="message.text" :class="['p-4 rounded-xl text-xs font-bold', message.type === 'success' ? 'bg-success-container/10 text-success' : 'bg-error-container/10 text-error']">
               {{ message.text }}
             </div>

             <button 
                @click="handleSaveCookie"
                :disabled="saving"
                class="w-full h-12 bg-primary text-on-primary rounded-2xl font-black text-sm hover:opacity-90 active:scale-[0.98] transition-all disabled:opacity-50 disabled:pointer-events-none flex items-center justify-center gap-2 shadow-lg shadow-primary/20"
             >
               <span v-if="saving" class="w-4 h-4 border-2 border-on-primary/30 border-t-on-primary rounded-full animate-spin"></span>
               {{ saving ? '正在同步...' : '更新凭据' }}
             </button>
          </div>
        </div>

        <div class="bg-surface-container-lowest rounded-3xl p-8 border border-outline-variant/10 shadow-sm opacity-50 cursor-not-allowed">
          <div v-for="section in ['常规设置', '通知设置', '团队权限']" :key="section" class="border-b border-outline-variant/5 last:border-0 pb-8 last:pb-0 mb-8 last:mb-0">
             <h3 class="font-black text-sm text-on-surface mb-4">{{ section }}</h3>
             <div class="flex items-center justify-between p-4 bg-surface rounded-xl border border-outline-variant/5">
                <span class="text-xs font-bold text-on-surface-variant italic">设置项完善中...</span>
             </div>
          </div>
        </div>
      </div>

      <div class="space-y-6">
        <div class="bg-primary/5 rounded-3xl p-6 border border-primary/10">
          <h4 class="text-primary font-black text-xs uppercase tracking-widest mb-3">安全提示</h4>
          <p class="text-xs text-on-surface-variant leading-relaxed">
            当前版本按平台用户隔离保存 BOSS Cookie。请确保你上传的是自己账号对应的最新 Cookie，系统不会再复用其他登录用户的直聘登录态。
          </p>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* 可以在此添加特殊动画 */
</style>
