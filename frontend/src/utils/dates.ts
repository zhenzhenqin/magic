import type { DateKey } from '../types/domain'

export function dateKey(date: Date): DateKey {
  const pad = (value: number) => String(value).padStart(2, '0')
  return [date.getFullYear(), pad(date.getMonth() + 1), pad(date.getDate())].join('-')
}

export function fromKey(value: DateKey): Date {
  const [year, month, day] = value.split('-').map(Number)
  return new Date(year, month - 1, day, 12)
}

export function isDateKey(value: unknown): value is DateKey {
  return typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value) && dateKey(fromKey(value)) === value
}

export function todayKey(): DateKey {
  return dateKey(new Date())
}

export function shiftDay(key: DateKey, delta: number): DateKey {
  const date = fromKey(key)
  date.setDate(date.getDate() + delta)
  return dateKey(date)
}

export function weekFor(key: DateKey): DateKey[] {
  const preceding = (fromKey(key).getDay() + 6) % 7
  return Array.from({ length: 7 }, (_, index) => shiftDay(key, index - preceding))
}

export function monthStart(key: DateKey, delta = 0): DateKey {
  const date = fromKey(key)
  return dateKey(new Date(date.getFullYear(), date.getMonth() + delta, 1, 12))
}

export const weekdays = ['一', '二', '三', '四', '五', '六', '日']
export const dayLabel = (key: DateKey) => fromKey(key).toLocaleDateString('zh-CN', { month: 'long', day: 'numeric' })
export const monthLabel = (key: DateKey) => fromKey(key).toLocaleDateString('zh-CN', { year: 'numeric', month: 'long' })
export const weekdayLabel = (key: DateKey) => fromKey(key).toLocaleDateString('zh-CN', { weekday: 'long' })
