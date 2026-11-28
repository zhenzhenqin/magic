import { useAuth } from '../stores/auth'
import type { MealKind } from '../types/domain'

export const nutrientFields = {
  calories_kcal: { label: '热量', unit: 'kcal' },
  protein_g: { label: '蛋白质', unit: 'g' },
  carbohydrates_g: { label: '碳水化合物', unit: 'g' },
  fat_g: { label: '脂肪', unit: 'g' },
} as const
export type NutrientKey = keyof typeof nutrientFields

export interface MediaInfo {
  id: string
  content_type: string
  width: number
  height: number
  status: 'draft' | 'attached'
  use_original?: boolean
}

export interface MealItemInput {
  id?: string
  ai_reference?: { job_id: string; candidate_id: string }
  food_name: string
  category: string | null
  weight_g: number | null
  calories_kcal: number | null
  protein_g: number | null
  carbohydrates_g: number | null
  fat_g: number | null
  note: string
}

export interface MealInput {
  meal_type: MealKind
  local_date: string
  local_time: string
  timezone: string
  note: string
  items: MealItemInput[]
  media_ids: string[]
  original_media_ids?: string[]
}

export interface Meal extends Omit<MealInput, 'media_ids' | 'original_media_ids' | 'items'> {
  id: string
  version: number
  items: (MealItemInput & { id: string; source: 'manual' | 'ai' | 'ai_edited'; ai_provider: string | null })[]
  media: MediaInfo[]
}

export interface MealPage { items: Meal[]; page: number; limit: number; total: number }
export interface CalendarDay { date: string; meal_count: number; representative_media_id: string | null; representative_use_original?: boolean }
export interface Calendar { month: string; days: CalendarDay[] }
export interface Daily {
  date: string
  meals: number
  items: number
  nutrition: Record<NutrientKey, { value: number | null; complete: boolean; known_items: number }>
  nutrition_sources: Record<NutrientKey, { estimated: number; edited: number; simulated: number }>
}

export function useDiaryApi() {
  const { api } = useAuth()
  const path = (group: string, id: string) => '/' + group + '/' + encodeURIComponent(id)
  return {
    meals: (date: string, page: number, signal: AbortSignal) => api<MealPage>('/meals', { query: { date, page }, signal }),
    meal: (id: string, signal?: AbortSignal) => api<Meal>(path('meals', id), { signal }),
    create: (body: MealInput, key: string) => api<Meal>('/meals', { method: 'POST', body, headers: { 'Idempotency-Key': key } }),
    edit: (id: string, body: MealInput, version: number) => api<Meal>(path('meals', id), { method: 'PATCH', body: { ...body, version } }),
    remove: (id: string, version: number) => api<void>(path('meals', id), { method: 'DELETE', query: { version } }),
    calendar: (month: string, signal: AbortSignal) => api<Calendar>('/calendar', { query: { month }, signal }),
    daily: (date: string, signal: AbortSignal) => api<Daily>('/statistics/daily', { query: { date }, signal }),
    upload: (file: File, signal?: AbortSignal) => {
      const body = new FormData()
      body.set('file', file)
      return api<MediaInfo>('/media/upload', { method: 'POST', body, signal })
    },
    photo: (id: string, original: boolean, signal: AbortSignal) => api<Blob>(
      path('media', id) + (original ? '' : '/thumbnail'), { response: 'blob', signal },
    ),
    discardDraft: (id: string, signal?: AbortSignal) => api<void>(path('media', id), { method: 'DELETE', signal }),
  }
}
