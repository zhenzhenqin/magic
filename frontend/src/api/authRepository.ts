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

export interface EmailProof {
  email: string
  request_id: string
  code: string
}

export interface VerificationTicket {
  request_id: string
  expires_in: number
  resend_after: number
}

export type IdentityOptions = { email_available: boolean; registration: 'closed' | 'invite' | 'public' }

export const authRepository = {
  options: () => request<IdentityOptions>('/identity/options'),
  issue: (email: string, purpose: 'register' | 'login' | 'reset') =>
    request<VerificationTicket>('/auth/email/code', { method: 'POST', body: { email, purpose } }),
  registerEmail: (body: Credentials & EmailProof & { nickname: string; invitation?: string }) =>
    request<UserProfile>('/auth/email/register', { method: 'POST', body }),
  loginEmail: (body: EmailProof) => request<AuthSession>('/auth/email/login', { method: 'POST', body }),
  resetPassword: (body: EmailProof & { password: string }) =>
    request<void>('/auth/email/reset', { method: 'POST', body }),
  register: (body: Credentials & { nickname: string }) => request<UserProfile>('/auth/register', { method: 'POST', body }),
  login: (body: Credentials) => request<AuthSession>('/auth/login', { method: 'POST', body }),
  refresh: (access?: string) => request<AuthSession>('/auth/refresh', { method: 'POST' }, access),
  logout: (access: string) => request<void>('/auth/logout', { method: 'POST' }, access),
}
import { request } from './client'
