import { useAuth } from '../stores/auth'

export type Crop = { left: number; top: number; width: number; height: number }
export interface StickerJob {
  id: string
  media_id: string
  status: 'pending' | 'running' | 'succeeded' | 'failed' | 'cancelled'
  ready: boolean
  result_id: string | null
  manual: boolean
  error_code: string | null
}
export const stickerRunning = (job?: StickerJob | null) => job?.status === 'pending' || job?.status === 'running'

export function useStickerApi() {
  const { api } = useAuth()
  const job = (id: string) => '/stickers/jobs/' + encodeURIComponent(id)
  return {
    capabilities: (signal?: AbortSignal) => api<{ online: boolean; enabled: boolean; simulated: boolean }>('/stickers/capabilities', { signal }),
    create: (media_id: string, crop?: Crop, signal?: AbortSignal) =>
      api<StickerJob>('/stickers/jobs', { method: 'POST', body: { media_id, crop }, signal }),
    source: (id: string, signal?: AbortSignal) =>
      api<StickerJob | null>('/stickers/sources/' + encodeURIComponent(id), { signal }),
    job: (id: string, signal?: AbortSignal) => api<StickerJob>(job(id), { signal }),
    retry: (id: string, crop?: Crop, signal?: AbortSignal) =>
      api<StickerJob>(job(id) + '/retry', { method: 'POST', body: { crop }, signal }),
    cancel: (id: string, signal?: AbortSignal) =>
      api<StickerJob>(job(id) + '/cancel', { method: 'POST', signal }),
    image: (id: string, variant: 'sticker' | 'thumbnail' | 'cutout', signal: AbortSignal) =>
      api<Blob>('/media/' + encodeURIComponent(id) + '/sticker' + (variant === 'sticker' ? '' : '/' + variant),
        { response: 'blob', signal }),
  }
}
