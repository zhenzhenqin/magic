import { onScopeDispose, reactive, ref, watch } from 'vue'
import { stickerRunning, useStickerApi } from '../api/stickerRepository'
import type { Crop, StickerJob } from '../api/stickerRepository'
import type { DraftPhoto } from './useMealRecognition'

const preference = 'fooddiary.auto-sticker'
function autoStickerEnabled() {
  try { return localStorage.getItem(preference) !== 'off' }
  catch { return true }
}
function setAutoStickerEnabled(enabled: boolean) {
  try { localStorage.setItem(preference, enabled ? 'on' : 'off') }
  catch { /* The current form still respects the setting. */ }
}

interface State {
  job?: StickerJob | null
  busy: boolean
  error: boolean
  mode: 'original' | 'cutout' | 'sticker'
}

export function useDraftStickers(photos: () => DraftPhoto[], upload: (photo: DraftPhoto) => Promise<string>) {
  const api = useStickerApi()
  const enabled = ref(false)
  const online = ref(false)
  const simulated = ref(false)
  const auto = ref(autoStickerEnabled())
  const states = reactive<Record<string, State>>({})
  const controllers = new Map<string, AbortController>()
  const timers = new Map<string, ReturnType<typeof setTimeout>>()
  const alive = new AbortController()

  function cleanup(key: string) {
    clearTimeout(timers.get(key))
    timers.delete(key)
    controllers.get(key)?.abort()
    controllers.delete(key)
  }
  function state(key: string) {
    if (!states[key]) states[key] = { busy: false, error: false, mode: 'original' }
    return states[key]
  }
  function update(key: string, job: StickerJob | null, controller: AbortController, polls = 0) {
    if (controller.signal.aborted) return
    const current = state(key)
    const fresh = job?.ready && job.result_id !== current.job?.result_id
    current.job = job
    current.error = false
    if (fresh) current.mode = 'sticker'
    if (!stickerRunning(job) || !job) return
    timers.set(key, setTimeout(async () => {
      try {
        update(key, await api.job(job.id, controller.signal), controller, polls + 1)
      } catch {
        if (!controller.signal.aborted) current.error = true
      }
    }, polls < 8 ? 650 : 1150))
  }
  async function run(photo: DraftPhoto, action: 'read' | 'make' | 'retry' | 'cancel', crop?: Crop) {
    const current = state(photo.key)
    if (current.busy) return
    cleanup(photo.key)
    const controller = new AbortController()
    controllers.set(photo.key, controller)
    const signal = controller.signal
    current.busy = action !== 'read'
    current.error = false
    try {
      const id = photo.id ?? (action === 'make' ? await upload(photo) : undefined)
      if (signal.aborted || !id) return
      const prior = current.job?.id
      const job = action === 'read' ? await api.source(id, signal)
        : action === 'cancel' && prior ? await api.cancel(prior, signal)
        : action === 'retry' && prior ? await api.retry(prior, crop, signal)
        : await api.create(id, crop, signal)
      update(photo.key, job, controller)
    } catch {
      if (!signal.aborted) current.error = true
    } finally {
      if (!signal.aborted) current.busy = false
    }
  }
  function gather() {
    const current = photos()
    for (const key of Object.keys(states)) {
      if (current.some(photo => photo.key === key)) continue
      cleanup(key)
      delete states[key]
    }
    for (const photo of current) {
      if (states[photo.key]) continue
      if (photo.captured && online.value) void run(photo, 'make')
      else if (photo.id && !photo.captured) void run(photo, 'read')
      else if (auto.value && online.value) void run(photo, 'make')
    }
  }
  async function check() {
    try {
      const caps = await api.capabilities(alive.signal)
      if (alive.signal.aborted) return
      enabled.value = caps.enabled
      online.value = caps.online
      simulated.value = caps.simulated
      gather()
    } catch { /* Original photos remain usable. */ }
  }

  watch(() => photos().map(photo => photo.key).join(','), gather)
  watch(auto, value => { setAutoStickerEnabled(value); gather() })
  function recover() {
    void check()
    for (const photo of photos()) {
      if (photo.id && states[photo.key]?.error) void run(photo, photo.captured ? 'make' : 'read')
    }
  }
  window.addEventListener('online', recover)
  void check()
  onScopeDispose(() => {
    window.removeEventListener('online', recover)
    alive.abort()
    for (const key of controllers.keys()) cleanup(key)
  })
  return { states, enabled, online, simulated, auto, run, check }
}
