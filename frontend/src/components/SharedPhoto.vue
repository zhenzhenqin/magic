<script setup lang="ts">
import { ImageOff } from 'lucide-vue-next'
import { computed, ref, watch } from 'vue'
import { useSharingApi } from '../api/sharingRepository'
import type { MediaContext, MediaKind, SharedMedia } from '../api/sharingRepository'

const props = defineProps<{ owner: string; media: SharedMedia; context: MediaContext; kind?: MediaKind; full?: boolean }>()
const api = useSharingApi()
const frame = ref<HTMLElement>()
const visible = ref(false)
const failed = ref(false)
const url = ref('')
const kind = computed(() => props.kind ?? props.media.kinds[0])
const tilt = computed(() => (Array.from(props.media.id).reduce((sum, token) => sum + token.charCodeAt(0), 0) % 7 - 3) + 'deg')
watch(frame, (element, _, cleanup) => {
  if (!element) return
  const observer = new IntersectionObserver(entries => {
    if (entries.some(entry => entry.isIntersecting)) { visible.value = true; observer.disconnect() }
  }, { rootMargin: '100px' })
  observer.observe(element)
  cleanup(() => observer.disconnect())
}, { flush: 'post' })

watch(() => [props.owner, props.media.id, kind.value, props.full, props.context.meal_id, props.context.catalog_id, visible.value] as const,
  async ([owner, media, variant, full, , , active], _, cleanup) => {
    let objectUrl = ''
    const controller = new AbortController()
    cleanup(() => {
      controller.abort()
      if (objectUrl) URL.revokeObjectURL(objectUrl)
      url.value = ''
    })
    failed.value = false
    if (!active || !variant || !props.media.kinds.includes(variant)) return
    try {
      const blob = await api.media(owner, media, variant, !full, props.context, controller.signal)
      if (!controller.signal.aborted) {
        objectUrl = URL.createObjectURL(blob)
        url.value = objectUrl
      }
    } catch {
      if (!controller.signal.aborted) failed.value = true
    }
  }, { immediate: true })
</script>

<template>
  <span ref="frame" class="shared-photo" :class="{ sticker: kind === 'sticker' }" :style="{ '--tilt': tilt }">
    <img v-if="url" :src="url" :alt="kind === 'sticker' ? '共享美食贴纸' : '共享照片'" decoding="async" />
    <span v-else-if="failed" class="photo-missing" role="status"><ImageOff aria-hidden="true" />{{ kind === 'sticker' ? '贴纸暂不可用' : '照片暂不可用' }}</span>
  </span>
</template>

<style scoped>
.shared-photo { display: grid; grid-template: minmax(0, 1fr) / minmax(0, 1fr); place-items: center; width: 100%; height: 100%; min-width: 0; min-height: 0; padding: .2rem; }
img { width: 100%; height: 100%; min-width: 0; min-height: 0; object-fit: contain; border-radius: .38rem; }
.sticker img { border-radius: 0; transform: rotate(var(--tilt)); filter: drop-shadow(0 2px 2px #503f3030); }
.photo-missing { display: grid; justify-items: center; gap: .25rem; color: var(--color-muted); font-size: .7rem; }
.photo-missing svg { width: 1rem; }
</style>
