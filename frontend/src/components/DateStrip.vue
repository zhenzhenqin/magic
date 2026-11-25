<script setup lang="ts">
import { ChevronLeft, ChevronRight } from 'lucide-vue-next'
import { computed } from 'vue'
import type { DateKey } from '../types/domain'
import { fromKey, shiftDay, todayKey, weekFor, weekdays } from '../utils/dates'

const props = defineProps<{ selected: DateKey; recorded?: DateKey[] }>()
const emit = defineEmits<{ select: [date: DateKey] }>()
const week = computed(() => weekFor(props.selected))
</script>

<template>
  <div class="date-strip" aria-label="一周日期选择器">
    <button class="icon-button button-quiet change-week" aria-label="上一周" @click="emit('select', shiftDay(selected, -7))"><ChevronLeft /></button>
    <div class="week-grid">
      <button v-for="(date, index) in week" :key="date" class="day-pick" :class="{ selected: date === selected }"
        :aria-label="date + (date === todayKey() ? ' 今天' : '')" :aria-pressed="date === selected" @click="emit('select', date)">
        <span>{{ weekdays[index] }}</span>
        <strong>{{ fromKey(date).getDate() }}</strong>
        <i v-if="recorded?.includes(date)" class="dot" aria-label="有记录"></i>
      </button>
    </div>
    <button class="icon-button button-quiet change-week" aria-label="下一周" @click="emit('select', shiftDay(selected, 7))"><ChevronRight /></button>
  </div>
</template>

<style scoped>
.date-strip { display: flex; align-items: center; padding: calc(var(--space-unit) * 3.6) calc(var(--space-unit) * 4.16); gap: calc(var(--space-unit) * 2.4); border: 1px solid var(--color-line); border-radius: var(--radius-card); background: var(--color-sheet-glaze); }
.week-grid { flex: 1; min-width: 0; display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)); gap: calc(var(--space-unit) * 2.4); }
.day-pick { display: flex; position: relative; flex-direction: column; justify-content: center; align-items: center; gap: calc(var(--space-unit) * 0.96); min-height: 3.6rem; border: 1px solid transparent; border-radius: var(--radius-small); color: var(--color-muted); font-size: .83rem; padding-bottom: calc(var(--space-unit) * 2); }
.day-pick strong { color: var(--color-ink); font: 700 1.28rem/1.15 var(--font-editorial); }
.day-pick:hover { background: var(--color-leaf-pale); }
.day-pick.selected { background: var(--color-sage-deep); color: var(--color-sheet); }
.day-pick.selected strong { color: var(--color-sheet); }
.dot { width: 4px; height: 4px; background: var(--color-sage); border-radius: var(--radius-round); position: absolute; bottom: .27rem; }
.selected .dot { background: var(--color-leaf-selected); }
@media (max-width: 540px) {
  .date-strip { padding: calc(var(--space-unit) * 2.4) calc(var(--space-unit) * 1.2); gap: 0; }
  .change-week { width: 2rem; }
  .week-grid { gap: calc(var(--space-unit) * 0.96); }
  .day-pick { min-height: 3.4rem; font-size: .75rem; }
  .day-pick strong { font-size: 1.15rem; }
}
</style>
