<script setup lang="ts">
import { Camera, Images, RotateCcw, X, Zap } from 'lucide-vue-next'
import { nextTick, onMounted, onScopeDispose, ref, shallowRef } from 'vue'
import { webCamera } from '../camera/provider'
import type { CameraProvider, CameraSession, CapturedPhoto, Facing } from '../camera/provider'

const { provider = webCamera } = defineProps<{ provider?: CameraProvider }>()
const emit = defineEmits<{ photo: [photo: CapturedPhoto]; close: []; manual: [] }>()
const dialog = ref<HTMLDialogElement>()
const preview = ref<HTMLVideoElement>()
const album = ref<HTMLInputElement>()
const system = ref<HTMLInputElement>()
const facing = ref<Facing>('environment')
const session = shallowRef<CameraSession>()
const state = ref<'opening' | 'preview' | 'capturing' | 'paused' | 'unavailable'>('opening')
const torch = ref(false)
const ratio = ref(4 / 3)
const online = ref(navigator.onLine)
const note = ref('')
let pending: AbortController | undefined
let disposed = false
let selecting = false

function release() {
  pending?.abort()
  pending = undefined
  session.value?.close()
  session.value = undefined
  torch.value = false
}

async function open() {
  release()
  if (document.hidden) { state.value = 'paused'; return }
  if (!provider.available()) {
    state.value = 'unavailable'
    note.value = window.isSecureContext ? '当前浏览器无法直接访问相机。' : '实时取景需要可信 HTTPS。'
    return
  }
  const attempt = new AbortController()
  pending = attempt
  state.value = 'opening'
  note.value = ''
  try {
    const opened = await provider.open(facing.value, attempt.signal)
    if (attempt.signal.aborted) { opened.close(); return }
    session.value = opened
    await nextTick()
    if (!attempt.signal.aborted && preview.value) opened.attach(preview.value)
  } catch (error) {
    if (attempt.signal.aborted) return
    state.value = 'unavailable'
    const code = error instanceof DOMException ? error.name : ''
    note.value = ({ NotAllowedError: '相机权限未开启，可以在浏览器设置里允许相机。',
      NotFoundError: '没有找到可用的摄像头。', NotReadableError: '摄像头暂时不可用，可能正被其他应用使用。' } as Record<string, string>)[code]
      ?? '暂时无法打开摄像头。'
  }
}

function pause() {
  if (state.value === 'unavailable' || state.value === 'paused') return
  release()
  state.value = 'paused'
}
function visibility() { if (document.hidden) pause() }
function network() { online.value = navigator.onLine }
function changeLens() {
  facing.value = facing.value === 'environment' ? 'user' : 'environment'
  void open()
}
function playing() {
  const video = preview.value
  if (!session.value || !video?.videoHeight || video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA) return
  ratio.value = video.videoWidth / video.videoHeight
  if (state.value === 'opening') state.value = 'preview'
}
async function toggleTorch() {
  const current = session.value
  try {
    if (!current?.torch) return
    const enabled = !torch.value
    await current.torch(enabled)
    if (current === session.value) torch.value = enabled
  } catch { if (current === session.value) note.value = '当前摄像头无法打开补光。' }
}
async function capture() {
  const current = session.value
  if (state.value !== 'preview' || !preview.value || !current || selecting) return
  state.value = 'capturing'
  try {
    const photo = await current.capture(preview.value)
    if (current !== session.value || disposed) return
    release()
    emit('photo', photo)
  } catch {
    if (current !== session.value || disposed) return
    state.value = 'preview'
    note.value = '这张照片没有拍下来，请再试一次。'
  }
}
async function selected(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file || selecting) return
  selecting = true
  try {
    const photo = await provider.select(file)
    if (disposed) return
    release()
    emit('photo', photo)
  } catch { if (!disposed) note.value = '无法读取这张图片，请选择 JPEG、PNG 或 WebP。' }
  finally { selecting = false }
}

onMounted(() => {
  dialog.value?.showModal()
  document.addEventListener('visibilitychange', visibility)
  window.addEventListener('pagehide', pause)
  window.addEventListener('online', network)
  window.addEventListener('offline', network)
  void open()
})
onScopeDispose(() => {
  disposed = true
  release()
  document.removeEventListener('visibilitychange', visibility)
  window.removeEventListener('pagehide', pause)
  window.removeEventListener('online', network)
  window.removeEventListener('offline', network)
})
</script>

<template>
  <dialog ref="dialog" class="camera" aria-labelledby="camera-title" @cancel.prevent="emit('close')">
    <div class="camera-shell">
      <header class="camera-top">
        <button type="button" aria-label="关闭相机" @click="emit('close')"><X /></button>
        <h1 id="camera-title">拍下这一餐</h1>
        <button v-if="session?.torch" type="button" aria-label="补光灯" :aria-pressed="torch" @click="toggleTorch"><Zap /></button>
        <span v-else aria-hidden="true"></span>
      </header>
      <div class="viewfinder" :class="{ live: state === 'preview' || state === 'capturing' }">
        <video ref="preview" autoplay muted playsinline aria-label="实时摄像头预览" @playing="playing" @resize="playing" />
        <div v-if="state === 'preview' || state === 'capturing'" class="frame" :style="{ '--camera-ratio': ratio }" aria-hidden="true"><i/><i/><i/><i/></div>
        <div v-else class="camera-message">
          <Camera aria-hidden="true" />
          <p role="status">{{ state === 'opening' ? '正在打开相机…' : state === 'paused' ? '相机已暂停。' : note }}</p>
          <button v-if="state === 'paused' || (state === 'unavailable' && provider.available())" type="button" class="camera-pill" @click="open">{{ state === 'paused' ? '继续取景' : '重试相机' }}</button>
          <button v-if="state === 'unavailable'" type="button" class="camera-pill" @click="system?.click()">使用系统相机</button>
        </div>
      </div>
      <p v-if="state !== 'unavailable'" class="camera-hint" :role="!online || note ? 'status' : undefined">{{ !online ? '网络已断开，拍摄后可重试上传。' : note || '对准食物，按下快门后上传到私有手账草稿。' }}</p>
      <footer class="camera-bottom">
        <button type="button" @click="album?.click()"><Images /> <span>相册</span></button>
        <button type="button" class="shutter" aria-label="按下快门" :disabled="state !== 'preview'" @click="capture"><span /></button>
        <button type="button" aria-label="切换摄像头" :disabled="state !== 'preview'" @click="changeLens"><RotateCcw /> <span>翻转</span></button>
        <button type="button" class="manual" @click="emit('manual')">手动记录</button>
      </footer>
      <input ref="album" type="file" accept="image/*" aria-label="从相册选择" hidden @change="selected" />
      <input ref="system" type="file" accept="image/*" capture="environment" aria-label="系统相机照片" hidden @change="selected" />
    </div>
  </dialog>
</template>

<style scoped>
.camera { position: fixed; inset: 0; margin: 0; padding: 0; border: 0; width: 100%; max-width: none; height: 100%; height: 100dvh; max-height: none; background: #111; color: #fffdf6; }
.camera::backdrop { background: #111; }
.camera-shell { max-width: 47rem; height: 100%; min-height: 20rem; margin: auto; padding: max(.48rem, env(safe-area-inset-top)) max(.75rem, env(safe-area-inset-right)) max(.4rem, env(safe-area-inset-bottom)) max(.75rem, env(safe-area-inset-left)); display: grid; grid-template-rows: auto minmax(0, 1fr) auto auto; }
.camera-top, .camera-bottom { display: grid; grid-template-columns: 1fr 1.8fr 1fr; align-items: center; text-align: center; }
.camera-top h1 { font: 600 1.06rem var(--font-sans); white-space: nowrap; }
.camera-top button:last-child { justify-self: end; }
button { color: inherit; min-width: 2.75rem; min-height: 2.75rem; }
button:focus-visible { outline: 2px solid white; outline-offset: 2px; }
button:disabled { opacity: .4; }
.camera-top button, .camera-bottom button { display: grid; place-items: center; justify-self: center; }
.camera-top button:first-child { justify-self: start; }
.viewfinder { grid-row: 2; position: relative; min-height: 0; isolation: isolate; overflow: hidden; container-type: size; border-radius: .9rem; background: #211f1d; }
.viewfinder video { width: 100%; height: 100%; display: block; object-fit: contain; opacity: 0; background: #080808; }
.viewfinder.live video { opacity: 1; }
.camera-message { position: absolute; inset: 0; display: flex; flex-direction: column; justify-content: center; align-items: center; gap: .55rem; padding: .75rem; text-align: center; }
.camera-message > svg { width: 1.25rem; }
.camera-pill { padding: .3rem .75rem; border: 1px solid #7d7771; border-radius: 2rem; }
.frame { position: absolute; left: 50%; top: 50%; width: 76%; width: min(76%, calc(76cqh * var(--camera-ratio))); aspect-ratio: var(--camera-ratio); max-height: 76%; transform: translate(-50%, -50%); display: grid; grid-template-columns: 1fr 1fr; grid-template-rows: 1fr 1fr; pointer-events: none; }
.frame i { width: 1.28rem; height: 1.28rem; border: 0 solid #fffdf6bb; }
.frame i:nth-child(1) { border-top-width: 2px; border-left-width: 2px; border-top-left-radius: .45rem; }
.frame i:nth-child(2) { justify-self: end; border-top-width: 2px; border-right-width: 2px; border-top-right-radius: .45rem; }
.frame i:nth-child(3) { align-self: end; border-bottom-width: 2px; border-left-width: 2px; border-bottom-left-radius: .45rem; }
.frame i:nth-child(4) { place-self: end; border-bottom-width: 2px; border-right-width: 2px; border-bottom-right-radius: .45rem; }
.camera-hint { grid-row: 3; text-align: center; color: #d1cac1; padding: .45rem; font-size: .8rem; }
.camera-bottom { grid-row: 4; padding: .3rem 0 0; }
.camera-bottom button { gap: .17rem; font-size: .75rem; }
.camera-bottom svg { width: 1.15rem; }
.camera-bottom .manual { grid-column: 1 / -1; color: #d1cac1; text-decoration: underline; text-underline-offset: .25rem; }
.shutter { width: clamp(3.4rem, 10vh, 4.85rem); aspect-ratio: 1; border: 2px solid white; border-radius: 50%; padding: .29rem; }
.shutter span { width: 100%; height: 100%; border-radius: 50%; background: #fff; }
.shutter:active:not(:disabled) span { transform: scale(.87); }
@media (max-height: 480px) and (orientation: landscape) { .camera-shell { max-width: none; grid-template-columns: auto 1fr auto; grid-template-rows: 1fr auto; gap: .4rem; } .viewfinder { grid-row: 1; } .camera-hint { grid-row: 2; grid-column: 2; } .camera-top, .camera-bottom { grid-row: 1 / -1; display: flex; flex-direction: column; justify-content: space-around; } .camera-top h1 { writing-mode: vertical-rl; } }
</style>
