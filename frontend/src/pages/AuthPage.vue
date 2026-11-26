<script setup lang="ts">
import { Eye, EyeOff, Sprout } from 'lucide-vue-next'
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import FoodSticker from '../components/FoodSticker.vue'
import { authMessage, useAuth } from '../stores/auth'

const auth = useAuth()
const route = useRoute()
const router = useRouter()
const isRegister = computed(() => route.name === 'register')
const username = ref('')
const nickname = ref('')
const password = ref('')
const showPassword = ref(false)
const busy = ref(false)
const error = ref('')
const title = computed(() => isRegister.value ? '开始你的手账' : '欢迎回来')

watch(() => route.name, () => {
  password.value = ''
  showPassword.value = false
  error.value = ''
})

async function submit() {
  if (busy.value) return
  busy.value = true
  error.value = ''
  try {
    const credentials = { username: username.value, password: password.value }
    if (isRegister.value) {
      await auth.register({ ...credentials, nickname: nickname.value })
      await router.replace({ name: 'login', query: { registered: '1' } })
    } else {
      await auth.login(credentials)
      await router.replace({ name: 'diary' })
    }
  } catch (failure) {
    error.value = authMessage(failure)
  } finally {
    busy.value = false
  }
}

async function retry() {
  await auth.initialize(true)
  if (auth.isAuthenticated) await router.replace({ name: 'diary' })
}
</script>

<template>
  <main class="auth-layout">
    <div class="auth-brand"><span><Sprout aria-hidden="true" /></span>FoodDiary</div>
    <div class="auth-spread paper-panel">
      <div class="auth-cover" aria-hidden="true">
        <FoodSticker id="croissant" decorative />
        <FoodSticker id="coffee" decorative />
      </div>
      <section class="auth-form">
        <h1>{{ title }}</h1>
        <p class="caption">{{ isRegister ? '创建一个账号，留住日常的好味道。' : '登录后继续写你的私人美食手账。' }}</p>
        <p v-if="route.query.registered === '1'" class="badge" role="status">账号已创建，请登录。</p>
        <div v-if="auth.sessionNotice && !error" class="session-note">
          <p role="status">{{ auth.sessionNotice }}</p>
          <button v-if="!isRegister" type="button" class="text-action" :disabled="auth.isInitializing" @click="retry">重新检查登录状态</button>
        </div>
        <form class="form-stack" @submit.prevent="submit">
          <label v-if="isRegister" class="field">昵称<input v-model="nickname" type="text" maxlength="40" autocomplete="nickname" required /></label>
          <label class="field">用户名<input v-model="username" type="text" minlength="3" maxlength="32" pattern="[a-zA-Z0-9_]+" autocomplete="username" autocapitalize="none" required /></label>
          <div>
            <label class="field" for="account-password">密码</label>
            <div class="password-field">
              <input id="account-password" v-model="password" :type="showPassword ? 'text' : 'password'" :minlength="isRegister ? 12 : 1" maxlength="128"
                :autocomplete="isRegister ? 'new-password' : 'current-password'" :aria-describedby="isRegister ? 'password-hint' : undefined" required />
              <button type="button" class="icon-button button-quiet" :aria-label="showPassword ? '隐藏密码' : '显示密码'" @click="showPassword = !showPassword">
                <EyeOff v-if="showPassword" /><Eye v-else />
              </button>
            </div>
            <p v-if="isRegister" id="password-hint" class="caption">至少 12 个字符。</p>
          </div>
          <p v-if="error" role="alert" class="form-error">{{ error }}</p>
          <button type="submit" class="button button-primary" :disabled="busy">{{ busy ? (isRegister ? '正在注册…' : '正在登录…') : (isRegister ? '注册' : '登录') }}</button>
        </form>
        <RouterLink :to="{ name: isRegister ? 'login' : 'register' }" class="text-action">{{ isRegister ? '已有账号，去登录' : '没有账号，去注册' }}</RouterLink>
      </section>
    </div>
  </main>
</template>

<style scoped>
.auth-layout { max-width: 62rem; padding: clamp(1rem, 5vw, 3rem); margin: 0 auto; }
.auth-brand { display: flex; align-items: center; gap: calc(var(--space-unit) * 6); margin-bottom: calc(var(--space-unit) * 16); font: 700 1.65rem var(--font-editorial); }
.auth-brand span { display: grid; place-items: center; width: 2.4rem; height: 2.4rem; border-radius: var(--radius-brand); background: var(--color-sage-deep); color: var(--color-sheet); transform: rotate(-6deg); }
.auth-brand svg { width: 1.4rem; }
.auth-spread { display: grid; grid-template-columns: .85fr minmax(0, 1fr); overflow: hidden; }
.auth-cover { position: relative; background: var(--color-paper-warm); background-image: var(--paper-texture); min-height: 24rem; }
.auth-cover .sticker { position: absolute; width: 79%; height: 49%; }
.auth-cover .sticker:first-child { top: 9%; left: 6%; transform: rotate(-16deg); }
.auth-cover .sticker:last-child { top: 43%; right: 1%; transform: rotate(11deg); }
.auth-form { display: grid; gap: calc(var(--space-unit) * 7); padding: clamp(1.15rem, 4vw, 2.6rem); }
.auth-form h1 { font: 700 clamp(1.9rem, 5vw, 2.85rem) var(--font-serif); }
.auth-form .badge { justify-self: start; }
.password-field { position: relative; margin-top: calc(var(--space-unit) * 3); }
.password-field input { border: 1px solid var(--color-line-warm); border-radius: var(--radius-small); width: 100%; min-height: var(--tap-size); padding-inline: calc(var(--space-unit) * 6) calc(var(--space-unit) * 40); background: var(--color-sheet); }
.password-field .icon-button { position: absolute; right: .1rem; top: 0; }
.session-note { color: var(--color-muted); font-size: .875rem; }
@media (max-width: 640px) {
  .auth-spread { grid-template-columns: minmax(0, 1fr); }
  .auth-cover { min-height: 8.2rem; }
  .auth-cover .sticker { width: 42%; height: 97%; }
  .auth-cover .sticker:first-child { top: 1%; left: 13%; }
  .auth-cover .sticker:last-child { top: 1%; right: 10%; }
}
</style>
