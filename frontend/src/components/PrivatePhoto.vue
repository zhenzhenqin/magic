<script setup lang="ts">
import { ImageOff } from 'lucide-vue-next'
import { ref, watch } from 'vue'
import { useDiaryApi } from '../api/diaryRepository'

const props = defineProps<{ id: string; original?: boolean; alt?: string }>()
const api = useDiaryApi()
const frame = ref<HTMLElement>()
const visible = ref(false)
const url = ref('')
const failed = ref(false)

watch(frame, (element, _, cleanup) => {
  if (!element) return
  const watcher = new IntersectionObserver(entries => {
    if (entries.some(entry => entry.isIntersecting)) {
      visible.value = true
      watcher.disconnect()
    }
  }, { rootMargin: '180px' })
  watcher.observe(element)
  cleanup(() => watcher.disconnect())
}, { flush: 'post' })

watch(() => [props.id, props.original, visible.value] as const, async ([id, original, active], _, cleanup) => {
  const controller = new AbortController()
  let acquired = ''
  cleanup(() => {
    controller.abort()
    if (acquired) URL.revokeObjectURL(acquired)
    url.value = ''
  })
  failed.value = false
  if (!active) return
  try {
    const blob = await api.photo(id, Boolean(original), controller.signal)
    if (controller.signal.aborted) return
    acquired = URL.createObjectURL(blob)
    url.value = acquired
  } catch {
    if (!controller.signal.aborted) failed.value = true
  }
}, { immediate: true })
</script>

<template>
  <span ref="frame" class="private-photo">
    <img v-if="url" :src="url" :alt="alt ?? '记录照片'" decoding="async" />
    <span v-else-if="failed" class="photo-fallback" role="status"><ImageOff aria-hidden="true" /> 图片暂不可用</span>
  </span>
</template>

<style scoped>
.private-photo { display: grid; place-items: center; width: 100%; height: 100%; min-height: 0; aspect-ratio: 4/3; overflow: hidden; border-radius: var(--radius-small); background: var(--color-canvas-hover); }
img { width: 100%; height: 100%; min-height: 0; object-fit: cover; }
.photo-fallback { display: grid; place-items: center; gap: .2rem; text-align: center; color: var(--color-muted); font-size: .72rem; }
.photo-fallback svg { width: 1rem; }
</style>
