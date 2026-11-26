<script setup lang="ts">
import { LogOut, UserRound } from 'lucide-vue-next'
import { onMounted, reactive, ref, watch } from 'vue'
import ModalSurface from '../components/ModalSurface.vue'
import PageHeading from '../components/PageHeading.vue'
import { authMessage, useAuth } from '../stores/auth'

const auth = useAuth()
const nickname = ref('')
const preferences = reactive({ timezone: '', show_calories: true, show_nutrition: true })
const loaded = ref(false)
const busy = ref<'load' | 'profile' | 'settings' | 'logout' | ''>('')
const message = ref('')
const error = ref('')
const confirming = ref(false)

watch(() => auth.currentUser?.nickname, value => { nickname.value = value ?? '' }, { immediate: true })

async function perform(action: typeof busy.value, work: () => Promise<void>, success = '') {
  if (busy.value) return
  busy.value = action
  message.value = ''
  error.value = ''
  try {
    await work()
    message.value = success
  } catch (failure) {
    error.value = authMessage(failure)
  } finally {
    busy.value = ''
  }
}

const load = () => perform('load', async () => {
  await auth.loadProfile()
  Object.assign(preferences, await auth.loadPreferences())
  loaded.value = true
})
const saveProfile = () => perform('profile', () => auth.updateProfile(nickname.value), '昵称已保存。')
const saveSettings = () => perform('settings', async () => {
  Object.assign(preferences, await auth.updatePreferences({
    timezone: preferences.timezone, show_calories: preferences.show_calories, show_nutrition: preferences.show_nutrition,
  }))
}, '个人设置已保存。')
const logout = () => perform('logout', async () => {
  await auth.logout()
  confirming.value = false
})

onMounted(load)
</script>

<template>
  <div>
    <PageHeading title="我的" subtitle="管理你的私人手账账号。" />
    <div v-if="auth.currentUser" class="profile-grid">
      <section class="paper-panel panel-pad form-stack">
        <h2><UserRound aria-hidden="true" /> 个人资料</h2>
        <dl><div><dt>用户名</dt><dd>{{ auth.currentUser.username }}</dd></div><div><dt>公开用户 ID</dt><dd>{{ auth.currentUser.public_id }}</dd></div></dl>
        <form class="form-stack" @submit.prevent="saveProfile">
          <label class="field">昵称<input v-model="nickname" type="text" maxlength="40" autocomplete="nickname" required /></label>
          <button class="button button-primary" :disabled="!!busy">{{ busy === 'profile' ? '正在保存…' : '保存昵称' }}</button>
        </form>
      </section>
      <section class="paper-panel panel-pad form-stack">
        <h2>个人设置</h2>
        <form v-if="loaded" class="form-stack" @submit.prevent="saveSettings">
          <label class="field">时区<input v-model="preferences.timezone" type="text" maxlength="64" placeholder="Asia/Shanghai" required /></label>
          <label class="check"><input v-model="preferences.show_calories" type="checkbox" /> 显示热量</label>
          <label class="check"><input v-model="preferences.show_nutrition" type="checkbox" /> 显示营养成分</label>
          <button class="button button-primary" :disabled="!!busy">{{ busy === 'settings' ? '正在保存…' : '保存设置' }}</button>
        </form>
        <p v-else-if="busy === 'load'" class="caption" role="status">正在读取设置…</p>
        <button v-else class="button" @click="load">重新读取设置</button>
      </section>
    </div>
    <p v-if="message" class="notice badge" role="status">{{ message }}</p>
    <p v-if="error && !confirming" class="notice form-error" role="alert">{{ error }}</p>
    <div class="notice"><button class="button button-danger" :disabled="!!busy" @click="confirming = true; error = ''"><LogOut /> 退出登录</button></div>
    <ModalSurface :open="confirming" title="退出登录" @close="!busy && (confirming = false)">
      <p>退出后，需要重新登录才能访问你的手账。</p>
      <p v-if="error" class="form-error" role="alert">{{ error }}</p>
      <div class="toolbar">
        <button class="button button-danger" :disabled="!!busy" @click="logout">{{ busy === 'logout' ? '正在退出…' : '确认退出' }}</button>
        <button class="button" :disabled="!!busy" @click="confirming = false">取消</button>
      </div>
    </ModalSurface>
  </div>
</template>

<style scoped>
.profile-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: calc(var(--space-unit) * 8); align-items: start; }
h2 { display: flex; align-items: center; gap: calc(var(--space-unit) * 4); font: 700 1.3rem var(--font-serif); }
h2 svg { width: 1.15rem; color: var(--color-sage-deep); }
dl { display: grid; gap: calc(var(--space-unit) * 6); margin: 0; }
dt { color: var(--color-muted); font-size: .86rem; }
dd { margin: 0; overflow-wrap: anywhere; }
.check { display: flex; align-items: center; gap: calc(var(--space-unit) * 4); min-height: var(--tap-size); }
.check input { accent-color: var(--color-sage-deep); width: 1.15rem; height: 1.15rem; }
.notice { margin-top: calc(var(--space-unit) * 8); }
@media (max-width: 650px) { .profile-grid { grid-template-columns: minmax(0, 1fr); } }
</style>
