<script setup lang="ts">
import { CalendarDays, ChevronLeft, ChevronRight } from 'lucide-vue-next'
import { computed } from 'vue'
import { useDiaryApi } from '../api/diaryRepository'
import PageHeading from '../components/PageHeading.vue'
import PrivatePhoto from '../components/PrivatePhoto.vue'
import { useApiDay } from '../composables/useApiDay'
import { usePrivateQuery } from '../composables/usePrivateQuery'
import { fromKey, monthLabel, monthStart, shiftDay, weekdays } from '../utils/dates'

const api = useDiaryApi()
const { selected, today, setDate } = useApiDay()
const first = computed(() => monthStart(selected.value))
const response = usePrivateQuery(() => first.value.slice(0, 7), api.calendar)
const { current, error, pending } = response
const stats = computed(() => new Map(current.value?.days.map(day => [day.date, day])))
const leading = computed(() => (fromKey(first.value).getDay() + 6) % 7)
const dates = computed(() => Array.from(
  { length: fromKey(shiftDay(monthStart(first.value, 1), -1)).getDate() },
  (_, index) => shiftDay(first.value, index),
))
</script>

<template>
  <div class="calendar-page">
    <RouterLink class="text-action" :to="{ name: 'diary', query: { date: selected } }">返回手账</RouterLink>
    <PageHeading title="饮食月历"><button class="button" @click="setDate(today)"><CalendarDays /> 回到本月</button></PageHeading>
    <section class="calendar-paper paper-panel panel-pad" aria-label="月历">
      <header class="calendar-header">
        <button class="icon-button button-quiet" aria-label="上个月" @click="setDate(monthStart(first, -1))"><ChevronLeft /></button>
        <h2>{{ monthLabel(first) }}</h2>
        <button class="icon-button button-quiet" aria-label="下个月" @click="setDate(monthStart(first, 1))"><ChevronRight /></button>
      </header>
      <p v-if="error" class="form-error" role="alert">{{ error }} <button class="text-action" @click="response.reload()">重新读取</button></p>
      <p v-if="pending" class="caption" role="status">正在读取月历…</p>
      <div class="weekdays"><span v-for="label in weekdays" :key="label">{{ label }}</span></div>
      <div class="days">
        <span v-for="index in leading" :key="'blank-' + index" aria-hidden="true"></span>
        <RouterLink v-for="(date, index) in dates" :key="date" class="day" :class="{ today: date === today }"
          :to="{ name: 'diary', query: { date } }" :aria-label="date + (stats.has(date) ? ' 有记录' : '')">
          <time :datetime="date">{{ index + 1 }}</time>
          <PrivatePhoto v-if="stats.get(date)?.representative_media_id" :id="stats.get(date)!.representative_media_id!" class="calendar-thumb"
            :presentation="stats.get(date)?.representative_use_original ? undefined : 'thumbnail'" alt="" />
          <span v-if="stats.has(date)" class="caption day-count">{{ stats.get(date)?.meal_count }} 笔</span>
        </RouterLink>
      </div>
      <footer v-if="current" class="caption">{{ current.days.length }} 天有记录 · {{ current.days.reduce((total, day) => total + day.meal_count, 0) }} 笔用餐记录</footer>
    </section>
  </div>
</template>

<style scoped>
.calendar-page { max-width: 51rem; margin: 0 auto; }
.calendar-paper { border-radius: 0; background: var(--color-sheet) var(--paper-texture); }
.calendar-header, footer { display: flex; justify-content: space-between; align-items: center; gap: .5rem; }
.calendar-header h2 { font: 700 clamp(1.25rem, 3vw, 1.85rem) var(--font-serif); }
.weekdays, .days { display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)); text-align: center; }
.weekdays { color: var(--color-muted); font-size: .84rem; padding-block: .6rem; }
.days { border-top: 1px solid var(--color-line); border-left: 1px solid var(--color-line); }
.days > * { min-width: 0; min-height: clamp(3.2rem, 7vw, 6.85rem); border-bottom: 1px solid var(--color-line); border-right: 1px solid var(--color-line); }
.day { display: grid; gap: .1rem; justify-items: center; align-content: start; padding: .26rem .12rem; }
.day:hover { background: var(--color-sheet-glaze); }
.day.today { background: var(--color-leaf); }
.day time { font: 700 1rem var(--font-editorial); }
.calendar-thumb { width: min(92%, 4.25rem); height: clamp(1.4rem, 4vw, 3.25rem); }
.day-count { font-size: .72rem; }
footer { justify-content: center; margin-top: .6rem; }
@media (max-width: 480px) { .calendar-paper { padding: .52rem; } }
</style>
