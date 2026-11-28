<script setup lang="ts">
import { ref, shallowRef, watch } from 'vue'
import { useStickerApi } from '../api/stickerRepository'

const props = defineProps<{ source: string; media?: string; revision?: string | null; extracting: boolean; original: boolean }>()
const stickers = useStickerApi()
const image = ref<HTMLImageElement>()
const sticker = ref('')
const artifact = shallowRef<Blob>()
const revealing = ref(false)
const skipped = ref(false)
const failure = ref(false)
const retry = ref(0)

function skip() { skipped.value = true; revealing.value = false }
function placement() {
  if (!artifact.value || !image.value || props.original) return
  return { blob: artifact.value, from: image.value.getBoundingClientRect().toJSON() as DOMRectInit }
}
defineExpose({ placement })

watch(() => [props.media, props.revision, props.original, retry.value] as const, async ([media, revision, original], _, cleanup) => {
  sticker.value = ''
  artifact.value = undefined
  revealing.value = failure.value = false
  if (!media || !revision || original) return
  const controller = new AbortController()
  let url = ''
  cleanup(() => { controller.abort(); if (url) URL.revokeObjectURL(url) })
  try {
    const requested = performance.now()
    const paper = await stickers.image(media, 'thumbnail', controller.signal)
    if (controller.signal.aborted) return
    const received = performance.now()
    const bitmap = new Image()
    url = URL.createObjectURL(paper)
    bitmap.src = url
    await bitmap.decode()
    if (controller.signal.aborted) return
    const decoded = performance.now()
    performance.clearMeasures('fooddiary-sticker-download')
    performance.clearMeasures('fooddiary-sticker-decode')
    performance.measure('fooddiary-sticker-download', { start: requested, end: received, detail: { bytes: paper.size } })
    performance.measure('fooddiary-sticker-decode', { start: received, end: decoded })
    artifact.value = paper
    revealing.value = !skipped.value && !props.original && !matchMedia('(prefers-reduced-motion: reduce)').matches
    sticker.value = url
  } catch { if (!controller.signal.aborted) failure.value = true }
}, { immediate: true })
</script>

<template>
  <div class="capture-stage" :data-stage="original ? 'original' : revealing ? 'revealing' : sticker ? 'ready' : extracting ? 'extracting' : 'photo'">
    <div class="stage-art" :class="{ 'has-result': !original && !!sticker, revealing, scanning: extracting && !original && !skipped, 'motion-skipped': skipped }">
      <img class="stage-original" :src="source" alt="刚刚拍下的照片" />
      <div v-if="revealing" class="cutout-outline">
        <img :src="sticker" alt="" />
      </div>
      <img v-if="!original && sticker" ref="image" class="stage-sticker" :src="sticker" alt="美食贴纸预览" @animationend.self="revealing = false" @animationcancel.self="revealing = false" />
      <div v-if="extracting && !original && !skipped" class="scan-light" aria-hidden="true"></div>
    </div>
    <div class="stage-tools">
      <p v-if="failure" role="status">贴纸预览暂未载入，仍可保存照片。</p>
      <p v-else-if="!original && extracting" role="status">正在把美食剪下来…</p>
      <p v-else-if="!original && sticker" role="status">美食贴纸做好啦。</p>
      <button v-if="failure" type="button" class="text-action" @click="retry++">重新载入贴纸</button>
      <button v-else-if="!skipped && !original && (extracting || revealing)" type="button" class="text-action skip-motion" @click="skip">跳过特效</button>
    </div>
  </div>
</template>

<style scoped>
.stage-art { display: grid; place-items: center; position: relative; isolation: isolate; overflow: hidden; height: clamp(12rem, 34vh, 21rem); background: var(--color-paper-warm); border: 1px solid var(--color-line); }
.stage-art img { grid-area: 1 / 1; max-width: 100%; width: auto; height: 100%; min-height: 0; max-height: 100%; object-fit: contain; }
.stage-original { animation: freeze .18s ease-out both; }
.has-result .stage-original { visibility: hidden; }
.stage-art.revealing .stage-original { visibility: visible; animation: fade-original .56s .18s ease both; }
.cutout-outline { position: absolute; width: 100%; height: 100%; inset: 0; display: grid; place-items: center; opacity: 0; animation: contour .69s ease both; }
.cutout-outline img { filter: drop-shadow(0 0 2px #fff) drop-shadow(0 0 4px #fff) drop-shadow(0 0 5px #fff); }
.stage-sticker { filter: drop-shadow(0 3px 4px #42362b28); transform: rotate(-3deg); }
.revealing .stage-sticker { animation: form-sticker .95s cubic-bezier(.2,.63,.27,1) both; }
.scan-light { position: absolute; inset: 0; pointer-events: none; background: linear-gradient(180deg, transparent 40%, #fff6 50%, transparent 60%) center / 100% 240%; animation: scan 2.3s ease-in-out infinite alternate; }
.stage-tools { display: flex; align-items: baseline; justify-content: space-between; gap: .45rem; padding-top: .4rem; color: var(--color-muted); font-size: .8rem; }
.stage-tools > button { min-height: 1.9rem; font-size: inherit; }
@keyframes freeze { from { opacity: .56; transform: scale(1.015); } }
@keyframes fade-original { to { opacity: 0; } }
@keyframes contour { 0%, 100% { opacity: 0; } 57% { opacity: 1; } }
@keyframes form-sticker { 0%, 32% { opacity: 0; transform: translateY(5%) scale(.91); } 76% { opacity: 1; transform: translateY(-1%) rotate(-4deg) scale(1.025); } }
@keyframes scan { from { transform: translateY(-65%); } to { transform: translateY(65%); } }
.motion-skipped img { animation: none; }
@media (prefers-reduced-motion: reduce) { .stage-art *, .stage-art.revealing * { animation: none; } .scan-light, .skip-motion { display: none; } }
</style>
