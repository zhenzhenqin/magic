export interface UserProfile {
  public_id: string
  username: string
  nickname: string
  avatar_key: string | null
  created_at: string
  updated_at: string
}

export interface UserPreferences {
  timezone: string
  show_calories: boolean
  show_nutrition: boolean
}

export interface AuthSession {
  access_token: string
  token_type: 'bearer'
  expires_in: number
  user: UserProfile
}

interface Credentials {
  username: string
  password: string
}

export class ApiError extends Error {
  constructor(readonly status: number, readonly code: string, message: string) {
    super(message)
  }
}

async function request<T>(path: string, method: 'GET' | 'POST' | 'PATCH', body?: object, access?: string): Promise<T> {
  const headers = new Headers({ Accept: 'application/json' })
  if (method === 'POST') headers.set('X-FoodDiary-Intent', 'browser')
  if (body) headers.set('Content-Type', 'application/json')
  if (access) headers.set('Authorization', 'Bearer ' + access)
  let response: Response
  try {
    response = await fetch('/api/v1' + path, {
      method, headers, credentials: path.startsWith('/auth/') ? 'same-origin' : 'omit',
      body: body ? JSON.stringify(body) : undefined, cache: 'no-store', signal: AbortSignal.timeout(10_000),
    })
  } catch {
    throw new ApiError(0, 'network_unavailable', '无法连接 FoodDiary 服务，请检查连接后重试。')
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    throw new ApiError(response.status, payload?.error?.code ?? 'request_failed',
      payload?.error?.message ?? 'FoodDiary 服务暂时不可用，请稍后重试。')
  }
  return (response.status === 204 ? undefined : await response.json()) as T
}

export const authRepository = {
  register: (data: Credentials & { nickname: string }) => request<UserProfile>('/auth/register', 'POST', data),
  login: (data: Credentials) => request<AuthSession>('/auth/login', 'POST', data),
  refresh: () => request<AuthSession>('/auth/refresh', 'POST'),
  logout: (access?: string) => request<void>('/auth/logout', 'POST', undefined, access),
  profile: (access: string) => request<UserProfile>('/users/me', 'GET', undefined, access),
  updateProfile: (access: string, nickname: string) => request<UserProfile>('/users/me', 'PATCH', { nickname }, access),
  preferences: (access: string) => request<UserPreferences>('/users/me/settings', 'GET', undefined, access),
  updatePreferences: (access: string, data: UserPreferences) => request<UserPreferences>('/users/me/settings', 'PATCH', data, access),
}
