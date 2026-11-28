import { computed, onScopeDispose, ref, watch } from 'vue'
import { useAiApi } from '../api/aiRepository'
import type { AiJob, AiRecoveryQuery } from '../api/aiRepository'
import { ApiError } from '../api/client'
import { authMessage, useAuth } from '../stores/auth'
import { usePrivateQuery } from './usePrivateQuery'

export interface DraftPhoto { key: string; id?: string; file?: File; preview?: string; captured?: boolean; useOriginal?: boolean }

const inProgress = (job?: AiJob) => job?.status === 'pending' || job?.status === 'running'
const failureMessages: Record<string, string> = {
  ai_quota: '今天的识别额度已用完，仍可手动记录。',
  ai_cumulative_limit: '真实模型联调累计额度已用完，仍可手动记录。',
  ai_result_unknown: '模型请求结果未确认，可能已计入额度。你可以继续手动记录。',
  ai_rate_limited: '第三方服务暂时限流，仍可手动记录。',
  ai_invalid_result: '这次识别结果无法使用，你仍可以手动记录。',
  ai_provider_auth: '识别服务暂不可用，你仍可以手动记录。',
  ai_provider_balance: '识别服务用量不足，你仍可以手动记录。',
  ai_configuration_changed: '识别服务配置已变更，请重新选择照片。',
  ai_images_expired: '识别照片已失效，请重新选择照片。',
  ai_image_invalid: '识别照片无法读取，请重新选择照片。',
  ai_expired: '等待识别超时，你仍可以手动记录。',
}

function wait(ms: number, signal: AbortSignal) {
  return new Promise<void>(resolve => {
    if (signal.aborted) { resolve(); return }
    const finish = () => {
      window.clearTimeout(timer)
      signal.removeEventListener('abort', finish)
      resolve()
    }
    const timer = window.setTimeout(finish, ms)
    signal.addEventListener('abort', finish, { once: true })
  })
}

export function useMealRecognition(photos: () => DraftPhoto[], formId: () => string | undefined,
  restorePhotos: (photos: DraftPhoto[]) => void, uploadPhoto: (photo: DraftPhoto) => Promise<string>) {
  const api = useAiApi()
  const auth = useAuth()
  const owner = () => auth.currentUser?.public_id
  const cap = usePrivateQuery(owner, (id, signal) => id ? api.capabilities(signal) : Promise.resolve(undefined))
  const { current: capabilities } = cap
  const recovery = usePrivateQuery(() => [owner(), formId()] as const, ([id, meal], signal) =>
    id ? api.recover({ form_meal_id: meal }, signal) : Promise.resolve(null))
  const picked = ref<string[]>([])
  const job = ref<AiJob>()
  const recovered = computed(() => recovery.current.value?.id === job.value?.id ? undefined : recovery.current.value)
  const applied = ref(false)
  const explicitlyRestored = ref(false)
  const waiting = ref(false)
  const error = ref('')
  const dialog = ref<'start' | 'retry'>()
  const canResume = ref(false)
  let controller: AbortController | undefined
  let createRequest: { signature: string; key: string } | undefined
  let retryRequest: { id: string; key: string } | undefined
  let context = owner()
  let restoring = false
  const cancelOnStale = new WeakSet<AbortSignal>()

  const maxImages = computed(() => capabilities.value?.max_images ?? 3)
  const selected = computed(() => photos().filter(photo => picked.value.includes(photo.key)))
  const workerOnline = computed(() => job.value && inProgress(job.value)
    ? job.value.worker_online : capabilities.value?.worker_online)
  const matchesForm = (value: AiJob) => value.form_meal_id === (formId() ?? null)
  const matchesSelection = (value: AiJob) => matchesForm(value) && value.media_ids.length > 0
    && value.media_ids.join(',') === selected.value.map(photo => photo.id ?? '').join(',')
  const candidates = computed(() => job.value?.status === 'succeeded' && !applied.value && matchesSelection(job.value)
    ? job.value.result?.foods ?? [] : [])
  const canRestore = computed(() => {
    const value = recovered.value
    if (!value || !matchesForm(value) || !value.media_ids.length) return false
    if (!photos().length) return true
    return photos().filter(photo => photo.id && value.media_ids.includes(photo.id))
      .map(photo => photo.id).join(',') === value.media_ids.join(',')
  })
  const jobMessage = computed(() => {
    const latest = job.value
    if (latest?.status === 'failed') return failureMessages[latest.error_code ?? ''] ?? '识别暂时失败，你仍可以手动记录。'
    if (latest?.status === 'cancelled') return '识别已取消。已发送的模型请求可能仍会完成。'
    if (latest?.status === 'succeeded' && !latest.result?.foods.length) {
      return latest.result?.status === 'no_food' ? '这张照片暂时没有识别出食物。' : '暂时看不清食物，可以换张照片或手动记录。'
    }
    return ''
  })

  function invalidate(cancelRemote = false) {
    const old = job.value
    if (controller && cancelRemote) cancelOnStale.add(controller.signal)
    controller?.abort()
    controller = undefined
    if (cancelRemote && old && inProgress(old) && context && owner() === context) {
      void api.cancel(old.id).then(() => recovery.reload()).catch(() => recovery.reload())
    }
    job.value = undefined
    waiting.value = false
    error.value = ''
    canResume.value = applied.value = explicitlyRestored.value = false
    dialog.value = createRequest = retryRequest = undefined
  }

  watch([formId, owner], () => {
    invalidate()
    context = owner()
  }, { flush: 'sync' })
  watch(() => photos().map(photo => photo.key).join(','), () => {
    if (restoring) return
    invalidate(true)
    picked.value = photos().slice(0, maxImages.value).map(photo => photo.key)
  }, { immediate: true, flush: 'sync' })
  watch(maxImages, max => { if (picked.value.length > max) picked.value = picked.value.slice(0, max) })
  watch(capabilities, (value, previous, cleanup) => {
    if (value?.consent_version !== previous?.consent_version) dialog.value = undefined
    if (!value?.available || value.worker_online) return
    const timer = window.setTimeout(() => cap.reload(), 4000)
    cleanup(() => window.clearTimeout(timer))
  }, { flush: 'sync' })
  function reconnect() {
    recovery.reload()
    if (!waiting.value) cap.reload()
  }
  window.addEventListener('online', reconnect)
  onScopeDispose(() => {
    window.removeEventListener('online', reconnect)
    invalidate()
  })

  function togglePhoto(key: string, selected: boolean) {
    invalidate(true)
    picked.value = selected ? [...picked.value, key] : picked.value.filter(value => value !== key)
  }

  async function restore() {
    const value = recovered.value
    if (!value || !canRestore.value) return
    if (!photos().length) {
      restoring = true
      try { restorePhotos(value.media_ids.map(id => ({ id, key: id }))) }
      finally { restoring = false }
    }
    picked.value = photos().filter(photo => photo.id && value.media_ids.includes(photo.id)).map(photo => photo.key)
    if (!matchesSelection(value)) return
    explicitlyRestored.value = true
    await run('resume', value)
  }

  async function postWithRecovery(send: () => Promise<AiJob>, query: AiRecoveryQuery, signal: AbortSignal) {
    try {
      return await send()
    } catch (failure) {
      if (signal.aborted || !(failure instanceof ApiError) || (failure.status > 0 && failure.status < 500)) throw failure
      const found = await api.recover(query, signal).catch(() => null)
      if (found) return found
      throw failure
    }
  }

  async function run(action: 'start' | 'retry' | 'resume' | 'cancel', recoveredJob?: AiJob) {
    const cap = capabilities.value
    if ((action === 'start' || action === 'retry') && (!cap?.available || !workerOnline.value)) return
    if ((waiting.value && action !== 'cancel') || !owner()) return
    const identity = owner()
    const previous = recoveredJob ?? job.value
    controller?.abort()
    const signal = (controller = new AbortController()).signal
    const stale = () => signal.aborted || identity !== owner()
    waiting.value = true
    dialog.value = undefined
    error.value = ''
    canResume.value = false
    try {
      let latest: AiJob
      if (action === 'cancel' && previous) {
        latest = await api.cancel(previous.id)
      } else if (action === 'resume' && previous) {
        latest = await api.job(previous.id, signal)
      } else if (action === 'retry' && previous) {
        if (!cap || !matchesSelection(previous)) return
        if (retryRequest?.id !== previous.id) retryRequest = { id: previous.id, key: crypto.randomUUID() }
        const key = retryRequest.key
        latest = await postWithRecovery(
          () => api.retry(previous.id, cap.consent_version, previous.error_code === 'ai_result_unknown', key),
          { job_id: previous.id, retry_key: key }, signal,
        )
        if (!stale()) retryRequest = undefined
      } else if (action === 'start' && cap) {
        const ids: string[] = []
        for (const photo of selected.value) {
          if (!photo.id && photo.file) await uploadPhoto(photo)
          if (stale()) return
          if (photo.id) ids.push(photo.id)
        }
        const form = formId()
        const signature = [ids.join(','), cap.consent_version, form].join(':')
        if (createRequest?.signature !== signature) createRequest = { signature, key: crypto.randomUUID() }
        const key = createRequest.key
        latest = await postWithRecovery(
          () => api.create(ids, cap.consent_version, key, form), { request_key: key }, signal,
        )
        if (!stale()) createRequest = undefined
        explicitlyRestored.value = false
      } else return
      if (stale()) {
        if (cancelOnStale.has(signal) && identity === owner() && inProgress(latest)) {
          void api.cancel(latest.id).then(() => recovery.reload()).catch(() => recovery.reload())
        }
        return
      }
      if (recoveredJob && action === 'cancel') {
        recovery.reload()
        return
      }
      job.value = latest
      applied.value = false
      let polls = 0
      let failures = 0
      while (inProgress(latest) && !stale()) {
        await wait(failures ? 2200 * failures : polls++ < 12 ? 1200 : 2600, signal)
        if (stale()) return
        try {
          latest = await api.job(latest.id, signal)
          failures = 0
          if (!stale()) { job.value = latest; error.value = '' }
        } catch (failure) {
          if (stale() || !(failure instanceof ApiError) || (failure.status > 0 && failure.status < 500) || ++failures > 3) throw failure
          error.value = '连接暂时中断，正在重新查看任务。'
        }
      }
    } catch (failure) {
      if (stale()) return
      error.value = authMessage(failure)
      canResume.value = inProgress(job.value)
      if (failure instanceof ApiError && failure.status > 0 && failure.status < 500) {
        if (action === 'start') createRequest = undefined
        if (action === 'retry') retryRequest = undefined
      }
    } finally {
      if (!stale()) waiting.value = false
    }
  }

  return {
    capabilities, capabilityError: cap.error, maxImages, selected, picked, job, candidates, applied, waiting,
    error, jobMessage, dialog, canResume, togglePhoto, run, recovered, canRestore, restore,
    recoveryError: recovery.error, explicitlyRestored, workerOnline, refreshRecovery: recovery.reload,
  }
}
