export type Facing = 'environment' | 'user'

export interface CapturedPhoto {
  file: File
  width: number
  height: number
  orientation: 'upright' | 'embedded'
}

export interface CameraSession {
  attach(video: HTMLVideoElement): void
  capture(video: HTMLVideoElement): Promise<CapturedPhoto>
  torch?: (enabled: boolean) => Promise<void>
  close(): void
}

// Opening a session requests permission. Reopening with another facing mode switches lenses.
// System camera and album selections use the same photo contract as a live capture.
export interface CameraProvider {
  available(): boolean
  open(facing: Facing, signal: AbortSignal): Promise<CameraSession>
  select(file: File): Promise<CapturedPhoto>
}

const maxEdge = 1600
const uploadTarget = 768 * 1024

async function makePhoto(source: CanvasImageSource, width: number, height: number): Promise<CapturedPhoto> {
  if (!width || !height) throw new Error('Camera frame is not ready')
  const scale = Math.min(1, maxEdge / Math.max(width, height))
  const canvas = document.createElement('canvas')
  canvas.width = Math.max(1, Math.round(width * scale))
  canvas.height = Math.max(1, Math.round(height * scale))
  try {
    const context = canvas.getContext('2d', { alpha: false })
    if (!context) throw new Error('Canvas unavailable')
    context.fillStyle = '#fff'
    context.fillRect(0, 0, canvas.width, canvas.height)
    context.drawImage(source, 0, 0, canvas.width, canvas.height)
    const encode = (quality: number) => new Promise<Blob>((resolve, reject) => {
      canvas.toBlob(image => image ? resolve(image) : reject(new Error('Image encoding failed')), 'image/jpeg', quality)
    })
    const initial = await encode(.88)
    const blob = initial.size > uploadTarget ? await encode(.76) : initial
    return { file: new File([blob], 'fooddiary-camera.jpg', { type: blob.type }), width: canvas.width,
      height: canvas.height, orientation: 'upright' }
  } finally {
    canvas.width = canvas.height = 0
  }
}

export const webCamera: CameraProvider = {
  available: () => window.isSecureContext && typeof navigator.mediaDevices?.getUserMedia === 'function',
  async open(facing, signal) {
    signal.throwIfAborted()
    const stream = await navigator.mediaDevices.getUserMedia({ audio: false,
      video: { facingMode: { ideal: facing }, width: { ideal: 1920 }, height: { ideal: 1080 } } })
    let preview: HTMLVideoElement | undefined
    const close = () => {
      signal.removeEventListener('abort', close)
      stream.getTracks().forEach(track => track.stop())
      if (preview?.srcObject === stream) preview.srcObject = null
      preview = undefined
    }
    if (signal.aborted) {
      close()
      signal.throwIfAborted()
    }
    signal.addEventListener('abort', close, { once: true })
    const track = stream.getVideoTracks()[0]
    const capabilities = track?.getCapabilities?.() as (MediaTrackCapabilities & { torch?: boolean }) | undefined
    return {
      attach(video) {
        preview = video
        video.srcObject = stream
        void video.play().catch(() => { /* The native autoplay policy can defer playback. */ })
      },
      async capture(video) {
        signal.throwIfAborted()
        const photo = await makePhoto(video, video.videoWidth, video.videoHeight)
        signal.throwIfAborted()
        return photo
      },
      torch: capabilities?.torch ? enabled => track.applyConstraints({ advanced: [{ torch: enabled } as MediaTrackConstraintSet] }) : undefined,
      close,
    }
  },
  async select(file) {
    const url = URL.createObjectURL(file)
    const image = new Image()
    try {
      image.src = url
      await image.decode()
      if (['image/jpeg', 'image/png', 'image/webp'].includes(file.type) && file.size <= uploadTarget
        && Math.max(image.naturalWidth, image.naturalHeight) <= maxEdge) {
        return { file, width: image.naturalWidth, height: image.naturalHeight, orientation: 'embedded' }
      }
      return await makePhoto(image, image.naturalWidth, image.naturalHeight)
    } finally {
      URL.revokeObjectURL(url)
    }
  },
}
