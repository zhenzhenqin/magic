<script setup lang="ts">
import { BookOpen, CalendarDays, Coffee, Leaf, Moon, Plus, Sun, Utensils } from 'lucide-vue-next'
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
import { mealKinds } from '../types/domain'
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
const kinds = { breakfast: Coffee, lunch: Sun, dinner: Moon, snack: Utensils }
const focused = ref<string>()
const confirming = ref(false)
const deleting = ref(false)
const detailError = ref('')
const detail = usePrivateQuery(() => focused.value, (id, signal) => id ? api.meal(id, signal) : Promise.resolve(undefined))
const { current: meal, pending: detailLoading, error: loadError } = detail
const visibleNutrients = computed(() => (Object.keys(nutrientFields) as NutrientKey[]).filter(key =>
  key === 'calories_kcal' ? auth.preferences?.show_calories : auth.preferences?.show_nutrition))

const groups = computed(() => mealKinds.map(kind => ({
  kind, meals: results.value?.items.filter(meal => meal.meal_type === kind) ?? [],
})))
const add = (kind?: string) => router.push({ name: 'capture', query: { date: selected.value, kind } })
function paginate(next: number) { pageDay.value = selected.value; page.value = next }
function close() { if (!deleting.value) focused.value = undefined }
watch(() => focused.value, () => { confirming.value = false; detailError.value = '' })
watch(selected, close)
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
  <div>
    <header class="diary-cover paper-panel">
      <div><p class="caption cover-label"><Leaf /> 我的美食日记</p><h1>美食手账</h1><time :datetime="selected">{{ dayLabel(selected) }} · {{ weekdayLabel(selected) }}</time></div>
      <RouterLink class="button" :to="{ name: 'calendar', query: { date: selected } }"><CalendarDays /> 月历</RouterLink>
    </header>
    <DateStrip :selected="selected" :today="today" :recorded="recorded.current.value" @select="setDate" />
    <div class="diary-columns">
      <section aria-labelledby="entries-heading">
        <div class="section-heading"><h2 id="entries-heading">{{ selected === today ? '今天的记录' : '当天的记录' }}</h2><button class="text-action" @click="add()"><Plus /> 记一笔</button></div>
        <p v-if="pending" class="caption" role="status">正在读取手账…</p>
        <div v-else-if="error" class="paper-panel empty-state"><p>{{ error }}</p><button class="button" @click="query.reload()">重新读取</button></div>
        <div v-else-if="!results?.total" class="paper-panel empty-state">
          <BookOpen /><h3>这一页还留白</h3><p>想记住今天的哪一种味道？</p><button class="button button-primary" @click="add()"><Plus /> 写下第一餐</button>
        </div>
        <div v-else>
          <section v-for="group in groups" :key="group.kind" class="meal-row" :aria-label="mealLabels[group.kind].label">
            <div class="meal-label"><span :class="group.kind"><component :is="kinds[group.kind]" /></span><h3>{{ mealLabels[group.kind].label }}</h3></div>
            <div>
              <button v-for="entry in group.meals" :key="entry.id" class="entry" :aria-label="'查看记录 ' + entry.items.map(item => item.food_name).join('、')" @click="focused = entry.id">
                <div class="entry-copy"><time>{{ entry.local_time.slice(0, 5) }}</time><strong>{{ entry.items.map(item => item.food_name).join('、') }}</strong><p v-if="entry.note">{{ entry.note }}</p></div>
                <div v-if="entry.media.length" class="entry-photos">
                  <PrivatePhoto v-for="image in entry.media.slice(0, 3)" :key="image.id" class="polaroid" :id="image.id" alt="" />
                </div>
              </button>
              <button v-if="!group.meals.length" class="text-action" @click="add(group.kind)"><Plus /> 记一笔{{ mealLabels[group.kind].label }}</button>
            </div>
          </section>
          <div v-if="results.total > results.limit" class="toolbar page-buttons">
            <button class="button" :disabled="results.page === 1" @click="paginate(results.page - 1)">上一页</button>
            <span>{{ results.page }} / {{ Math.ceil(results.total / results.limit) }}</span>
            <button class="button" :disabled="results.page * results.limit >= results.total" @click="paginate(results.page + 1)">下一页</button>
          </div>
        </div>
      </section>
      <aside v-if="daily" class="paper-panel panel-pad summary">
        <h2><Leaf /> {{ selected === today ? '今日小结' : '当日小结' }}</h2>
        <p>{{ daily.meals }} 笔记录 · {{ daily.items }} 样美食</p>
        <details v-if="visibleNutrients.length && daily.items">
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
      </aside>
    </div>
    <ModalSurface :open="!!focused" title="饮食详情" @close="close">
      <p v-if="detailLoading" class="caption" role="status">正在读取详情…</p>
      <p v-if="loadError" class="form-error" role="alert">{{ loadError }}</p>
      <template v-if="meal">
        <p class="caption">{{ meal.local_date }} · {{ mealLabels[meal.meal_type].label }} · {{ meal.local_time.slice(0, 5) }}</p>
        <div v-if="meal.media.length" class="detail-photos"><PrivatePhoto v-for="image in meal.media" :key="image.id" :id="image.id" original /></div>
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
.diary-cover { min-height: 10.8rem; padding: clamp(1rem, 4vw, 2rem); margin-bottom: 1rem; display: flex; justify-content: space-between; align-items: end; gap: .75rem; background: var(--color-paper-warm); background-image: var(--paper-texture); }
.cover-label { display: flex; align-items: center; gap: .35rem; color: var(--color-sage-deep); }
.cover-label svg { width: 1rem; height: 1rem; }
h1 { font: 700 clamp(2.15rem, 7vw, 4.5rem)/1.2 var(--font-serif); letter-spacing: -.06em; }
.diary-cover time { font-weight: 650; }
.diary-cover a { flex-shrink: 0; }
.diary-columns { display: grid; grid-template-columns: minmax(0, 1fr) minmax(12rem, 26%); align-items: start; gap: 1.4rem; margin-top: 1.2rem; }
.section-heading { display: flex; align-items: center; justify-content: space-between; gap: .6rem; }
h2 { font: 700 1.35rem var(--font-serif); }
.meal-row { display: grid; grid-template-columns: 4.2rem minmax(0, 1fr); gap: .8rem; padding: .75rem 0; border-top: 1px solid var(--color-line); }
.meal-label span { display: grid; place-items: center; width: 2.3rem; height: 2.3rem; border-radius: var(--radius-round); color: var(--color-earth); background: var(--color-butter); margin-bottom: .35rem; }
.meal-label svg, .summary svg { width: 1.05rem; height: 1.05rem; stroke-width: 1.6; }
.meal-label .lunch { background: var(--color-peach-soft); }
.meal-label .dinner { background: var(--color-leaf); color: var(--color-sage-deep); }
.meal-label .snack { background: var(--color-rose-soft); }
.meal-label h3 { font-size: .9rem; font-weight: 700; }
.entry { width: 100%; display: grid; grid-template-columns: minmax(0, .9fr) minmax(0, 1.1fr); align-items: center; gap: .6rem; border-radius: var(--radius-small); text-align: left; padding: .45rem; }
.entry:hover { background: var(--color-sheet-glaze); }
.entry + .entry { border-top: 1px dashed var(--color-line); }
.entry-copy { display: grid; gap: .35rem; overflow-wrap: anywhere; }
.entry-copy time { color: var(--color-sage-deep); font: 700 1.03rem var(--font-editorial); }
.entry-copy p { padding-left: .5rem; border-left: 2px solid var(--color-line-warm); color: var(--color-muted); font-size: .87rem; }
.entry-photos { display: flex; gap: .45rem; justify-content: center; }
.polaroid { width: min(100%, 8rem); height: auto; border: 4px solid var(--color-sheet); box-shadow: var(--shadow-paper); transform: rotate(-4deg); }
.polaroid:nth-child(even) { transform: rotate(5deg); }
.summary { background: var(--color-leaf-selected); }
.summary h2 { display: flex; align-items: center; gap: .4rem; font-size: 1.12rem; }
.summary p { margin-block: .6rem; }
.summary details { border-top: 1px solid var(--color-line-leaf); padding-top: .55rem; }
.summary dl { display: grid; gap: .5rem; margin: .6rem 0 0; }
.summary dl div { display: flex; flex-wrap: wrap; gap: .4rem; justify-content: space-between; font-size: .82rem; }
.summary dd { margin: 0; }
.page-buttons { justify-content: center; margin-top: .6rem; }
.detail-photos { display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: .5rem; }
.detail-item { border-top: 1px solid var(--color-line); padding-top: .55rem; overflow-wrap: anywhere; }
.detail-item details { margin-top: .25rem; }
@media (max-width: 700px) {
  .diary-cover { min-height: 8.5rem; }
  .diary-columns, .entry { grid-template-columns: minmax(0, 1fr); }
  .meal-row { grid-template-columns: 3.15rem minmax(0, 1fr); gap: .55rem; }
  .entry-photos { justify-content: start; }
}
</style>
