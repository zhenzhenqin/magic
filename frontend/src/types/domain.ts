export type DateKey = string
export const mealKinds = ['breakfast', 'lunch', 'dinner', 'snack'] as const
export type MealKind = typeof mealKinds[number]
export type FoodCategory = '烘焙甜点' | '饮品' | '主食' | '家常菜' | '水果' | '其他'

export interface User {
  id: string
  nickname: string
  initials: string
  tone: 'sage' | 'peach' | 'butter'
}

export interface MediaAsset {
  id: string
  name: string
  mimeType: string
}

export interface Nutrition {
  protein: number
  carbs: number
  fat: number
}

export interface MealItem {
  id: string
  foodId: string
  name: string
  category: FoodCategory
  stickerId?: string
  weight?: number
  calories?: number
  nutrition?: Nutrition
  note?: string
}

export interface Meal {
  id: string
  ownerId: string
  date: DateKey
  kind: MealKind
  time: string
  items: MealItem[]
  note: string
  photo?: MediaAsset
  updatedAt: string
}

export interface FoodCatalogItem {
  id: string
  name: string
  category: FoodCategory
  stickerId?: string
  count: number
  firstDate: DateKey
  latestDate: DateKey
  favorite: boolean
}

export interface Friend {
  id: string
  senderId: string
  recipientId: string
  status: 'pending' | 'accepted' | 'rejected'
}

export const permissionKeys = ['records', 'names', 'photos', 'stickers', 'catalog', 'calories', 'nutrition', 'notes', 'history'] as const
export type PermissionKey = typeof permissionKeys[number]
export type SharePermission = Record<PermissionKey, boolean>

export interface DiaryState {
  activeUserId: string
  meals: Meal[]
  friends: Friend[]
  grants: Record<string, SharePermission>
  favorites: Record<string, string[]>
}
