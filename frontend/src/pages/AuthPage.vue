<script setup lang="ts">
import { Eye, EyeOff } from 'lucide-vue-next'
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { authRepository } from '../api/authRepository'
import type { EmailProof, IdentityOptions } from '../api/authRepository'
import DiaryBrand from '../components/DiaryBrand.vue'
import EmailCodeFields from '../components/EmailCodeFields.vue'
import FoodSticker from '../components/FoodSticker.vue'
import { authMessage, useAuth } from '../stores/auth'

const auth = useAuth()
const route = useRoute()
const router = useRouter()
const isRegister = computed(() => route.name === 'register')
const isRecover = computed(() => route.name === 'recover')
const options = ref<IdentityOptions>()
const method = ref<'password' | 'code'>('password')
const proof = ref<EmailProof>({ email: '', request_id: '', code: '' })
const invitation = ref('')
const username = ref('')
const nickname = ref('')
const password = ref('')
const showPassword = ref(false)
const busy = ref(false)
const error = ref('')
const title = computed(() => isRegister.value ? '开始你的手账' : isRecover.value ? '重设密码' : '欢迎回来')
const purpose = computed(() => isRegister.value ? 'register' : isRecover.value ? 'reset' : 'login')
const registrationOpen = computed(() => options.value?.registration !== 'closed')
const useEmailCode = computed(() => isRecover.value || method.value === 'code' || isRegister.value && options.value?.email_available)
const usePassword = computed(() => method.value === 'password' || isRegister.value || isRecover.value)
const sendCode = (email: string) => authRepository.issue(email, purpose.value)

function resetFields() {
  password.value = ''
  proof.value = { email: '', request_id: '', code: '' }
  invitation.value = ''
  showPassword.value = false
  error.value = ''
}

watch(() => route.name, () => {
  method.value = 'password'
  resetFields()
})

onMounted(async () => {
  try { options.value = await authRepository.options() } catch { /* Password login can still be retried. */ }
})

async function submit() {
  if (busy.value) return
  busy.value = true
  error.value = ''
  try {
    const credentials = { username: username.value, password: password.value }
    if (useEmailCode.value && !proof.value.request_id) {
      error.value = '请先发送并填写邮箱验证码。'
    } else if (isRegister.value) {
      const info = { ...credentials, nickname: nickname.value }
      if (useEmailCode.value) {
        await authRepository.registerEmail({ ...info, ...proof.value, invitation: invitation.value || undefined })
      } else {
        await auth.register(info)
      }
      await router.replace({ name: 'login', query: { registered: '1' } })
    } else if (isRecover.value) {
      await authRepository.resetPassword({ ...proof.value, password: password.value })
      await router.replace({ name: 'login', query: { recovered: '1' } })
    } else {
      if (method.value === 'code') await auth.loginEmail(proof.value)
      else await auth.login(credentials)
      await router.replace({ name: 'diary' })
    }
  } catch (failure) {
    error.value = authMessage(failure)
  } finally {
    busy.value = false
    if (method.value === 'code') proof.value.code = ''
  }
}

async function retry() {
  await auth.initialize(true)
  if (auth.isAuthenticated) await router.replace({ name: 'diary' })
}
</script>

<template>
  <main class="auth-layout">
    <div class="auth-brand"><DiaryBrand /></div>
    <div class="auth-spread">
      <section class="auth-form">
        <h1>{{ title }}</h1>
        <p v-if="route.query.registered === '1'" class="caption" role="status">账号已创建，请登录。</p>
        <p v-if="route.query.recovered === '1'" class="caption" role="status">已处理密码重设，请登录。</p>
        <div v-if="auth.sessionNotice && !error" class="session-note">
          <p role="status">{{ auth.sessionNotice }}</p>
          <button v-if="!isRegister" type="button" class="text-action" :disabled="auth.isInitializing" @click="retry">重新检查登录状态</button>
        </div>
        <nav v-if="options?.email_available && !isRegister && !isRecover" class="auth-methods" aria-label="登录方式">
          <button type="button" :aria-pressed="method === 'password'" @click="method = 'password'; resetFields()">密码登录</button>
          <button type="button" :aria-pressed="method === 'code'" @click="method = 'code'; resetFields()">邮箱验证码登录</button>
        </nav>
        <p v-if="isRegister && (!registrationOpen || options?.registration === 'invite' && !options.email_available)" class="caption">当前仅限已有账号登录。</p>
        <form v-else class="form-stack" @submit.prevent="submit">
          <label v-if="isRegister" class="field">昵称<input v-model="nickname" type="text" maxlength="40" autocomplete="nickname" required /></label>
          <label v-if="isRegister || !isRecover && method === 'password'" class="field">{{ isRegister || !options?.email_available ? '用户名' : '用户名或已验证邮箱' }}<input v-model="username"
            type="text" minlength="3" :maxlength="isRegister ? 32 : 254" :pattern="isRegister ? '[a-zA-Z0-9_]+' : undefined" autocomplete="username" autocapitalize="none" required /></label>
          <EmailCodeFields v-if="useEmailCode" :key="purpose" v-model="proof" :send="sendCode" />
          <label v-if="isRegister && options?.registration === 'invite'" class="field">邀请码<input v-model="invitation" maxlength="96" autocomplete="off" required /></label>
          <div v-if="usePassword">
            <label class="field" for="account-password">密码</label>
            <div class="password-field">
              <input id="account-password" v-model="password" :type="showPassword ? 'text' : 'password'" :minlength="isRegister || isRecover ? 12 : 1" maxlength="128"
                :autocomplete="isRegister || isRecover ? 'new-password' : 'current-password'" :aria-describedby="isRegister || isRecover ? 'password-hint' : undefined" required />
              <button type="button" class="icon-button button-quiet" :aria-label="showPassword ? '隐藏密码' : '显示密码'" @click="showPassword = !showPassword">
                <EyeOff v-if="showPassword" /><Eye v-else />
              </button>
            </div>
            <p v-if="isRegister || isRecover" id="password-hint" class="caption">至少 12 个字符。</p>
          </div>
          <p v-if="error" role="alert" class="form-error">{{ error }}</p>
          <button type="submit" class="button button-primary" :disabled="busy">{{ busy ? '正在处理…' : isRegister ? '注册' : isRecover ? '保存新密码' : '登录' }}</button>
        </form>
        <div class="auth-links">
          <RouterLink v-if="isRegister || isRecover || registrationOpen" :to="{ name: isRegister || isRecover ? 'login' : 'register' }" class="text-action">{{ isRegister || isRecover ? '返回登录' : '注册账号' }}</RouterLink>
          <RouterLink v-if="options?.email_available && !isRegister && !isRecover" :to="{ name: 'recover' }" class="text-action">忘记密码</RouterLink>
        </div>
      </section>
      <figure class="auth-cover" aria-hidden="true"><FoodSticker id="croissant" decorative /><FoodSticker id="coffee" decorative /><figcaption>可颂 · 咖啡</figcaption></figure>
    </div>
  </main>
</template>

<style scoped>
.auth-layout { max-width: 65rem; padding: max(1.25rem, env(safe-area-inset-top)) clamp(1.25rem, 6vw, 4.5rem) max(2rem, env(safe-area-inset-bottom)); margin: 0 auto; }
.auth-brand { display: flex; padding: 1rem 0 1.35rem; border-bottom: 1px solid var(--color-line); }
.auth-spread { display: grid; grid-template-columns: minmax(19rem, .94fr) minmax(0, 1fr); gap: clamp(2rem, 7vw, 6rem); align-items: start; padding-top: clamp(2rem, 7vw, 5.5rem); }
.auth-cover { position: relative; margin: 0; background: var(--color-paper-warm); background-image: var(--paper-texture); min-height: 23rem; border: 1px solid var(--color-line); }
.auth-cover .sticker { position: absolute; width: 67%; height: 52%; }
.auth-cover .sticker:first-child { top: 7%; left: 4%; transform: rotate(-12deg); }
.auth-cover .sticker:nth-child(2) { top: 32%; right: 1%; transform: rotate(9deg); }
.auth-cover figcaption { position: absolute; bottom: 1.5rem; left: 1.6rem; color: var(--diary-ink-soft); font: 500 1.12rem var(--font-hand); }
.auth-form { display: grid; gap: 1.1rem; max-width: 28rem; width: 100%; }
.auth-form h1 { font: 700 clamp(1.8rem, 5vw, 2.35rem) var(--font-serif); letter-spacing: -.04em; }
.auth-methods { display: flex; gap: 1.2rem; border-bottom: 1px solid var(--color-line); }
.auth-methods button { min-height: var(--tap-size); text-align: left; font-size: .875rem; color: var(--color-muted); border-bottom: 2px solid transparent; }
.auth-methods button[aria-pressed="true"] { border-bottom-color: var(--color-sage-deep); color: var(--color-ink); }
.auth-links { display: flex; justify-content: space-between; gap: .9rem; }
.password-field { position: relative; margin-top: calc(var(--space-unit) * 3); }
.password-field input { border: 1px solid var(--color-line-warm); border-radius: var(--radius-small); width: 100%; min-height: var(--tap-size); padding-inline: calc(var(--space-unit) * 6) calc(var(--space-unit) * 40); background: var(--color-sheet); }
.password-field .icon-button { position: absolute; right: .1rem; top: 0; }
.session-note { color: var(--color-muted); font-size: .875rem; }
@media (max-width: 640px) {
  .auth-spread { grid-template-columns: minmax(0, 1fr); gap: 1.65rem; }
  .auth-cover { min-height: 11rem; max-width: 28rem; }
  .auth-cover .sticker { width: 49%; height: 82%; }
  .auth-cover .sticker:first-child { top: 5%; left: 8%; }
  .auth-cover .sticker:nth-child(2) { top: 2%; right: 5%; }
  .auth-cover figcaption { bottom: .7rem; left: 1rem; font-size: .9rem; }
}
</style>
