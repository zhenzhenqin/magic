import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { authRepository } from '../api/authRepository'
import { ApiError, request } from '../api/client'
import type { RequestOptions } from '../api/client'
import type { AuthSession, UserPreferences, UserProfile } from '../api/authRepository'

async function serializeSession<T>(work: () => Promise<T>): Promise<T> {
  return navigator.locks ? await navigator.locks.request('fooddiary-api-auth-session', work) : work()
}

export function authMessage(error: unknown) {
  return error instanceof ApiError ? error.message : '操作暂未完成，请稍后重试。'
}

const pausedKey = 'fooddiary.api.identity-paused'

function tabPause(value?: boolean) {
  try {
    if (value === true) sessionStorage.setItem(pausedKey, '1')
    if (value === false) sessionStorage.removeItem(pausedKey)
    return sessionStorage.getItem(pausedKey) === '1'
  } catch {
    return false
  }
}

export const useAuth = defineStore('api-auth', () => {
  const currentUser = ref<UserProfile | null>(null)
  const preferences = ref<UserPreferences | null>(null)
  const isAuthenticated = computed(() => currentUser.value !== null)
  const isInitializing = ref(true)
  const sessionNotice = ref('')
  let access: string | undefined
  let generation = 0
  let refreshing: Promise<boolean> | undefined
  let restoring: Promise<void> | undefined
  let accountScope = new AbortController()
  const channel = typeof BroadcastChannel === 'undefined' ? undefined : new BroadcastChannel('fooddiary-api-identity')
  channel?.addEventListener('message', ({ data }) => {
    if (currentUser.value && (data?.type === 'login' || (data?.type === 'logout' && data.owner === currentUser.value.public_id))) {
      tabPause(true)
      clear('登录状态在另一个标签页中已变更，请重新登录。')
    }
  })

  function clear(notice = '') {
    generation++
    accountScope.abort()
    accountScope = new AbortController()
    access = undefined
    currentUser.value = null
    preferences.value = null
    sessionNotice.value = notice
  }

  function apply(session: AuthSession) {
    access = session.access_token
    currentUser.value = session.user
    sessionNotice.value = ''
  }

  function refresh(): Promise<boolean> {
    if (refreshing) return refreshing
    const previous = currentUser.value?.public_id
    const epoch = generation
    refreshing = serializeSession(async () => {
      if (epoch !== generation) return false
      try {
        let session: AuthSession
        try {
          session = await authRepository.refresh(access)
        } catch (error) {
          if (!(error instanceof ApiError) || error.code !== 'refresh_in_progress') throw error
          await new Promise(resolve => setTimeout(resolve, 300))
          if (epoch !== generation) return false
          session = await authRepository.refresh(access)
        }
        if (epoch !== generation) return false
        if (previous && session.user.public_id !== previous) {
          tabPause(true)
          clear('此浏览器的登录账号已变更，请重新登录。')
          return false
        }
        apply(session)
        return true
      } catch (error) {
        if (epoch !== generation) return false
        if (error instanceof ApiError && error.status === 401) {
          if (previous) tabPause(true)
          clear(previous ? error.message : '')
          return false
        }
        throw error
      }
    }).finally(() => { refreshing = undefined })
    return refreshing
  }

  function initialize(retry = false): Promise<void> {
    if (restoring) return restoring
    if (!isInitializing.value && !retry) return Promise.resolve()
    if (!retry && tabPause()) {
      isInitializing.value = false
      sessionNotice.value = '登录状态已变更，请重新确认当前账号。'
      return Promise.resolve()
    }
    if (retry) tabPause(false)
    isInitializing.value = true
    restoring = refresh()
      .then(() => {})
      .catch(error => { sessionNotice.value = authMessage(error) })
      .finally(() => { isInitializing.value = false; restoring = undefined })
    return restoring
  }

  async function login(data: { username: string; password: string }) {
    await serializeSession(async () => {
      const session = await authRepository.login(data)
      tabPause(false)
      clear()
      apply(session)
      channel?.postMessage({ type: 'login' })
    })
  }

  async function logout() {
    await serializeSession(async () => {
      if (!access) return
      const owner = currentUser.value?.public_id
      await authRepository.logout(access)
      tabPause(false)
      clear()
      channel?.postMessage({ type: 'logout', owner })
    })
  }

  async function authenticated<T>(work: (token: string, scope: AbortSignal) => Promise<T>): Promise<T> {
    const epoch = generation
    const requestedToken = access
    const scope = accountScope.signal
    const ended = () => new ApiError(401, 'invalid_session', '登录已失效，请重新登录。')
    if (!requestedToken) throw ended()
    try {
      const result = await work(requestedToken, scope)
      if (epoch !== generation) throw ended()
      return result
    } catch (error) {
      if (epoch !== generation || !(error instanceof ApiError) || error.status !== 401) throw error
      if (access === requestedToken && !await refresh()) throw ended()
      if (!access || epoch !== generation) throw ended()
      try {
        const result = await work(access, scope)
        if (epoch !== generation) throw ended()
        return result
      } catch (retried) {
        if (epoch === generation && retried instanceof ApiError && retried.status === 401) clear(retried.message)
        throw retried
      }
    }
  }

  function api<T>(path: string, options: RequestOptions = {}) {
    return authenticated((token, scope) => {
      const signal = options.signal ? AbortSignal.any([scope, options.signal]) : scope
      return request<T>(path, { ...options, signal }, token)
    })
  }

  async function loadProfile() {
    currentUser.value = await api<UserProfile>('/users/me')
  }
  async function updateProfile(nickname: string) {
    currentUser.value = await api<UserProfile>('/users/me', { method: 'PATCH', body: { nickname } })
  }

  return {
    currentUser, preferences, isAuthenticated, isInitializing, sessionNotice, initialize, login, logout, refresh,
    register: authRepository.register, loadProfile, updateProfile, api,
    loadPreferences: async () => preferences.value = await api<UserPreferences>('/users/me/settings'),
    updatePreferences: async (data: UserPreferences) => preferences.value = await api<UserPreferences>('/users/me/settings', { method: 'PATCH', body: data }),
  }
})
