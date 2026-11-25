import type { MealKind, PermissionKey } from '../types/domain'

export const mealLabels: Record<MealKind, { label: string; time: string }> = {
  breakfast: { label: '早餐', time: '08:00' },
  lunch: { label: '午餐', time: '12:30' },
  dinner: { label: '晚餐', time: '18:30' },
  snack: { label: '加餐', time: '15:30' },
}

export const permissionLabels: Record<PermissionKey, string> = {
  records: '饮食记录',
  names: '食物名称',
  photos: '食物照片',
  stickers: '食物贴纸',
  catalog: '美食图鉴',
  calories: '热量统计',
  nutrition: '营养成分',
  notes: '文字备注',
  history: '历史记录',
}
