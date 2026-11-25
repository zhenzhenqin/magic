<script setup lang="ts">
import { BookHeart, CalendarDays, Leaf, Plus, Sprout } from 'lucide-vue-next'
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import DateStrip from '../components/DateStrip.vue'
import FoodSticker from '../components/FoodSticker.vue'
import MealDetail from '../components/MealDetail.vue'
import MealSpread from '../components/MealSpread.vue'
import { useDiaryDate } from '../composables/useDiaryDate'
import { useDiary } from '../stores/diary'
import type { Meal, MealItem, MealKind } from '../types/domain'
import { dayLabel, todayKey, weekdayLabel } from '../utils/dates'

const diary = useDiary()
const route = useRoute()
const router = useRouter()
const { selectedDate, setDate } = useDiaryDate()
const readonly = computed(() => route.name === 'friend-diary')
const ownerId = computed(() => readonly.value ? String(route.params.id) : diary.account.id)
const owner = computed(() => diary.person(ownerId.value))
const access = computed(() => diary.permissions(ownerId.value))
const meals = computed(() => diary.meals(selectedDate.value, ownerId.value))
const dates = computed(() => diary.meals(undefined, ownerId.value).map(meal => meal.date))
const items = computed(() => meals.value.flatMap(meal => meal.items))
const favorites = computed(() => readonly.value ? [] : diary.catalog().filter(food => food.favorite))
const nutrition = computed(() => items.value.reduce((total, item) => ({
  calories: total.calories + (item.calories ?? 0),
  protein: total.protein + (item.nutrition?.protein ?? 0),
  carbs: total.carbs + (item.nutrition?.carbs ?? 0),
  fat: total.fat + (item.nutrition?.fat ?? 0),
}), { calories: 0, protein: 0, carbs: 0, fat: 0 }))
const detail = ref<{ meal: Meal; item: MealItem }>()
watch([selectedDate, ownerId, access], () => { detail.value = undefined })
const add = (kind?: MealKind) => router.push({ name: 'capture', query: { date: selectedDate.value, kind } })
function remove(id: string) {
  diary.deleteMeal(id)
  detail.value = undefined
}
</script>

<template>
  <div class="diary-page">
    <div v-if="readonly" class="breadcrumb"><RouterLink to="/friends" class="text-action">饭搭子</RouterLink><span>/</span><span>好友手账</span></div>
    <header class="diary-cover">
      <div class="cover-copy">
        <div class="cover-kicker"><Sprout aria-hidden="true" /><span>{{ readonly ? '好友手账 · 只读' : '我的美食日记' }}</span></div>
        <h1>{{ readonly ? (owner?.nickname ?? '好友') + '的手账' : '美食手账' }}</h1>
        <p class="date-title"><time :datetime="selectedDate">{{ dayLabel(selectedDate) }}</time><span>{{ weekdayLabel(selectedDate) }}</span></p>
      </div>
      <div v-if="!readonly" class="cover-art" aria-hidden="true">
        <svg class="swoop" viewBox="0 0 270 140" fill="none"><path d="M11 111c40-26 108-1 151-29 29-19 29-39 61-43 17-2 29 5 34 18" stroke="currentColor" stroke-width="1.25" stroke-dasharray="3 5" stroke-linecap="round"/><path d="M184 15v19m-10-9h20M45 48v14m-7-7h14M239 94v14m-7-7h14" stroke="currentColor" stroke-width="1.35" stroke-linecap="round"/></svg>
        <FoodSticker class="cover-bread" id="croissant" decorative />
        <FoodSticker class="cover-coffee" id="coffee" decorative />
      </div>
      <RouterLink v-if="!readonly" class="button cover-calendar" :to="{ name: 'calendar', query: { date: selectedDate } }"><CalendarDays /> 月历</RouterLink>
      <RouterLink v-else-if="access.catalog" class="button cover-calendar" :to="{ name: 'friend-catalog', params: { id: ownerId } }">好友图鉴</RouterLink>
    </header>

    <DateStrip :selected="selectedDate" :recorded="dates" @select="setDate" />

    <div class="diary-columns" :class="{ 'no-sidebar': readonly }">
      <section class="entries" aria-labelledby="entries-heading">
        <div class="section-heading">
          <h2 id="entries-heading">{{ selectedDate === todayKey() ? '今天的记录' : '当天的记录' }}</h2>
          <button v-if="!readonly" class="text-action" @click="add()"><Plus /> 记一笔</button>
          <button v-else-if="selectedDate !== todayKey()" class="text-action" @click="setDate(todayKey())">回到今天</button>
        </div>
        <div v-if="readonly && (!access.records || (!access.history && selectedDate !== todayKey()))" class="paper-panel empty-state" role="status">
          <BookHeart /><p>{{ access.records ? '好友仅分享当天记录。' : '好友尚未授权你查看饮食记录。' }}</p>
        </div>
        <template v-else>
          <p v-if="!meals.length" class="empty-hint">{{ readonly ? '这一天暂时没有共享记录。' : '这一页暂时留白，随时可以记下这一餐。' }}</p>
          <MealSpread :meals="meals" :readonly="readonly" @open="(meal, item) => detail = { meal, item }" @add="add" />
        </template>
      </section>
      <aside v-if="!readonly" class="diary-sidebar">
        <section class="daily-note">
          <div class="aside-title"><Leaf aria-hidden="true" /><h2>{{ selectedDate === todayKey() ? '今日小结' : '当日小结' }}</h2></div>
          <p class="daily-count"><strong>{{ meals.length }}</strong> 笔记录 <span>·</span> <strong>{{ items.length }}</strong> 样美食</p>
          <details v-if="items.some(item => item.calories !== undefined || item.nutrition)">
            <summary>展开营养数据</summary>
            <div class="daily-nutrition"><span>热量 {{ nutrition.calories }} kcal</span><span>蛋白质 {{ nutrition.protein }} g</span><span>碳水 {{ nutrition.carbs }} g</span><span>脂肪 {{ nutrition.fat }} g</span><small>演示数值</small></div>
          </details>
        </section>
        <section class="favorites-note paper-panel">
          <div class="aside-title"><BookHeart aria-hidden="true" /><h2>我的收藏</h2></div>
          <div v-if="favorites.length" class="favorite-art" aria-hidden="true">
            <FoodSticker v-for="food in favorites.slice(0, 3)" :key="food.id" :id="food.stickerId" decorative />
          </div>
          <p v-else class="caption">在图鉴里收藏喜欢的食物。</p>
          <RouterLink class="text-action" :to="{ name: 'catalog', query: { favorites: '1' } }">查看图鉴收藏</RouterLink>
        </section>
      </aside>
    </div>
    <MealDetail :meal="detail?.meal" :item="detail?.item" :readonly="readonly" @close="detail = undefined" @remove="remove" />
  </div>
</template>

<style scoped>
.breadcrumb { display: flex; gap: calc(var(--space-unit) * 4.8); align-items: center; color: var(--color-muted); font-size: .86rem; }
.diary-cover { min-height: 12.2rem; margin-bottom: calc(var(--space-unit) * 8.96); position: relative; isolation: isolate; overflow: hidden; padding: clamp(calc(var(--space-unit) * 8), 3.1vw, calc(var(--space-unit) * 16)); display: flex; align-items: end; justify-content: space-between; gap: calc(var(--space-unit) * 4.4); border: 1px solid var(--color-line-warm); border-radius: var(--radius-paper); background: var(--color-paper-warm); background-image: var(--paper-texture), radial-gradient(ellipse at 76% 110%, var(--color-peach-glaze), transparent 62%); }
.cover-copy { position: relative; z-index: 1; }
.cover-kicker { color: var(--color-text-strong); display: flex; gap: calc(var(--space-unit) * 3.2); align-items: center; font-weight: 700; font-size: .84rem; letter-spacing: .09em; }
.cover-kicker svg { width: 1.05rem; height: 1.05rem; stroke-width: 1.55; }
h1 { margin: calc(var(--space-unit) * 3.6) 0 calc(var(--space-unit) * 4.16); font: 700 clamp(2.6rem, 5vw, 4.5rem)/1.08 var(--font-serif); letter-spacing: -.06em; white-space: nowrap; }
.date-title { display: flex; gap: calc(var(--space-unit) * 3.84); align-items: baseline; }
.date-title time { font-weight: 700; }
.date-title span { color: var(--color-text-strong); font-size: .88rem; }
.cover-calendar { position: relative; z-index: 1; white-space: nowrap; background: var(--color-sheet-glaze); }
.cover-art { position: absolute; inset: 0 9% 0 auto; width: clamp(12rem, 38%, 24rem); pointer-events: none; }
.cover-bread { position: absolute; width: 52%; height: 76%; top: 14%; left: 0; transform: rotate(-19deg); }
.cover-coffee { position: absolute; width: 53%; height: 74%; top: 7%; right: 0; transform: rotate(12deg); }
.swoop { width: 100%; height: 100%; position: absolute; color: var(--color-earth); opacity: .65; }
.diary-columns { display: grid; grid-template-columns: minmax(0, 1fr) minmax(13.6rem, 26%); gap: clamp(calc(var(--space-unit) * 8), 2.6vw, calc(var(--space-unit) * 16)); margin-top: calc(var(--space-unit) * 11.2); }
.diary-columns.no-sidebar { grid-template-columns: minmax(0, 1fr); }
.section-heading, .aside-title { display: flex; align-items: center; justify-content: space-between; gap: calc(var(--space-unit) * 4.4); }
.section-heading { margin-bottom: calc(var(--space-unit) * 3.2); min-height: var(--tap-size); }
.section-heading h2 { font: 700 clamp(1.35rem, 2.8vw, 1.8rem)/1.28 var(--font-serif); }
.empty-hint { padding-bottom: calc(var(--space-unit) * 5.6); color: var(--color-muted); font-size: .88rem; }
.diary-sidebar { display: flex; flex-direction: column; gap: calc(var(--space-unit) * 6.8); padding-top: calc(var(--space-unit) * 2); }
.daily-note, .favorites-note { padding: calc(var(--space-unit) * 8); }
.daily-note { border-radius: var(--radius-card); background: var(--color-leaf-selected); border: 1px solid var(--color-line-leaf); }
.aside-title { justify-content: flex-start; }
.aside-title svg { color: var(--color-sage-deep); width: 1.05rem; height: 1.05rem; stroke-width: 1.6; }
.aside-title h2 { font: 700 1.15rem/1.25 var(--font-serif); }
.daily-count { display: flex; align-items: baseline; gap: calc(var(--space-unit) * 3.04); margin: calc(var(--space-unit) * 6.4) 0; white-space: nowrap; font-size: .86rem; }
.daily-count strong { font: 700 1.7rem/1 var(--font-editorial); color: var(--color-sage-deep); }
.daily-count span { color: var(--color-muted); }
.daily-note summary { border-top: 1px solid var(--color-line-leaf); padding-top: calc(var(--space-unit) * 4.8); font-size: .85rem; color: var(--color-sage-deep); font-weight: 650; }
.daily-nutrition { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: calc(var(--space-unit) * 2.4); margin-top: calc(var(--space-unit) * 4); font-size: .78rem; }
.daily-nutrition small { grid-column: 1 / -1; color: var(--color-muted); }
.favorite-art { display: flex; gap: calc(var(--space-unit) * 0.4); align-items: center; height: 5rem; padding-top: calc(var(--space-unit) * 2.8); }
.favorite-art .sticker { flex: 1 1 0; min-width: 0; height: 100%; transform: rotate(-12deg); }
.favorite-art .sticker:nth-child(2) { transform: rotate(6deg) translateY(.6rem); }
.favorite-art .sticker:nth-child(3) { transform: rotate(12deg); }
@media (max-width: 1050px) and (min-width: 901px) { .diary-columns { grid-template-columns: minmax(0, 1fr); } .diary-sidebar { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 680px) {
  .diary-columns { grid-template-columns: minmax(0, 1fr); margin-top: calc(var(--space-unit) * 6.64); }
  .diary-cover { min-height: 9.7rem; margin-bottom: calc(var(--space-unit) * 5.44); padding: calc(var(--space-unit) * 7.04); }
  .cover-kicker { font-size: .78rem; }
  .cover-art { width: 45%; inset: 0 1% 1rem auto; opacity: .93; }
  .cover-bread { width: 70%; height: 71%; left: 1%; top: 4%; }
  .cover-coffee { width: 61%; height: 60%; top: 0; right: 0; }
  .cover-calendar { min-height: 2.35rem; padding: calc(var(--space-unit) * 2.24) calc(var(--space-unit) * 4.16); font-size: .82rem; }
  .cover-calendar svg { width: 1rem; height: 1rem; }
  h1 { font-size: clamp(1.9rem, 9.4vw, 3.15rem); white-space: normal; }
  .date-title { gap: calc(var(--space-unit) * 2.8); font-size: .87rem; }
  .date-title span { font-size: .76rem; }
  .diary-sidebar { gap: calc(var(--space-unit) * 5.6); }
}
</style>
