export class ApiError extends Error {
  constructor(readonly status: number, readonly code: string, message: string) { super(message) }
}

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE'
  body?: object
  query?: Record<string, string | number | undefined>
  headers?: HeadersInit
  signal?: AbortSignal
  response?: 'json' | 'blob'
}

export async function request<T>(path: string, options: RequestOptions = {}, access?: string): Promise<T> {
  const method = options.method ?? 'GET'
  const authPath = path.startsWith('/auth/')
  const headers = new Headers(options.headers)
  headers.set('Accept', options.response === 'blob' ? 'image/*' : 'application/json')
  if (authPath && method === 'POST') headers.set('X-FoodDiary-Intent', 'browser')
  if (access) headers.set('Authorization', 'Bearer ' + access)
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(options.query ?? {})) {
    if (value !== undefined) query.set(key, String(value))
  }
  const isForm = options.body instanceof FormData
  if (options.body && !isForm && !(options.body instanceof Blob)) headers.set('Content-Type', 'application/json')
  const body = isForm || options.body instanceof Blob ? options.body as FormData | Blob
    : options.body ? JSON.stringify(options.body) : undefined
  const timeout = AbortSignal.timeout(isForm ? 60_000 : 10_000)
  const signal = options.signal ? AbortSignal.any([timeout, options.signal]) : timeout
  let response: Response
  try {
    response = await fetch('/api/v1' + path + (query.size ? '?' + query : ''), {
      method, headers, credentials: authPath ? 'same-origin' : 'omit', body, cache: 'no-store', signal,
    })
  } catch {
    if (options.signal?.aborted) throw new DOMException('Request cancelled', 'AbortError')
    throw new ApiError(0, 'network_unavailable', '无法连接 FoodDiary 服务，请检查连接后重试。')
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    throw new ApiError(response.status, payload?.error?.code ?? 'request_failed',
      payload?.error?.message ?? 'FoodDiary 服务暂时不可用，请稍后重试。')
  }
  return (response.status === 204 ? undefined : options.response === 'blob' ? await response.blob() : await response.json()) as T
}
