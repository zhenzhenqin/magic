<script setup lang="ts">
import { ArrowLeft, ChevronRight } from 'lucide-vue-next'
import { onMounted, reactive, ref } from 'vue'
import type { EmailProof, VerificationTicket } from '../api/authRepository'
import EmailCodeFields from '../components/EmailCodeFields.vue'
import { authMessage, useAuth } from '../stores/auth'

interface Session { id: string; device: string; current: boolean; last_used_at: string }
interface SecurityInfo {
  username: string
  email: string | null
  email_verified: boolean
  email_available: boolean
  ai_connected: boolean
  sessions: Session[]
}

const auth = useAuth()
const root = '/users/me/security'
const state = ref<SecurityInfo>()
const proof = ref<EmailProof>({ email: '', request_id: '', code: '' })
const emailPassword = ref('')
const password = reactive({ current_password: '', password: '' })
const deletion = reactive({ confirm_username: '', password: '' })
const busy = ref(false)
const info = ref('')
const error = ref('')

async function run(work: () => Promise<void>, success = '') {
  if (busy.value) return
  busy.value = true
  info.value = error.value = ''
  try { await work(); info.value = success } catch (failure) { error.value = authMessage(failure) }
  finally { busy.value = false }
}

async function load() { state.value = await auth.api<SecurityInfo>(root) }
onMounted(() => run(load))

const sendCode = (email: string) => auth.api<VerificationTicket>(root + '/email/code', { method: 'POST', body: { email } })
const bindEmail = () => run(async () => {
  await auth.api(root + '/email', { method: 'PUT', body: { ...proof.value, password: emailPassword.value } })
  proof.value = { email: '', request_id: '', code: '' }
  emailPassword.value = ''
  await load()
}, '邮箱已验证。')
const changePassword = () => run(async () => {
  await auth.api(root + '/password', { method: 'PUT', body: { ...password } })
  Object.assign(password, { current_password: '', password: '' })
  await load()
}, '密码已更新，其他设备的会话已撤销。')
const revoke = (id: string) => run(async () => {
  await auth.api(root + '/sessions/' + id, { method: 'DELETE' })
  await load()
}, '会话已撤销。')
const deleteAccount = () => run(async () => {
  await auth.api(root + '/account', { method: 'DELETE', body: { ...deletion } })
  Object.assign(deletion, { confirm_username: '', password: '' })
  auth.forget()
})
</script>

<template>
  <div class="editorial-settings">
    <header class="settings-heading"><RouterLink :to="{ name: 'profile' }" class="text-action"><ArrowLeft aria-hidden="true" /> 我的</RouterLink><h1>账号安全</h1></header>
    <template v-if="state">
      <section class="settings-group">
        <h2>账号与邮箱</h2>
        <dl class="settings-facts"><div><dt>用户名</dt><dd>{{ state.username }}</dd></div><div><dt>邮箱</dt><dd>{{ state.email ?? '尚未绑定' }}<span v-if="state.email_verified" class="caption"> · 已验证</span></dd></div></dl>
        <details v-if="state.email_available">
          <summary>{{ state.email_verified ? '更换邮箱' : '绑定邮箱' }}</summary>
          <form class="form-stack" @submit.prevent="bindEmail">
            <EmailCodeFields v-model="proof" :send="sendCode" />
            <label class="field">当前密码<input v-model="emailPassword" type="password" autocomplete="current-password" maxlength="128" required /></label>
            <div><button class="button button-primary" :disabled="busy || !proof.request_id">验证并保存</button></div>
          </form>
        </details>
        <p v-else class="caption">当前环境暂未启用邮箱验证。</p>
        <details>
          <summary>修改密码</summary>
          <form class="form-stack" @submit.prevent="changePassword">
            <label class="field">当前密码<input v-model="password.current_password" type="password" autocomplete="current-password" maxlength="128" required /></label>
            <label class="field">新密码<input v-model="password.password" type="password" autocomplete="new-password" minlength="12" maxlength="128" required /></label>
            <div><button class="button button-primary" :disabled="busy">更新密码</button></div>
          </form>
        </details>
      </section>
      <section class="settings-group">
        <h2>登录设备</h2>
        <ul class="session-list">
          <li v-for="session in state.sessions" :key="session.id">
            <div><strong>{{ session.device }}</strong><p class="caption">{{ session.current ? '当前会话' : '最近活动 ' + new Date(session.last_used_at).toLocaleString() }}</p></div>
            <button v-if="!session.current" type="button" class="text-action" :disabled="busy" @click="revoke(session.id)">退出此设备</button>
          </li>
        </ul>
        <div v-if="state.sessions.length > 1"><button type="button" class="button" :disabled="busy" @click="revoke('others')">退出所有其他设备</button></div>
      </section>
      <section class="settings-group">
        <h2>隐私与 AI</h2>
        <RouterLink class="settings-link" :to="{ name: 'personal-ai' }"><span>AI 助手 · {{ state.ai_connected ? '当前会话已连接' : '当前会话未连接' }}</span><ChevronRight aria-hidden="true" /></RouterLink>
        <RouterLink class="settings-link" :to="{ name: 'friends' }"><span>好友与共享授权</span><ChevronRight aria-hidden="true" /></RouterLink>
        <details class="danger">
          <summary>删除账号</summary>
          <form class="form-stack" @submit.prevent="deleteAccount">
            <p class="caption">删除会撤销登录和共享。活动库的手账、照片和贴纸会被移除。备份保留周期独立，旧备份里的副本会随轮换到期。识别用量留作历史核算。</p>
            <label class="field">输入当前用户名确认<input v-model="deletion.confirm_username" maxlength="32" autocapitalize="none" required /></label>
            <label class="field">确认密码<input v-model="deletion.password" type="password" maxlength="128" autocomplete="current-password" required /></label>
            <div><button class="button button-danger" :disabled="busy || deletion.confirm_username !== state.username">永久删除账号</button></div>
          </form>
        </details>
      </section>
    </template>
    <p v-if="info" class="caption" role="status">{{ info }}</p>
    <p v-if="error" class="form-error" role="alert">{{ error }}</p>
  </div>
</template>

<style scoped>
.settings-facts div, .session-list li { display: flex; justify-content: space-between; gap: 1rem; align-items: center; padding: .55rem 0; }
.settings-facts dd { margin: 0; overflow-wrap: anywhere; }
.settings-facts dt { min-width: 4rem; }
.session-list { list-style: none; padding: 0; margin: 0; }
.session-list li + li { border-top: 1px solid var(--color-line); }
details { border-top: 1px solid var(--color-line); }
details summary { min-height: var(--tap-size); padding-block: .7rem; font-weight: 600; }
details form { max-width: 28rem; padding: .3rem 0 .85rem; }
.danger summary { color: var(--color-error); }
</style>
