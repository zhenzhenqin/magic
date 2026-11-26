import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { ApiError, authRepository } from '../api/authRepository'
import type { AuthSession, UserPreferences, UserProfile } from '../api/authRepository'

async function serializeSession<T>(work: () => Promise<T>): Promise<T> {
  return navigator.locks ? await navigator.locks.request('fooddiary-api-auth-session', work) : work()
}

export function authMessage(error: unknown) {
  return error instanceof ApiError ? error.message : '操作暂未完成，请稍后重试。'
}

export const useAuth = defineStore('api-auth', () => {
  const currentUser = ref<UserProfile | null>(null)
  const isAuthenticated = computed(() => currentUser.value !== null)
  const isInitializing = ref(true)
  const sessionNotice = ref('')
  let access: string | undefined
  let generation = 0
  let refreshing: Promise<boolean> | undefined
  let restoring: Promise<void> | undefined

  function clear(notice = '') {
    generation++
    access = undefined
    currentUser.value = null
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
          session = await authRepository.refresh()
        } catch (error) {
          if (!(error instanceof ApiError) || error.code !== 'refresh_in_progress') throw error
          await new Promise(resolve => setTimeout(resolve, 300))
          session = await authRepository.refresh()
        }
        if (epoch !== generation) return false
        if (previous && session.user.public_id !== previous) {
          clear('此浏览器的登录账号已变更，请重新登录。')
          return false
        }
        apply(session)
        return true
      } catch (error) {
        if (epoch !== generation) return false
        if (error instanceof ApiError && error.status === 401) {
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
      clear()
      apply(session)
    })
  }

  async function logout() {
    await serializeSession(async () => {
      await authRepository.logout(access)
      clear()
    })
  }

  async function authenticated<T>(work: (token: string) => Promise<T>): Promise<T> {
    const epoch = generation
    const requestedToken = access
    const ended = () => new ApiError(401, 'invalid_session', '登录已失效，请重新登录。')
    if (!requestedToken) throw ended()
    try {
      const result = await work(requestedToken)
      if (epoch !== generation) throw ended()
      return result
    } catch (error) {
      if (epoch !== generation || !(error instanceof ApiError) || error.status !== 401) throw error
      if (access === requestedToken && !await refresh()) throw ended()
      if (!access || epoch !== generation) throw ended()
      try {
        const result = await work(access)
        if (epoch !== generation) throw ended()
        return result
      } catch (retried) {
        if (epoch === generation && retried instanceof ApiError && retried.status === 401) clear(retried.message)
        throw retried
      }
    }
  }

  async function loadProfile() {
    currentUser.value = await authenticated(authRepository.profile)
  }
  async function updateProfile(nickname: string) {
    currentUser.value = await authenticated(token => authRepository.updateProfile(token, nickname))
  }

  return {
    currentUser, isAuthenticated, isInitializing, sessionNotice, initialize, login, logout, refresh,
    register: authRepository.register, loadProfile, updateProfile,
    loadPreferences: () => authenticated(authRepository.preferences),
    updatePreferences: (data: UserPreferences) => authenticated(token => authRepository.updatePreferences(token, data)),
  }
})
