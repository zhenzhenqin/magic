import { computed, onScopeDispose, ref, watch } from 'vue'
import { useAiApi } from '../api/aiRepository'
import type { AiJob } from '../api/aiRepository'
import { ApiError } from '../api/client'
import { useDiaryApi } from '../api/diaryRepository'
import { authMessage, useAuth } from '../stores/auth'
import { usePrivateQuery } from './usePrivateQuery'

export interface DraftPhoto { key: string; id?: string; file?: File; preview?: string }

const inProgress = (job?: AiJob) => job?.status === 'pending' || job?.status === 'running'
const failureMessages: Record<string, string> = {
  ai_quota: '今天的识别额度已用完，仍可手动记录。',
  ai_result_unknown: '模型请求超时，结果未确认，可能已计入额度。你可以继续手动记录。',
  ai_rate_limited: '第三方服务暂时限流，仍可手动记录。',
  ai_invalid_result: '这次识别结果无法使用，你仍可以手动记录。',
  ai_provider_auth: '识别服务暂不可用，你仍可以手动记录。',
  ai_configuration_changed: '识别服务配置已变更，请重新选择照片。',
  ai_images_expired: '识别照片已失效，请重新选择照片。',
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

export function useMealRecognition(photos: () => DraftPhoto[], formId: () => string | undefined) {
  const api = useAiApi()
  const diary = useDiaryApi()
  const auth = useAuth()
  const owner = () => auth.currentUser?.public_id
  const cap = usePrivateQuery(owner, (id, signal) => id ? api.capabilities(signal) : Promise.resolve(undefined))
  const { current: capabilities } = cap
  const picked = ref<string[]>([])
  const job = ref<AiJob>()
  const applied = ref(false)
  const waiting = ref(false)
  const error = ref('')
  const dialog = ref<'start' | 'retry'>()
  const canResume = ref(false)
  let controller: AbortController | undefined
  let createRequest: { signature: string; key: string } | undefined
  let retryRequest: { id: string; key: string } | undefined
  let context = owner()

  const maxImages = computed(() => capabilities.value?.max_images ?? 3)
  const selected = computed(() => photos().filter(photo => picked.value.includes(photo.key)))
  const candidates = computed(() => job.value?.status === 'succeeded' && !applied.value
    ? job.value.result?.foods ?? [] : [])
  const jobMessage = computed(() => {
    const latest = job.value
    if (latest?.status === 'failed') return failureMessages[latest.error_code ?? ''] ?? '识别暂时失败，你仍可以手动记录。'
    if (latest?.status === 'cancelled') return '识别已取消。已发送的模型请求可能仍会完成。'
    if (latest?.status === 'succeeded' && !latest.result?.foods.length) {
      return latest.result?.status === 'no_food' ? '这张照片暂时没有识别出食物。' : '暂时看不清食物，可以换张照片或手动记录。'
    }
    return ''
  })

  function invalidate() {
    const old = job.value
    controller?.abort()
    controller = undefined
    if (old && inProgress(old) && context && owner() === context) void api.cancel(old.id).catch(() => undefined)
    job.value = undefined
    waiting.value = false
    error.value = ''
    canResume.value = applied.value = false
    dialog.value = createRequest = retryRequest = undefined
  }

  watch([formId, owner], () => {
    invalidate()
    context = owner()
  }, { flush: 'sync' })
  watch([() => photos().map(photo => photo.key).join(','), maxImages], () => {
    invalidate()
    picked.value = photos().slice(0, maxImages.value).map(photo => photo.key)
  }, { immediate: true, flush: 'sync' })
  onScopeDispose(invalidate)

  function togglePhoto(key: string, selected: boolean) {
    invalidate()
    picked.value = selected ? [...picked.value, key] : picked.value.filter(value => value !== key)
  }

  async function run(action: 'start' | 'retry' | 'resume' | 'cancel') {
    const cap = capabilities.value
    if (!cap?.available || (waiting.value && action !== 'cancel')) return
    const identity = owner()
    const previous = job.value
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
        if (retryRequest?.id !== previous.id) retryRequest = { id: previous.id, key: crypto.randomUUID() }
        latest = await api.retry(previous.id, cap.consent_version, previous.error_code === 'ai_result_unknown', retryRequest.key)
        if (!stale()) retryRequest = undefined
      } else {
        const ids = []
        for (const photo of selected.value) {
          if (!photo.id && photo.file) photo.id = (await diary.upload(photo.file, signal)).id
          if (stale()) return
          if (photo.id) ids.push(photo.id)
        }
        const signature = ids.join(',') + ':' + cap.consent_version
        if (createRequest?.signature !== signature) createRequest = { signature, key: crypto.randomUUID() }
        latest = await api.create(ids, cap.consent_version, createRequest.key)
        if (!stale()) createRequest = undefined
      }
      if (stale()) {
        if (identity && identity === owner() && inProgress(latest)) void api.cancel(latest.id).catch(() => undefined)
        return
      }
      job.value = latest
      applied.value = false
      let polls = 0
      while (inProgress(latest) && !stale()) {
        await wait(polls++ < 12 ? 1200 : 2600, signal)
        if (stale()) return
        latest = await api.job(latest.id, signal)
        if (!stale()) job.value = latest
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
    error, jobMessage, dialog, canResume, togglePhoto, run,
  }
}
