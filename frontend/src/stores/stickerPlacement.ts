import { defineStore } from 'pinia'
import { shallowRef, watch } from 'vue'
import { useAuth } from './auth'

interface Placement { meal: string; media: string; blob: Blob; from: DOMRectInit }

export const useStickerPlacement = defineStore('sticker-placement', () => {
  const auth = useAuth()
  const pending = shallowRef<Placement>()
  let expiration: ReturnType<typeof setTimeout> | undefined
  function clear() { clearTimeout(expiration); pending.value = undefined }
  function offer(placement: Placement) {
    clear()
    pending.value = placement
    expiration = setTimeout(clear, 5000)
  }
  watch(() => auth.currentUser?.public_id, clear, { flush: 'sync' })
  return { pending, offer, clear }
})
