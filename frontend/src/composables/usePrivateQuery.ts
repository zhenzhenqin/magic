import { ref, shallowRef, watch } from 'vue'
import { authMessage } from '../stores/auth'

export function usePrivateQuery<K, T>(key: () => K, load: (key: K, signal: AbortSignal) => Promise<T>) {
  const current = shallowRef<T>()
  const error = ref('')
  const pending = ref(false)
  const revision = ref(0)
  watch([key, revision], async ([value], _, cleanup) => {
    const controller = new AbortController()
    cleanup(() => controller.abort())
    pending.value = true
    error.value = ''
    current.value = undefined
    try {
      const result = await load(value as K, controller.signal)
      if (!controller.signal.aborted) current.value = result
    } catch (failure) {
      if (!controller.signal.aborted) error.value = authMessage(failure)
    } finally {
      if (!controller.signal.aborted) pending.value = false
    }
  }, { immediate: true, flush: 'sync' })
  return { current, error, pending, reload: () => { revision.value++ } }
}
