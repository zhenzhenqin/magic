<script setup lang="ts">
import { CalendarDays, ChevronLeft, ChevronRight } from 'lucide-vue-next'
import { computed } from 'vue'
import FoodSticker from '../components/FoodSticker.vue'
import PageHeading from '../components/PageHeading.vue'
import { useDiaryDate } from '../composables/useDiaryDate'
import { useDiary } from '../stores/diary'
import { fromKey, monthLabel, monthStart, shiftDay, todayKey, weekdays } from '../utils/dates'

const diary = useDiary()
const { selectedDate, setDate } = useDiaryDate()
const month = computed(() => monthStart(selectedDate.value))
const monthMeals = computed(() => diary.meals().filter(meal => meal.date.startsWith(month.value.slice(0, 7))))
const days = computed(() => {
  const start = month.value
  const blanks = (fromKey(start).getDay() + 6) % 7
  const count = fromKey(shiftDay(monthStart(start, 1), -1)).getDate()
  return [
    ...Array.from({ length: blanks }, (_, index) => ({ key: 'empty-' + index, date: '', day: 0, sticker: undefined })),
    ...Array.from({ length: count }, (_, index) => {
      const date = shiftDay(start, index)
      const items = monthMeals.value.filter(meal => meal.date === date).flatMap(meal => meal.items)
      return { key: date, date, day: index + 1, sticker: items.find(item => item.stickerId), recorded: items.length > 0 }
    }),
  ]
})
</script>

<template>
  <div class="calendar-page">
    <RouterLink class="text-action" :to="{ name: 'diary', query: { date: selectedDate } }">返回手账</RouterLink>
    <PageHeading title="饮食月历">
      <button class="button" @click="setDate(todayKey())"><CalendarDays /> 回到本月</button>
    </PageHeading>
    <section class="calendar-paper paper-panel" aria-label="月历">
      <header class="calendar-header">
        <button class="icon-button button-quiet" aria-label="上个月" @click="setDate(monthStart(month, -1))"><ChevronLeft /></button>
        <h2>{{ monthLabel(month) }}</h2>
        <button class="icon-button button-quiet" aria-label="下个月" @click="setDate(monthStart(month, 1))"><ChevronRight /></button>
      </header>
      <div class="weekday-row"><span v-for="name in weekdays" :key="name">{{ name }}</span></div>
      <div class="calendar-grid">
        <template v-for="day in days" :key="day.key">
          <span v-if="!day.date" class="blank" aria-hidden="true"></span>
          <RouterLink v-else class="calendar-day" :class="{ 'calendar-today': day.date === todayKey() }"
            :to="{ name: 'diary', query: { date: day.date } }" :aria-label="day.date + ('recorded' in day && day.recorded ? ' 有记录' : '')">
            <time :datetime="day.date">{{ day.day }}</time>
            <FoodSticker v-if="day.sticker" :id="day.sticker.stickerId" decorative />
            <i v-else-if="'recorded' in day && day.recorded" class="calendar-dot"></i>
          </RouterLink>
        </template>
      </div>
      <footer class="calendar-totals"><span><strong>{{ new Set(monthMeals.map(meal => meal.date)).size }}</strong> 天有记录</span><span><strong>{{ monthMeals.reduce((sum, meal) => sum + meal.items.length, 0) }}</strong> 道美食</span></footer>
    </section>
  </div>
</template>

<style scoped>
.calendar-page { max-width: 53rem; margin-inline: auto; }
.calendar-paper { padding: clamp(calc(var(--space-unit) * 4.64), 2.5vw, calc(var(--space-unit) * 12)); }
.calendar-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: calc(var(--space-unit) * 4.8); }
.calendar-header h2 { font: 700 clamp(1.3rem, 3vw, 1.85rem)/1.2 var(--font-serif); }
.weekday-row, .calendar-grid { display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)); text-align: center; }
.weekday-row { color: var(--color-muted); font-size: .83rem; padding: calc(var(--space-unit) * 2.4) 0 calc(var(--space-unit) * 4.96); }
.calendar-grid { border-top: 1px solid var(--color-line); border-left: 1px solid var(--color-line); }
.calendar-grid > * { border-right: 1px solid var(--color-line); border-bottom: 1px solid var(--color-line); min-width: 0; min-height: clamp(3.58rem, 7.4vw, 6.5rem); }
.calendar-day { display: grid; grid-template-rows: auto minmax(0, 1fr); justify-items: center; padding: calc(var(--space-unit) * 2.56) calc(var(--space-unit) * 0.64) calc(var(--space-unit) * 1.04); }
.calendar-day:hover { background: var(--color-canvas-hover); }
.calendar-today { background: var(--color-leaf); }
.calendar-day time { font: 700 1rem/1.15 var(--font-editorial); }
.calendar-day .sticker { min-width: 0; height: clamp(2.05rem, 6vw, 4.5rem); transform: rotate(-7deg); }
.calendar-day:nth-child(even) .sticker { transform: rotate(8deg); }
.calendar-dot { align-self: center; width: 5px; height: 5px; border-radius: var(--radius-round); background: var(--color-sage-deep); }
.calendar-totals { display: flex; justify-content: center; gap: calc(var(--space-unit) * 8.8); margin-top: calc(var(--space-unit) * 5.6); color: var(--color-muted); font-size: .88rem; }
.calendar-totals strong { color: var(--color-sage-deep); font: 700 1.4rem var(--font-editorial); }
</style>
