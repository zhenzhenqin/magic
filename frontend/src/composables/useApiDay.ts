import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuth } from '../stores/auth'
import { isDateKey } from '../utils/dates'

export function dateInTimezone(zone: string) {
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: zone, year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts()
  return ['year', 'month', 'day'].map(part => parts.find(field => field.type === part)?.value).join('-')
}

export function useApiDay() {
  const auth = useAuth()
  const route = useRoute()
  const router = useRouter()
  const timezone = computed(() => auth.preferences?.timezone ?? 'Asia/Shanghai')
  const today = computed(() => dateInTimezone(timezone.value))
  const selected = computed(() => isDateKey(route.query.date) ? route.query.date : today.value)
  const setDate = (date: string) => router.push({ query: { ...route.query, date } })
  onMounted(() => { if (!auth.preferences) void auth.loadPreferences().catch(() => {}) })
  return { timezone, today, selected, setDate }
}
