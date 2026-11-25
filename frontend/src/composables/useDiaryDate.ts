import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { DateKey } from '../types/domain'
import { isDateKey, todayKey } from '../utils/dates'

export function useDiaryDate() {
  const route = useRoute()
  const router = useRouter()
  const selectedDate = computed(() => isDateKey(route.query.date) ? route.query.date : todayKey())
  const setDate = (date: DateKey) => router.push({ query: { ...route.query, date } })
  return { selectedDate, setDate }
}
