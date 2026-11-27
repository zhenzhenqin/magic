<script setup lang="ts">
import { BookOpen, CalendarDays, NotebookPen, Plus, Utensils } from 'lucide-vue-next'
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { nutrientFields, useDiaryApi } from '../api/diaryRepository'
import type { Meal, NutrientKey } from '../api/diaryRepository'
import DateStrip from '../components/DateStrip.vue'
import ModalSurface from '../components/ModalSurface.vue'
import PrivatePhoto from '../components/PrivatePhoto.vue'
import { useApiDay } from '../composables/useApiDay'
import { usePrivateQuery } from '../composables/usePrivateQuery'
import { authMessage, useAuth } from '../stores/auth'
import { dayLabel, weekdayLabel, weekFor } from '../utils/dates'
import { mealLabels } from '../utils/labels'

const { selected, today, setDate } = useApiDay()
const auth = useAuth()
const api = useDiaryApi()
const router = useRouter()
const page = ref(1)
const pageDay = ref('')
const query = usePrivateQuery(
  () => ({ day: selected.value, page: pageDay.value === selected.value ? page.value : 1 }),
  ({ day, page: current }, signal) => api.meals(day, current, signal),
)
const summary = usePrivateQuery(() => selected.value, api.daily)
const monthKeys = computed(() => [...new Set(weekFor(selected.value).map(date => date.slice(0, 7)))].join(','))
const recorded = usePrivateQuery(() => monthKeys.value, async (keys, signal) =>
  (await Promise.all(keys.split(',').map(month => api.calendar(month, signal)))).flatMap(result => result.days.map(day => day.date)))
const { current: results, pending, error } = query
const { current: daily } = summary
const reportOpen = ref(false)
const focused = ref<string>()
const confirming = ref(false)
const deleting = ref(false)
const detailError = ref('')
const detail = usePrivateQuery(() => focused.value, (id, signal) => id ? api.meal(id, signal) : Promise.resolve(undefined))
const { current: meal, pending: detailLoading, error: loadError } = detail
const visibleNutrients = computed(() => (Object.keys(nutrientFields) as NutrientKey[]).filter(key =>
  key === 'calories_kcal' ? auth.preferences?.show_calories : auth.preferences?.show_nutrition))

const entries = computed(() => [...(results.value?.items ?? [])].sort((first, second) => first.local_time.localeCompare(second.local_time)))
const calories = computed(() => daily.value?.nutrition.calories_kcal)
function captionCalories(entry: Meal) {
  const known = entry.items.filter(item => item.calories_kcal !== null)
  if (!known.length) return '热量未知'
  const total = known.reduce((value, item) => value + Number(item.calories_kcal), 0)
  const kind = known.some(item => item.source === 'ai_edited') ? ' · 含人工修正'
    : known.some(item => item.source === 'ai') ? ' · 含估算' : ''
  return new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 1 }).format(total)
    + ' kcal' + (known.length < entry.items.length ? ' · 部分' : '') + kind
}
const add = (kind?: string) => router.push({ name: 'capture', query: { date: selected.value, kind } })
function paginate(next: number) { pageDay.value = selected.value; page.value = next }
function close() { if (!deleting.value) focused.value = undefined }
watch(() => focused.value, () => { confirming.value = false; detailError.value = '' })
watch(selected, close)
watch(() => router.currentRoute.value.query.meal, value => {
  if (typeof value === 'string') focused.value = value
}, { immediate: true })
async function remove(item: Meal) {
  if (deleting.value) return
  deleting.value = true
  try {
    await api.remove(item.id, item.version)
    focused.value = undefined
    if (results.value?.items.length === 1 && page.value > 1) paginate(page.value - 1)
    query.reload()
    summary.reload()
    recorded.reload()
  } catch (failure) {
    detailError.value = authMessage(failure)
  } finally {
    deleting.value = false
  }
}
</script>

<template>
  <div class="notebook-home">
    <header class="diary-cover">
      <h1>美食手账</h1>
      <button type="button" class="text-action report-action" @click="reportOpen = true"><NotebookPen aria-hidden="true" /> 周报 <small>待开放</small></button>
    </header>
    <DateStrip notebook :selected="selected" :today="today" :recorded="recorded.current.value" @select="setDate" />
    <section class="notebook-sheet" aria-labelledby="entries-heading">
        <header class="sheet-header">
          <div>
            <h2 id="entries-heading"><time :datetime="selected">{{ dayLabel(selected) }}</time> <small>{{ selected === today ? '今天' : weekdayLabel(selected) }}</small></h2>
            <p v-if="auth.preferences?.show_calories && calories" class="sheet-calories">
              <template v-if="calories.value !== null">
                <strong>{{ calories.value }}</strong> <small>kcal</small>
                <small v-if="!calories.complete"> · 部分记录</small>
                <small v-if="daily?.nutrition_sources.calories_kcal.edited"> · 含人工修正</small>
                <small v-else-if="daily?.nutrition_sources.calories_kcal.estimated"> · 含估算</small>
              </template>
              <small v-else>热量未记录</small>
            </p>
          </div>
          <div class="sheet-actions">
            <RouterLink class="text-action" :to="{ name: 'calendar', query: { date: selected } }"><CalendarDays aria-hidden="true" /> 月历</RouterLink>
            <button class="text-action" @click="add()"><Plus aria-hidden="true" /> 记一笔</button>
          </div>
        </header>
        <p v-if="pending" class="caption" role="status">正在读取手账…</p>
        <div v-else-if="error" class="empty-state"><p>{{ error }}</p><button class="button" @click="query.reload()">重新读取</button></div>
        <div v-else-if="!results?.total" class="empty-state">
          <BookOpen /><h3>这一页还留白</h3><p>想记住今天的哪一种味道？</p><button class="button button-primary" @click="add()"><Plus /> 写下第一餐</button>
        </div>
        <div v-else>
          <div class="scrap-grid">
            <button v-for="entry in entries" :key="entry.id" class="scrap"
              :aria-label="'查看记录 ' + entry.items.map(item => item.food_name).join('、')" @click="focused = entry.id">
              <span v-if="entry.media.length" class="scrap-gallery" :class="{ 'extra-photos': entry.media.length > 1 }">
                <PrivatePhoto v-for="image in entry.media.slice(0, 3)" :key="image.id" :id="image.id" presentation="sticker" alt="" />
              </span>
              <span v-else class="text-scrap"><Utensils aria-hidden="true" /></span>
              <strong>{{ entry.items.map(item => item.food_name).join('、') }}</strong>
              <span v-if="auth.preferences?.show_calories" class="scrap-nutrition">{{ captionCalories(entry) }}</span>
              <span class="scrap-meal">{{ mealLabels[entry.meal_type].label }} · {{ entry.local_time.slice(0, 5) }}</span>
              <span v-if="entry.note" class="scrap-note">{{ entry.note }}</span>
            </button>
          </div>
          <div v-if="results.total > results.limit" class="toolbar page-buttons">
            <button class="button" :disabled="results.page === 1" @click="paginate(results.page - 1)">上一页</button>
            <span>{{ results.page }} / {{ Math.ceil(results.total / results.limit) }}</span>
            <button class="button" :disabled="results.page * results.limit >= results.total" @click="paginate(results.page + 1)">下一页</button>
          </div>
        </div>
      <footer v-if="daily?.items && visibleNutrients.length" class="day-notes">
        <details>
          <summary>展开营养数据</summary>
          <dl>
            <div v-for="key in visibleNutrients" :key="key">
              <dt>{{ nutrientFields[key].label }}</dt>
              <dd>
                {{ daily.nutrition[key].value === null ? '未知' : daily.nutrition[key].value + ' ' + nutrientFields[key].unit }}
                <small v-if="daily.nutrition[key].value !== null && !daily.nutrition[key].complete"> · 部分记录</small>
                <small v-if="daily.nutrition_sources?.[key]?.estimated"> · 含估算</small>
                <small v-if="daily.nutrition_sources?.[key]?.edited"> · 含人工修正</small>
                <small v-if="daily.nutrition_sources?.[key]?.simulated"> · 含模拟</small>
              </dd>
            </div>
          </dl>
        </details>
      </footer>
    </section>
    <ModalSurface :open="reportOpen" title="周报" @close="reportOpen = false">
      <p class="caption">周报功能待开放。现在可以在月历中查看已有的饮食记录。</p>
      <RouterLink class="button" :to="{ name: 'calendar', query: { date: selected } }">查看月历</RouterLink>
    </ModalSurface>
    <ModalSurface :open="!!focused" title="饮食详情" @close="close">
      <p v-if="detailLoading" class="caption" role="status">正在读取详情…</p>
      <p v-if="loadError" class="form-error" role="alert">{{ loadError }}</p>
      <template v-if="meal">
        <p class="caption">{{ meal.local_date }} · {{ mealLabels[meal.meal_type].label }} · {{ meal.local_time.slice(0, 5) }}</p>
        <div v-if="meal.media.length" class="detail-photos"><PrivatePhoto v-for="image in meal.media" :key="image.id" :id="image.id" original /></div>
        <details v-if="meal.media.length"><summary>查看美食贴纸</summary><div class="detail-photos detail-stickers"><PrivatePhoto v-for="image in meal.media" :key="image.id" :id="image.id" presentation="sticker" alt="美食贴纸" /></div></details>
        <p v-if="meal.note">{{ meal.note }}</p>
        <article v-for="item in meal.items" :key="item.id" class="detail-item">
          <strong>{{ item.food_name }}</strong>
          <p v-if="item.source !== 'manual'" class="caption">{{ item.ai_provider === 'fake' ? '模拟估算' : 'AI 估算' }}<span v-if="item.source === 'ai_edited'"> · 已人工修正</span></p>
          <p v-if="item.category || item.weight_g !== null" class="caption">{{ [item.category, item.weight_g === null ? '' : item.weight_g + ' g'].filter(Boolean).join(' · ') }}</p>
          <p v-if="item.note" class="caption">{{ item.note }}</p>
          <details v-if="visibleNutrients.length"><summary>营养信息</summary><p v-for="key in visibleNutrients" :key="key" class="caption">{{ nutrientFields[key].label }} {{ item[key] === null ? '未知' : item[key] + ' ' + nutrientFields[key].unit }}</p></details>
        </article>
        <p v-if="detailError" class="form-error" role="alert">{{ detailError }}</p>
        <div class="toolbar" v-if="!confirming">
          <RouterLink class="button" :to="{ name: 'capture', query: { edit: meal.id } }">编辑记录</RouterLink>
          <button class="button button-danger" @click="confirming = true">删除记录</button>
        </div>
        <div v-else class="toolbar">
          <p>确认删除这餐及所有食物明细？</p>
          <button class="button button-danger" :disabled="deleting" @click="remove(meal)">确认删除</button>
          <button class="button" :disabled="deleting" @click="confirming = false">取消</button>
        </div>
      </template>
    </ModalSurface>
  </div>
</template>

<style scoped>
.notebook-home { max-width: 51rem; margin: auto; }
.diary-cover { display: flex; justify-content: space-between; align-items: center; gap: .75rem; margin-bottom: .65rem; }
h1 { font: 700 clamp(1.6rem, 5vw, 2.65rem)/1.16 var(--font-serif); letter-spacing: -.035em; color: #222; }
.report-action { white-space: nowrap; }
.report-action small { padding: .1rem .35rem; color: #6c655f; background: #ebe8e4; border-radius: .25rem; font-size: .65rem; }
.notebook-sheet { position: relative; min-height: 26rem; padding: clamp(1rem, 4.4vw, 2.2rem) clamp(.85rem, 4.6vw, 2.6rem) 1.65rem clamp(1.5rem, 6.5vw, 3.65rem); border-radius: .65rem 1.8rem 1.8rem .65rem; isolation: isolate; border: 1px solid #e4dfd8; background-color: #fffefc; background-image: linear-gradient(90deg, #eee8e043, transparent 11%), var(--paper-texture); box-shadow: 0 6px 16px #4e3f3011, 4px 4px 0 #eae6e0, 5px 5px 0 #ded9d3; }
.notebook-sheet::before { position: absolute; content: ""; inset: .7rem auto .7rem clamp(.12rem, 1.25vw, .8rem); width: .95rem; background: radial-gradient(circle at 50% 50%, #eeeae4 0, #eeeae4 3px, #ddd6ce 3.5px, transparent 4.2px) 0 0 / 100% 2.05rem; pointer-events: none; }
.sheet-header { display: flex; align-items: start; justify-content: space-between; gap: .45rem; margin-bottom: .6rem; }
.sheet-header h2 { font: 600 clamp(1.12rem, 4vw, 1.75rem)/1.2 var(--font-hand); color: var(--diary-ink-soft); }
.sheet-header h2 small { font-size: .75em; margin-left: .2rem; color: #766e65; }
.sheet-calories { color: var(--diary-ink-soft); line-height: 1.1; margin-top: .35rem; font-family: var(--font-hand); }
.sheet-calories strong { font-size: clamp(1.48rem, 6vw, 2.7rem); font-weight: 500; }
.sheet-calories small { font-size: .79rem; color: #786e64; }
.sheet-actions { display: flex; gap: .55rem; flex-wrap: wrap; justify-content: end; }
.sheet-actions .text-action { color: #4c433c; font-size: .77rem; min-height: 2rem; }
.sheet-actions svg { width: .9rem; }
.scrap-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); align-items: start; column-gap: clamp(.55rem, 4vw, 2.4rem); row-gap: .65rem; margin: .15rem 0 1rem; }
.scrap { min-width: 0; display: flex; flex-direction: column; align-items: center; gap: .12rem; text-align: center; border-radius: .6rem; padding: .45rem .08rem .58rem; overflow-wrap: anywhere; }
.scrap:nth-child(even) { margin-top: clamp(.22rem, 2vw, 1.1rem); }
.scrap:hover .scrap-gallery, .scrap:focus-visible .scrap-gallery { transform: translateY(-2px); }
.scrap-gallery { display: grid; place-items: center; width: min(100%, 15rem); height: clamp(5.4rem, 23vw, 11rem); margin-bottom: .35rem; transition: transform .2s var(--ease-gentle); }
.scrap:nth-child(4n+2) .scrap-gallery { width: min(91%, 13rem); }
.scrap:nth-child(4n+3) .scrap-gallery { width: 87%; height: clamp(5.1rem, 21vw, 10rem); }
.scrap-gallery.extra-photos { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.extra-photos > :nth-child(n+3) { display: none; }
.scrap strong { color: var(--diary-ink-soft); font: 600 clamp(1rem, 4.3vw, 1.52rem)/1.17 var(--font-hand); }
.scrap-nutrition { color: #766e65; font: 500 clamp(.75rem, 2.9vw, .99rem) var(--font-hand); }
.scrap-meal, .scrap-note { color: #74706a; font-size: .67rem; }
.text-scrap { min-height: 2.15rem; padding-top: .25rem; color: #b1a195; }
.text-scrap svg { width: 1.25rem; }
.day-notes { color: var(--color-muted); font-size: .83rem; margin-top: .6rem; border-top: 1px solid var(--color-line); padding-top: .55rem; }
.day-notes dl { display: grid; gap: .45rem; margin-top: .55rem; }
.day-notes dl div { display: flex; flex-wrap: wrap; gap: .4rem; justify-content: space-between; }
.day-notes dd { margin: 0; }
.page-buttons { justify-content: center; margin-top: .6rem; }
.detail-photos { display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: .5rem; }
.detail-stickers { height: 10rem; margin-block: .4rem; }
.detail-item { border-top: 1px solid var(--color-line); padding-top: .55rem; overflow-wrap: anywhere; }
.detail-item details { margin-top: .25rem; }
@media (max-width: 480px) {
  .sheet-actions { flex-direction: column; gap: .06rem; }
  .notebook-sheet { margin-right: .2rem; }
  .sheet-header { margin-bottom: .18rem; }
  .scrap-grid { row-gap: .12rem; margin-top: 0; }
  .scrap { padding-block: .26rem .27rem; gap: .07rem; }
  .scrap:nth-child(even) { margin-top: .2rem; }
  .scrap-gallery { height: clamp(4.1rem, 19vw, 5.8rem); margin-bottom: .22rem; }
  .scrap:nth-child(4n+3) .scrap-gallery { height: clamp(3.9rem, 18vw, 5.6rem); }
}
</style>
