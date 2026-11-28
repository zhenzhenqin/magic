<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { personalAi } from '../api/personalAi'
import { authMessage } from '../stores/auth'

const api = personalAi()
const show = ref(false)
const busy = ref(false)
const error = ref('')

onMounted(async () => {
  try {
    const state = await api.read()
    show.value = !state.intro_dismissed && !state.connected
  } catch { /* The diary remains available. */ }
})

async function dismiss() {
  if (busy.value) return
  busy.value = true
  error.value = ''
  try { await api.preferences({ dismiss_intro: true }); show.value = false }
  catch (failure) { error.value = authMessage(failure) }
  finally { busy.value = false }
}
</script>

<template>
  <aside v-if="show" class="connection-note" aria-label="首次使用 AI 助手">
    <div><strong>个人 AI 助手</strong><p>选择照片后才会交给 DeepSeek 识别，由你自己的账户承担费用。也可以先手动记餐。</p></div>
    <div class="toolbar">
      <RouterLink class="text-action" :to="{ name: 'personal-ai', query: { welcome: '1' } }">了解如何连接</RouterLink>
      <button class="text-action" type="button" :disabled="busy" @click="dismiss">暂时跳过</button>
    </div>
    <p v-if="error" class="form-error" role="alert">{{ error }}</p>
  </aside>
</template>

<style scoped>
.connection-note { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: .3rem 1rem; border-block: 1px solid var(--color-line); padding: .6rem 0; color: var(--color-ink); }
.connection-note strong { font-size: .88rem; }
.connection-note p { font-size: .79rem; color: var(--color-muted); }
.connection-note .text-action { font-size: .8rem; }
</style>
