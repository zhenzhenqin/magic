import { useAuth } from '../stores/auth'

export interface Connection {
  mode: 'simulation' | 'disabled'
  connected: boolean
  expires_at: string | null
  daily_limit: number | null
  maximum_daily_limit: number
  intro_dismissed: boolean
  today: number
  total: number
  input_tokens: number | null
  output_tokens: number | null
  unknown: number
}

export function personalAi() {
  const auth = useAuth()
  return {
    read: () => auth.api<Connection>('/ai/connection'),
    connect: (api_key: string) => auth.api<Connection>('/ai/connection', { method: 'PUT', body: { api_key } }),
    disconnect: () => auth.api<void>('/ai/connection', { method: 'DELETE' }),
    balance: () => auth.api<{ simulated: boolean; is_available: boolean }>('/ai/connection/balance', { method: 'POST' }),
    preferences: (body: { dismiss_intro?: boolean; daily_limit?: number | null }) =>
      auth.api<Connection>('/ai/preferences', { method: 'PATCH', body }),
  }
}
