import { useAuth } from '../stores/auth'
import type { MealKind } from '../types/domain'

export interface FoodEntry {
  id: string
  canonical_name: string
  display_name: string
  category: string | null
  cover_media_id: string | null
  cover_whole_meal: boolean
  is_favorite: boolean
  first_eaten: string | null
  last_eaten: string | null
  occasions: number
  details: number
}
export interface CatalogQuery {
  search: string
  category: string
  favorites: boolean
  sort: 'recent' | 'occasions'
  page: number
  limit?: number
}
interface Result<T> { items: T[]; total: number; page: number; limit: number }
interface Catalog extends Result<FoodEntry> { collected: number; categories: string[] }
interface HistoryItem { meal_id: string; local_date: string; meal_type: MealKind; eaten_at: string; media_ids: string[] }
type Change = Partial<Pick<FoodEntry, 'display_name' | 'category' | 'cover_media_id' | 'is_favorite'>>

export function useCatalogApi() {
  const { api } = useAuth()
  const path = (id: string) => '/catalog/' + encodeURIComponent(id)
  return {
    list: (query: CatalogQuery, signal: AbortSignal) =>
      api<Catalog>('/catalog', { query: { ...query, favorites: String(query.favorites) }, signal }),
    entry: (id: string, signal: AbortSignal) => api<FoodEntry>(path(id), { signal }),
    patch: (id: string, body: Change) => api<FoodEntry>(path(id), { method: 'PATCH', body }),
    history: (id: string, page: number, signal: AbortSignal) => api<Result<HistoryItem>>(path(id) + '/history', { query: { page }, signal }),
    merge: (source_id: string, target_id: string) => api<FoodEntry>('/catalog/merge', { method: 'POST', body: { source_id, target_id } }),
  }
}
