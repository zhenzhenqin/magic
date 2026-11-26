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

export const authRepository = {
  register: (body: Credentials & { nickname: string }) => request<UserProfile>('/auth/register', { method: 'POST', body }),
  login: (body: Credentials) => request<AuthSession>('/auth/login', { method: 'POST', body }),
  refresh: (access?: string) => request<AuthSession>('/auth/refresh', { method: 'POST' }, access),
  logout: (access: string) => request<void>('/auth/logout', { method: 'POST' }, access),
}
import { request } from './client'
