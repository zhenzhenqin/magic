import { useAuth } from '../stores/auth'
import type { MealItemInput } from './diaryRepository'

export type AiCandidate = Omit<MealItemInput, 'note' | 'ai_reference'> & { id: string; uncertainty: string | null }
export interface AiJob {
  id: string
  status: 'pending' | 'running' | 'succeeded' | 'failed' | 'cancelled'
  simulated: boolean
  error_code: string | null
  can_retry: boolean
  result: {
    schema_version: '1'
    status: 'recognized' | 'no_food' | 'unrecognized'
    foods: AiCandidate[]
    warnings: string[]
  } | null
}

interface Capabilities {
  available: boolean
  simulated: boolean
  max_images: number
  consent_version: string
  privacy_url: string | null
}

export function useAiApi() {
  const { api } = useAuth()
  const path = (id: string) => '/ai/jobs/' + encodeURIComponent(id)
  return {
    capabilities: (signal: AbortSignal) => api<Capabilities>('/ai/capabilities', { signal }),
    create: (ids: string[], version: string, key: string) => api<AiJob>('/ai/jobs', {
      method: 'POST', body: { media_ids: ids, consent_version: version }, headers: { 'Idempotency-Key': key },
    }),
    job: (id: string, signal: AbortSignal) => api<AiJob>(path(id), { signal }),
    cancel: (id: string) => api<AiJob>(path(id) + '/cancel', { method: 'POST' }),
    retry: (id: string, version: string, acceptUnknown: boolean, key: string) => api<AiJob>(path(id) + '/retry', {
      method: 'POST', body: { consent_version: version, accept_unknown_charge: acceptUnknown }, headers: { 'Idempotency-Key': key },
    }),
  }
}
