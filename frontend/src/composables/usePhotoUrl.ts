import { onScopeDispose, ref, watch } from 'vue'
import { mediaRepository } from '../api/mediaRepository'

export function usePhotoUrl(assetId: () => string | undefined) {
  const url = ref('')
  let request = 0
  function clear() {
    if (url.value) URL.revokeObjectURL(url.value)
    url.value = ''
  }
  watch(assetId, async id => {
    const token = ++request
    clear()
    if (!id) return
    const image = await mediaRepository.get(id).catch(() => undefined)
    if (image && token === request) url.value = URL.createObjectURL(image)
  }, { immediate: true })
  onScopeDispose(() => {
    request++
    clear()
  })
  return url
}
