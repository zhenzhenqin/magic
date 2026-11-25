<script setup lang="ts">
import { computed } from 'vue'
import PageHeading from '../components/PageHeading.vue'
import { useDiary } from '../stores/diary'
import { dayLabel, shiftDay, todayKey } from '../utils/dates'

const diary = useDiary()
const week = computed(() => Array.from({ length: 7 }, (_, index) => {
  const date = shiftDay(todayKey(), index - 6)
  const meals = diary.meals(date)
  return { date, meals: meals.length, foods: meals.reduce((total, meal) => total + meal.items.length, 0) }
}))
const highest = computed(() => Math.max(1, ...week.value.map(day => day.foods)))
</script>

<template>
  <div class="stats">
    <RouterLink to="/me" class="text-action">返回我的</RouterLink>
    <PageHeading title="饮食统计" subtitle="最近七天的演示记录" />
    <section class="paper-panel panel-pad">
      <h2>每日记录</h2>
      <ul class="stat-list">
        <li v-for="day in week" :key="day.date">
          <span>{{ dayLabel(day.date) }}</span>
          <div class="track" aria-hidden="true"><i :style="{ width: day.foods / highest * 100 + '%' }"></i></div>
          <span>{{ day.meals }} 笔 · {{ day.foods }} 样</span>
        </li>
      </ul>
    </section>
  </div>
</template>

<style scoped>
.stats { max-width: 43rem; margin-inline: auto; }
h2 { font: 700 1.35rem var(--font-serif); }
.stat-list { display: grid; gap: calc(var(--space-unit) * 6.8); margin-top: calc(var(--space-unit) * 8); }
.stat-list li { display: grid; grid-template-columns: 5rem minmax(0, 1fr) 5.5rem; gap: calc(var(--space-unit) * 4.4); align-items: center; font-size: .88rem; }
.track { background: var(--color-canvas-hover); height: .4rem; border-radius: var(--radius-pill); }
.track i { display: block; height: 100%; border-radius: inherit; background: var(--color-sage); }
</style>
