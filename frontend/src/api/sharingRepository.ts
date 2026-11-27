import { useAuth } from '../stores/auth'
import type { MealKind } from '../types/domain'

export const sharingFields = {
  records: { label: '饮食记录', help: '查看餐次、时间、手账和月历' },
  names: { label: '食物名称及分类', help: '用于手账明细和已开放图鉴的列表' },
  photos: { label: '原始食物照片', help: '授权原图和原图缩略图' },
  stickers: { label: '美食贴纸', help: '仅授权白边贴纸和贴纸缩略图' },
  catalog: { label: '美食图鉴', help: '只有同时开放食物名称时才显示条目' },
  calories: { label: '热量数据', help: '手账及每日小结中的热量' },
  nutrition: { label: '营养成分', help: '食物重量、蛋白质、脂肪和碳水' },
  notes: { label: '文字备注', help: '餐次与食物明细的备注' },
  history: { label: '历史记录', help: '选择历史起点，并允许查看图鉴的历史统计' },
} as const
export type ShareKey = keyof typeof sharingFields
export type ShareFlags = Record<ShareKey, boolean>
export type HistoryScope = 'today' | 'week' | 'month' | 'all'
export interface Peer { public_id: string; nickname: string }
export interface Grant {
  permissions: ShareFlags
  history_scope: HistoryScope
  history_start: string | null
  granted_at: string | null
  version: number
}
export interface Friend { relationship_id: string; person: Peer; outgoing: Grant; incoming: Grant }
export interface FriendRequest {
  id: string
  person: Peer
  direction: 'incoming' | 'outgoing'
  status: 'pending' | 'accepted' | 'rejected' | 'cancelled'
  created_at: string
}
export type MediaKind = 'photo' | 'sticker'
export interface SharedMedia { id: string; kinds: MediaKind[] }
export type MediaContext = { meal_id: string; catalog_id?: never } | { catalog_id: string; meal_id?: never }
export interface SharedItem {
  food_name?: string | null
  category?: string | null
  calories_kcal?: number | null
  weight_g?: number | null
  protein_g?: number | null
  carbohydrates_g?: number | null
  fat_g?: number | null
  note?: string | null
  estimated?: boolean
}
export interface SharedMeal {
  id: string
  meal_type: MealKind
  local_date: string
  local_time: string
  items?: SharedItem[]
  media?: SharedMedia[]
  note?: string
}
export interface SharedFood {
  id: string
  name: string
  category: string | null
  cover?: SharedMedia
  cover_whole_meal?: boolean
  occurrences?: number
  items?: number
  first_eaten?: string
  last_eaten?: string
}
interface SharedPage<T> { items: T[]; page: number; limit: number; total: number }
export interface SharedCalendar {
  month: string
  days: { date: string; meals: number; media?: SharedMedia; meal_id?: string }[]
}
export interface SharedDaily {
  date: string
  meals: number
  nutrition?: Record<string, { value: number | null; known_items: number; complete: boolean; estimated: boolean }>
}

export function useSharingApi() {
  const { api } = useAuth()
  const path = (id: string) => '/friends/' + encodeURIComponent(id)
  return {
    list: (signal?: AbortSignal) => api<{ me: Peer; items: Friend[] }>('/friends', { signal }),
    lookup: (public_id: string, signal?: AbortSignal) => api<Peer>('/friends/lookup', { query: { public_id }, signal }),
    requests: (signal?: AbortSignal) => api<FriendRequest[]>('/friends/requests', { signal }),
    send: (public_id: string) => api<FriendRequest>('/friends/requests', { method: 'POST', body: { public_id } }),
    respond: (id: string, action: 'accept' | 'reject' | 'cancel') => api<FriendRequest>(
      '/friends/requests/' + encodeURIComponent(id) + '/' + action, { method: 'POST' },
    ),
    sharing: (id: string, signal?: AbortSignal) => api<Friend>(path(id) + '/sharing', { signal }),
    save: (id: string, relationship_id: string, version: number, permissions: ShareFlags,
      history_scope?: HistoryScope, confirm_history_start?: string) =>
      api<Friend>(path(id) + '/sharing', { method: 'PUT', body: { relationship_id, version, permissions, history_scope, confirm_history_start } }),
    stop: (id: string, relationship_id: string, version: number) => api<Friend>(
      path(id) + '/sharing', { method: 'DELETE', query: { relationship_id, version } },
    ),
    remove: (id: string, relationship_id: string) => api<void>(path(id), { method: 'DELETE', query: { relationship_id } }),
    meals: (id: string, date: string, page: number, signal: AbortSignal, limit?: number) =>
      api<SharedPage<SharedMeal>>(path(id) + '/meals', { query: { date, page, limit }, signal }),
    meal: (id: string, meal: string, signal: AbortSignal) =>
      api<SharedMeal>(path(id) + '/meals/' + encodeURIComponent(meal), { signal }),
    calendar: (id: string, month: string, signal: AbortSignal) =>
      api<SharedCalendar>(path(id) + '/calendar', { query: { month }, signal }),
    daily: (id: string, date: string, signal: AbortSignal) =>
      api<SharedDaily>(path(id) + '/statistics/daily', { query: { date }, signal }),
    catalog: (id: string, page: number, search: string, category: string, signal: AbortSignal) =>
      api<Omit<SharedPage<SharedFood>, 'total'> & { total?: number; categories?: string[]; names_shared: boolean }>(
        path(id) + '/catalog', { query: { page, search, category }, signal },
      ),
    food: (id: string, food: string, signal: AbortSignal) =>
      api<SharedFood>(path(id) + '/catalog/' + encodeURIComponent(food), { signal }),
    history: (id: string, food: string, page: number, signal: AbortSignal) =>
      api<SharedPage<{ id: string; local_date: string; meal_type: MealKind }>>(
        path(id) + '/catalog/' + encodeURIComponent(food) + '/history', { query: { page }, signal },
      ),
    media: (id: string, media: string, kind: MediaKind, thumbnail: boolean, context: MediaContext, signal: AbortSignal) =>
      api<Blob>(path(id) + '/media/' + encodeURIComponent(media) +
        (kind === 'sticker' ? '/sticker' : '') + (thumbnail ? '/thumbnail' : ''), { query: context, signal, response: 'blob' }),
  }
}
