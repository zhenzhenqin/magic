import { onMounted, onScopeDispose, ref } from 'vue'

export function useSharingRefresh(refresh: () => void, period = 25_000) {
  const online = ref(navigator.onLine)
  const foreground = ref(!document.hidden)
  let timer: ReturnType<typeof setInterval> | undefined
  let lastRefresh = 0

  function refreshNow() {
    if (!online.value || document.hidden) return
    lastRefresh = Date.now()
    refresh()
  }
  function run() {
    if (Date.now() - lastRefresh >= 400) refreshNow()
  }
  function updateAvailability(refreshIfAlreadyActive: boolean) {
    const wasActive = online.value && foreground.value
    online.value = navigator.onLine
    foreground.value = !document.hidden
    clearInterval(timer)
    if (!foreground.value || !online.value) return
    // Entering the active state also invalidates each page's private query key.
    if (wasActive && refreshIfAlreadyActive) refreshNow()
    timer = setInterval(run, period)
  }
  const visibility = () => updateAvailability(false)
  const connection = () => updateAvailability(true)
  onMounted(() => {
    window.addEventListener('focus', run)
    window.addEventListener('online', connection)
    window.addEventListener('offline', connection)
    document.addEventListener('visibilitychange', visibility)
    visibility()
  })
  onScopeDispose(() => {
    clearInterval(timer)
    window.removeEventListener('focus', run)
    window.removeEventListener('online', connection)
    window.removeEventListener('offline', connection)
    document.removeEventListener('visibilitychange', visibility)
  })
  return { online, foreground, refresh: refreshNow }
}
