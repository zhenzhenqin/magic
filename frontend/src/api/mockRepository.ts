import { grantKey, newPermissions, sampleItem, seedDiary } from '../mocks/seed'
import type { DateKey, DiaryState, FoodCatalogItem, Meal, SharePermission } from '../types/domain'
import { todayKey } from '../utils/dates'

const key = 'fooddiary.demo.v1'

export const mockRepository = {
  load(): DiaryState {
    try {
      const stored = localStorage.getItem(key)
      return stored ? JSON.parse(stored) as DiaryState : seedDiary()
    } catch {
      return seedDiary()
    }
  },
  save(state: DiaryState) {
    localStorage.setItem(key, JSON.stringify(state))
  },
  recognize() {
    return new Promise<Meal['items']>(resolve => {
      window.setTimeout(() => resolve([sampleItem('curry')]), 450)
    })
  },
}

export function areFriends(state: DiaryState, a: string, b: string) {
  return state.friends.some(friend => friend.status === 'accepted' &&
    ((friend.senderId === a && friend.recipientId === b) || (friend.senderId === b && friend.recipientId === a)))
}

export function permissionsFor(state: DiaryState, ownerId: string, viewerId: string): SharePermission {
  if (ownerId === viewerId) return newPermissions(true)
  if (!areFriends(state, ownerId, viewerId)) return newPermissions()
  return state.grants[grantKey(ownerId, viewerId)] ?? newPermissions()
}

export function projectedMeals(state: DiaryState, ownerId: string, viewerId: string, date?: DateKey, surface: 'diary' | 'catalog' = 'diary'): Meal[] {
  const permissions = permissionsFor(state, ownerId, viewerId)
  if (!permissions[surface === 'diary' ? 'records' : 'catalog']) return []
  return state.meals.filter(meal => meal.ownerId === ownerId &&
    (!date || meal.date === date) && (permissions.history || meal.date === todayKey()))
    .map(meal => ({
      ...meal,
      note: permissions.notes ? meal.note : '',
      photo: permissions.photos ? meal.photo : undefined,
      items: meal.items.map(item => ({
        ...item,
        name: permissions.names ? item.name : '共享食物',
        category: permissions.names ? item.category : '其他',
        stickerId: permissions.stickers ? item.stickerId : undefined,
        weight: permissions.nutrition ? item.weight : undefined,
        calories: permissions.calories ? item.calories : undefined,
        nutrition: permissions.nutrition ? item.nutrition : undefined,
        note: permissions.notes ? item.note : undefined,
      })),
    })).sort((left, right) => right.date.localeCompare(left.date) || left.time.localeCompare(right.time))
}

export function buildCatalog(state: DiaryState, ownerId: string, viewerId: string): FoodCatalogItem[] {
  const byId = new Map<string, FoodCatalogItem>()
  for (const meal of projectedMeals(state, ownerId, viewerId, undefined, 'catalog')) {
    for (const item of meal.items) {
      const existing = byId.get(item.foodId)
      if (existing) {
        existing.count++
        existing.firstDate = meal.date
        continue
      }
      byId.set(item.foodId, { id: item.foodId, name: item.name, category: item.category, stickerId: item.stickerId,
        count: 1, firstDate: meal.date, latestDate: meal.date,
        favorite: ownerId === viewerId && (state.favorites[viewerId] ?? []).includes(item.foodId) })
    }
  }
  return [...byId.values()]
}
