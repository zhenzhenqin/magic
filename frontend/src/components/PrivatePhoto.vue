<script setup lang="ts">
import { ImageOff } from 'lucide-vue-next'
import { computed, ref, watch } from 'vue'
import { ApiError } from '../api/client'
import { useDiaryApi } from '../api/diaryRepository'
import { stickerRunning, useStickerApi } from '../api/stickerRepository'

const props = defineProps<{
  id: string; original?: boolean; alt?: string; presentation?: 'sticker' | 'thumbnail' | 'cutout'; revision?: string | null; natural?: boolean
}>()
const api = useDiaryApi()
const stickers = useStickerApi()
const frame = ref<HTMLElement>()
const visible = ref(false)
const url = ref('')
const failed = ref(false)
const isSticker = ref(false)
const angle = computed(() => String((Array.from(props.id).reduce((value, char) => value + char.charCodeAt(0), 0) % 9) - 4) + 'deg')

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

watch(() => [props.id, props.original, props.presentation, props.revision, visible.value] as const, async ([id, original, presentation, , active], _, cleanup) => {
  const controller = new AbortController()
  const signal = controller.signal
  let acquired = ''
  let timer: ReturnType<typeof setTimeout> | undefined
  cleanup(() => {
    controller.abort()
    clearTimeout(timer)
    if (acquired) URL.revokeObjectURL(acquired)
    url.value = ''
  })
  failed.value = false
  isSticker.value = false
  if (!active) return
  function show(blob: Blob, derived: boolean) {
    if (signal.aborted) return
    if (acquired) URL.revokeObjectURL(acquired)
    acquired = URL.createObjectURL(blob)
    url.value = acquired
    isSticker.value = derived
  }
  async function loadSticker() {
    if (!presentation || signal.aborted) return false
    try {
      show(await stickers.image(id, presentation, signal), true)
      return !signal.aborted
    } catch (error) {
      if (signal.aborted || (error instanceof ApiError && error.status === 404)) return false
      throw error
    }
  }
  async function check() {
    try {
      if (await loadSticker()) return
      if (!signal.aborted && stickerRunning(await stickers.source(id, signal))) timer = setTimeout(check, 2500)
    } catch { /* Keep the last available image when a refresh fails. */ }
  }
  try {
    if (await loadSticker()) return
    if (presentation === 'cutout') { failed.value = true; return }
    show(await api.photo(id, Boolean(original), signal), false)
    if (presentation && !signal.aborted && stickerRunning(await stickers.source(id, signal))) timer = setTimeout(check, 2500)
  } catch {
    if (!signal.aborted && !url.value) failed.value = true
  }
}, { immediate: true })
</script>

<template>
  <span ref="frame" class="private-photo" :class="{ 'sticker-frame': presentation, 'has-sticker': isSticker, 'raw-cutout': presentation === 'cutout', natural }"
    :data-sticker="isSticker || undefined" :style="{ '--tilt': angle }">
    <img v-if="url" :src="url" :alt="alt ?? '记录照片'" decoding="async" />
    <span v-else-if="failed" class="photo-fallback" role="status"><ImageOff aria-hidden="true" /> 图片暂不可用</span>
  </span>
</template>

<style scoped>
.private-photo { display: grid; place-items: center; width: 100%; height: 100%; min-height: 0; aspect-ratio: 4/3; overflow: hidden; border-radius: var(--radius-small); background: var(--color-canvas-hover); }
img { width: 100%; height: 100%; min-height: 0; object-fit: cover; }
.photo-fallback { display: grid; place-items: center; gap: .2rem; text-align: center; color: var(--color-muted); font-size: .72rem; }
.photo-fallback svg { width: 1rem; }
.sticker-frame { overflow: visible; background: transparent; aspect-ratio: auto; min-width: 0; }
.sticker-frame img { width: auto; height: auto; max-height: 100%; max-width: 100%; object-fit: contain; transform: rotate(var(--tilt)); filter: drop-shadow(0 2px 2px #4e382528); }
.sticker-frame:not(.has-sticker) img { border-radius: .45rem; }
.raw-cutout img { transform: none; filter: none; }
.natural { height: auto; aspect-ratio: auto; }
.natural img { height: auto; }
</style>
