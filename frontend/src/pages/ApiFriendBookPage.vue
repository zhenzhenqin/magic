<script setup lang="ts">
import { ArrowLeft, BookLock, ChevronLeft, ChevronRight, RotateCw } from 'lucide-vue-next'
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { nutrientFields, useDiaryApi } from '../api/diaryRepository'
import { useSharingApi } from '../api/sharingRepository'
import type { MediaKind } from '../api/sharingRepository'
import DateStrip from '../components/DateStrip.vue'
import ModalSurface from '../components/ModalSurface.vue'
import PrivatePhoto from '../components/PrivatePhoto.vue'
import SharedMealScrap from '../components/SharedMealScrap.vue'
import SharedPhoto from '../components/SharedPhoto.vue'
import { useApiDay } from '../composables/useApiDay'
import { usePrivateQuery } from '../composables/usePrivateQuery'
import { useSharingRefresh } from '../composables/useSharingRefresh'
import { useAuth } from '../stores/auth'
import { mealKinds } from '../types/domain'
import { dayLabel, monthLabel, monthStart, shiftDay, weekdays, weekFor } from '../utils/dates'
import { mealLabels } from '../utils/labels'

const route = useRoute()
const auth = useAuth()
const api = useSharingApi()
const ownApi = useDiaryApi()
const { selected, today, setDate } = useApiDay()
const mode = computed(() => String(route.name))
const id = computed(() => String(route.params.friendId ?? ''))
const currentMonth = ref(monthStart(selected.value))
const page = ref(1)
const ownPage = ref(1)
const search = ref('')
const searchDraft = ref('')
const category = ref('')
const selectedMeal = ref('')
const selectedFood = ref('')
const historyPage = ref(1)
const photoKinds = ref<Record<string, MediaKind>>({})
const state = useSharingRefresh(() => { relationship.reload(); ownMeals.reload() })
const available = computed(() => state.online.value && state.foreground.value)

const relationship = usePrivateQuery(() => (available.value ? id.value : ''), (key, signal) =>
  key ? api.sharing(key, signal) : Promise.resolve(undefined),
)
const { current: friend } = relationship
const grant = computed(() => friend.value?.incoming)
const records = computed(() => grant.value?.permissions.records)
const outside = computed(() => Boolean(grant.value?.history_start && selected.value < grant.value.history_start))
const dateMode = computed(() => mode.value === 'friend-diary' || mode.value === 'friend-together')
const weekMonth = computed(() => monthStart(weekFor(selected.value)[0]))
const weekEndMonth = computed(() => monthStart(weekFor(selected.value)[6]))
const meals = usePrivateQuery(
  () => records.value && dateMode.value && !outside.value ? { id: id.value, date: selected.value, page: page.value } : null,
  (key, signal) => key ? api.meals(key.id, key.date, key.page, signal) : Promise.resolve(undefined),
)
const ownMeals = usePrivateQuery(
  () => mode.value === 'friend-together' && available.value ? { date: selected.value, page: ownPage.value } : null,
  (key, signal) => key ? ownApi.meals(key.date, key.page, signal) : Promise.resolve(undefined),
)
const daily = usePrivateQuery(
  () => mode.value === 'friend-diary' && records.value && !outside.value &&
    (grant.value?.permissions.calories || grant.value?.permissions.nutrition) ? { id: id.value, date: selected.value } : null,
  (key, signal) => key ? api.daily(key.id, key.date, signal) : Promise.resolve(undefined),
)
const calendar = usePrivateQuery(
  () => records.value && mode.value !== 'friend-catalog' ? {
    owner: id.value,
    months: mode.value === 'friend-calendar' ? [currentMonth.value]
      : Array.from(new Set([weekMonth.value, weekEndMonth.value])),
  } : null,
  (key, signal) => key ? Promise.all(key.months.map(month => api.calendar(key.owner, month.slice(0, 7), signal))) : Promise.resolve(undefined),
)
const foods = usePrivateQuery(
  () => mode.value === 'friend-catalog' && grant.value?.permissions.catalog
    ? { id: id.value, page: page.value, search: search.value, category: category.value } : null,
  (key, signal) => key ? api.catalog(key.id, key.page, key.search, key.category, signal) : Promise.resolve(undefined),
)
const meal = usePrivateQuery(
  () => records.value && selectedMeal.value ? { id: id.value, meal: selectedMeal.value } : null,
  (key, signal) => key ? api.meal(key.id, key.meal, signal) : Promise.resolve(undefined),
)
const food = usePrivateQuery(
  () => grant.value?.permissions.catalog && grant.value.permissions.names && selectedFood.value
    ? { id: id.value, food: selectedFood.value } : null,
  (key, signal) => key ? api.food(key.id, key.food, signal) : Promise.resolve(undefined),
)
const history = usePrivateQuery(
  () => grant.value?.permissions.history && food.current.value
    ? { id: id.value, food: food.current.value.id, page: historyPage.value } : null,
  (key, signal) => key ? api.history(key.id, key.food, key.page, signal) : Promise.resolve(undefined),
)
const markedDays = computed(() => calendar.current.value?.flatMap(month => month.days.map(day => day.date)) ?? [])
const calendarByDate = computed(() => new Map(calendar.current.value?.flatMap(month => month.days.map(day => [day.date, day] as const))))
const calendarDates = computed(() => {
  const first = currentMonth.value
  const next = monthStart(first, 1)
  const padding = weekFor(first).indexOf(first)
  const days = []
  for (let day = first; day < next; day = shiftDay(day, 1)) days.push(day)
  return [...Array<string | null>(padding).fill(null), ...days]
})
const title = computed(() => ({
  'friend-diary': '好友手账', 'friend-calendar': '好友月历', 'friend-catalog': '好友图鉴', 'friend-together': '双人手账',
})[mode.value] ?? '好友手账')
const tabs = [
  { name: 'friend-diary', label: '手账' }, { name: 'friend-calendar', label: '月历' },
  { name: 'friend-catalog', label: '图鉴' }, { name: 'friend-together', label: '双人手账' },
]
const values = { ...nutrientFields, weight_g: { label: '重量', unit: 'g' } }
const nutrientKeys = Object.keys(values) as (keyof typeof values)[]
const failure = computed(() => meals.error.value || ownMeals.error.value || calendar.error.value || daily.error.value || foods.error.value)
const query = computed(() => ({ date: selected.value }))
const readPage = computed(() => mode.value === 'friend-catalog' ? foods.current.value : meals.current.value)
const detailTitle = computed(() => selectedMeal.value ? '饮食详情' : food.current.value?.name ?? '图鉴详情')
const unavailableFields = computed(() => {
  const flags = grant.value?.permissions
  if (!flags?.records) return []
  return [
    !flags.photos && !flags.stickers ? '图片' : '',
    !flags.calories && !flags.nutrition ? '营养数据' : '',
    !flags.names ? '食物名称' : '',
  ].filter(Boolean)
})

function closeDetail() {
  selectedMeal.value = selectedFood.value = ''
  photoKinds.value = {}
  historyPage.value = 1
}
function openMeal(mealId: string) {
  closeDetail()
  selectedMeal.value = mealId
}
function openFood(foodId: string) {
  closeDetail()
  selectedFood.value = foodId
}
function labelValue(key: keyof typeof values, value: number | null) {
  return value === null ? '未知' : value + ' ' + values[key].unit
}
watch([mode, id], () => {
  currentMonth.value = monthStart(selected.value)
  search.value = searchDraft.value = category.value = ''
  page.value = ownPage.value = 1
  closeDetail()
})
watch(selected, () => { page.value = ownPage.value = 1; closeDetail() })
watch([search, category], () => { page.value = 1 })
watch(available, active => { if (!active) closeDetail() })
</script>

<template>
  <div class="friend-book">
    <header class="book-heading">
      <RouterLink class="text-action" :to="{ name: 'friends' }"><ArrowLeft aria-hidden="true" /> 返回饭搭子</RouterLink>
      <div class="heading-row">
        <div><h1>{{ title }}</h1><p v-if="friend" class="caption">{{ mode === 'friend-together' ? '我和 ' : '' }}{{ friend.person.nickname }}</p></div>
        <button type="button" class="icon-button button-quiet" aria-label="刷新共享内容" :disabled="!available" @click="state.refresh"><RotateCw aria-hidden="true" /></button>
      </div>
      <nav class="book-tabs" aria-label="好友手账导航">
        <RouterLink v-for="tab in tabs" :key="tab.name" :to="{ name: tab.name, params: { friendId: id }, query }"
          :aria-current="tab.name === mode ? 'page' : undefined">{{ tab.label }}</RouterLink>
      </nav>
    </header>
    <DateStrip v-if="dateMode" :selected="selected" :today="today" :recorded="markedDays" notebook @select="setDate" />
    <section class="book-paper" :aria-label="title">
      <p v-if="!state.online.value" class="quiet-state" role="status">网络已断开。连接后会重新读取共享内容。</p>
      <p v-else-if="relationship.error.value" class="quiet-state" role="status"><BookLock aria-hidden="true" /> 无法读取该好友的共享内容。</p>
      <p v-else-if="!friend" class="quiet-state" role="status">正在核对共享权限…</p>
      <template v-else>
        <p v-if="failure" class="form-error" role="alert">{{ failure }}</p>
        <template v-if="mode === 'friend-diary'">
          <h2>{{ dayLabel(selected) }}</h2>
          <p v-if="!records || outside" class="quiet-state"><BookLock aria-hidden="true" />{{ outside && records ? '这段日期暂未共享。' : '这本手账暂未共享。' }}</p>
          <template v-else>
            <p v-if="unavailableFields.length" class="caption">{{ unavailableFields.join('、') }}暂未共享</p>
            <dl v-if="daily.current.value?.nutrition && daily.current.value.meals" class="nutrient-list">
              <template v-for="key in nutrientKeys" :key="key">
                <div v-if="daily.current.value.nutrition[key]">
                  <dt>{{ values[key].label }}</dt><dd>{{ labelValue(key, daily.current.value.nutrition[key].value) }}
                    <small v-if="daily.current.value.nutrition[key].known_items && !daily.current.value.nutrition[key].complete">已知小计</small>
                    <small v-if="daily.current.value.nutrition[key].estimated">含照片估算或调整</small>
                  </dd>
                </div>
              </template>
            </dl>
            <p v-if="meals.current.value?.total === 0" class="quiet-state">这一天还没有饮食记录。</p>
            <div class="scraps"><SharedMealScrap v-for="entry in meals.current.value?.items" :key="entry.id" :meal="entry" :owner="id" @open="openMeal" /></div>
          </template>
        </template>
        <template v-else-if="mode === 'friend-calendar'">
          <p v-if="!records" class="quiet-state"><BookLock aria-hidden="true" /> 这本月历暂未共享。</p>
          <template v-else>
            <div class="month-controls">
              <button type="button" class="icon-button button-quiet" aria-label="上个月" @click="currentMonth = monthStart(currentMonth, -1)"><ChevronLeft /></button>
              <h2>{{ monthLabel(currentMonth) }}</h2>
              <button type="button" class="icon-button button-quiet" aria-label="下个月" @click="currentMonth = monthStart(currentMonth, 1)"><ChevronRight /></button>
            </div>
            <div class="month-grid">
              <span v-for="day in weekdays" :key="day" class="caption">{{ day }}</span>
              <template v-for="(date, index) in calendarDates" :key="date || index">
                <span v-if="!date" aria-hidden="true"></span>
                <span v-else-if="grant?.history_start && date < grant.history_start" class="month-day withheld" :aria-label="date + ' 暂未共享'">{{ Number(date.slice(-2)) }}</span>
                <RouterLink v-else class="month-day" :to="{ name: 'friend-diary', params: { friendId: id }, query: { date } }" :aria-label="date">
                  <span>{{ Number(date.slice(-2)) }}</span>
                  <SharedPhoto v-if="calendarByDate.get(date)?.media && calendarByDate.get(date)?.meal_id"
                    :owner="id" :media="calendarByDate.get(date)!.media!" :context="{ meal_id: calendarByDate.get(date)!.meal_id! }" />
                  <small v-else-if="calendarByDate.has(date)" class="calendar-dot" aria-label="有饮食记录">●</small>
                </RouterLink>
              </template>
            </div>
          </template>
        </template>
        <template v-else-if="mode === 'friend-catalog'">
          <p v-if="!grant?.permissions.catalog || !grant.permissions.names" class="quiet-state"><BookLock aria-hidden="true" />{{ grant?.permissions.catalog ? '食物名称暂未共享。' : '这本图鉴暂未共享。' }}</p>
          <template v-else>
            <form class="catalog-filter" @submit.prevent="search = searchDraft.trim()">
              <input v-model="searchDraft" maxlength="80" aria-label="查找共享食物" placeholder="查找共享食物" />
              <button class="button" type="submit">查找</button>
              <select v-model="category" aria-label="共享食物分类"><option value="">全部分类</option><option v-for="item in foods.current.value?.categories" :key="item">{{ item }}</option></select>
            </form>
            <p v-if="foods.current.value?.total === 0" class="quiet-state">这里暂时没有符合条件的食物。</p>
            <div class="scraps gallery">
              <button v-for="entry in foods.current.value?.items" :key="entry.id" type="button" class="food-entry" @click="openFood(entry.id)">
                <div v-if="entry.cover" class="food-cover"><SharedPhoto :owner="id" :media="entry.cover" :context="{ catalog_id: entry.id }" /></div>
                <strong>{{ entry.name }}</strong><span v-if="entry.category" class="caption">{{ entry.category }}</span>
                <small v-if="entry.cover_whole_meal" class="caption">整餐照片</small>
              </button>
            </div>
          </template>
        </template>
        <template v-else>
          <h2>{{ dayLabel(selected) }}</h2>
          <div v-for="kind in mealKinds" :key="kind" class="paired-meal">
            <h3>{{ mealLabels[kind].label }}</h3>
            <div class="paired-pages">
              <section aria-label="我的记录">
                <h4>{{ auth.currentUser?.nickname ?? '我' }} <small>我</small></h4>
                <template v-for="entry in ownMeals.current.value?.items.filter(entry => entry.meal_type === kind)" :key="entry.id">
                  <div v-if="entry.media.length" class="own-photos"><PrivatePhoto v-for="media in entry.media" :key="media.id" :id="media.id" presentation="thumbnail" /></div>
                  <p class="own-caption">{{ entry.items.map(item => item.food_name).join('、') }}</p>
                  <p class="caption">{{ entry.local_time.slice(0, 5) }}</p>
                  <p v-if="auth.preferences?.show_calories && entry.items.some(item => item.calories_kcal !== null)" class="caption">
                    {{ entry.items.map(item => item.calories_kcal).filter((value): value is number => value !== null).join(' / ') }} kcal
                    <span v-if="entry.items.some(item => item.source !== 'manual')"> · 含照片估算或调整</span>
                  </p>
                </template>
                <p v-if="ownMeals.current.value && !ownMeals.current.value.items.some(entry => entry.meal_type === kind)" class="caption">{{ ownMeals.current.value.total > ownMeals.current.value.limit ? '当前页没有这一餐的记录。' : '这一餐还没有记录。' }}</p>
              </section>
              <section :aria-label="friend.person.nickname + '的记录'">
                <h4>{{ friend.person.nickname }}</h4>
                <p v-if="!records || outside" class="caption">该内容暂未共享。</p>
                <template v-else-if="meals.current.value">
                  <SharedMealScrap v-for="entry in meals.current.value.items.filter(entry => entry.meal_type === kind)"
                    :key="entry.id" :meal="entry" :owner="id" @open="openMeal" />
                  <p v-if="!meals.current.value.items.some(entry => entry.meal_type === kind)" class="caption">{{ meals.current.value.total > meals.current.value.limit ? '当前页没有这一餐的记录。' : '这一餐还没有记录。' }}</p>
                </template>
              </section>
            </div>
          </div>
          <div v-if="ownMeals.current.value && ownMeals.current.value.total > ownMeals.current.value.limit" class="pager toolbar">
            <button class="button" :disabled="ownPage === 1" @click="ownPage--">我的上一页</button>
            <button class="button" :disabled="ownPage * ownMeals.current.value.limit >= ownMeals.current.value.total" @click="ownPage++">我的下一页</button>
          </div>
        </template>
        <div v-if="readPage?.total && readPage.total > readPage.limit" class="pager toolbar">
          <button class="button" :disabled="page === 1" @click="page--">上一页</button>
          <span class="caption">第 {{ page }} 页</span>
          <button class="button" :disabled="page * readPage.limit >= readPage.total" @click="page++">下一页</button>
        </div>
      </template>
    </section>
    <ModalSurface :open="Boolean((selectedMeal || selectedFood) && friend)" :title="detailTitle" @close="closeDetail">
      <p v-if="meal.error.value || food.error.value || (!meal.pending.value && !food.pending.value && !meal.current.value && !food.current.value)" class="caption">该内容暂不可查看。</p>
      <template v-if="meal.current.value">
        <p class="caption">{{ meal.current.value.local_date }} · {{ mealLabels[meal.current.value.meal_type].label }} · {{ meal.current.value.local_time }}</p>
        <div v-for="media in meal.current.value.media" :key="media.id">
          <div v-if="media.kinds.length > 1" class="toolbar">
            <button v-for="kind in media.kinds" :key="kind" class="button" :aria-pressed="(photoKinds[media.id] ?? media.kinds[0]) === kind"
              @click="photoKinds[media.id] = kind">{{ kind === 'sticker' ? '贴纸' : '原始照片' }}</button>
          </div>
          <div class="detail-photo"><SharedPhoto :owner="id" :media="media" :context="{ meal_id: meal.current.value.id }" :kind="photoKinds[media.id]" full /></div>
        </div>
        <p v-if="meal.current.value.note">{{ meal.current.value.note }}</p>
        <article v-for="(item, index) in meal.current.value.items" :key="index" class="detail-item">
          <h3>{{ item.food_name ?? '食物 ' + (index + 1) }}</h3>
          <p v-if="item.category" class="caption">{{ item.category }}</p>
          <dl class="nutrient-list">
            <template v-for="key in nutrientKeys" :key="key">
              <div v-if="item[key] !== undefined"><dt>{{ values[key].label }}</dt><dd>{{ labelValue(key, item[key]) }} <small v-if="item[key] !== null && item.estimated">含照片估算或调整</small></dd></div>
            </template>
          </dl>
          <p v-if="item.note">{{ item.note }}</p>
        </article>
      </template>
      <template v-if="food.current.value">
        <div v-if="food.current.value.cover" class="detail-photo"><SharedPhoto :owner="id" :media="food.current.value.cover" :context="{ catalog_id: food.current.value.id }" full /></div>
        <p v-if="food.current.value.cover_whole_meal || food.current.value.category" class="caption">{{ [food.current.value.category, food.current.value.cover_whole_meal ? '整餐照片' : ''].filter(Boolean).join(' · ') }}</p>
        <p v-if="food.current.value.occurrences !== undefined" class="caption">
          授权范围内 {{ food.current.value.occurrences }} 餐 · {{ food.current.value.items }} 条明细<br />
          首次 {{ food.current.value.first_eaten }} · 最近 {{ food.current.value.last_eaten }}
        </p>
        <section v-if="history.current.value">
          <h3>共享历史</h3>
          <ul><li v-for="entry in history.current.value.items" :key="entry.id">
            <RouterLink v-if="records" class="text-action" :to="{ name: 'friend-diary', params: { friendId: id }, query: { date: entry.local_date } }" @click="closeDetail">{{ entry.local_date }} · {{ mealLabels[entry.meal_type].label }}</RouterLink>
            <span v-else>{{ entry.local_date }} · {{ mealLabels[entry.meal_type].label }}</span>
          </li></ul>
          <div v-if="history.current.value.total > history.current.value.limit" class="toolbar">
            <button class="button" :disabled="historyPage === 1" @click="historyPage--">上一页</button>
            <button class="button" :disabled="historyPage * history.current.value.limit >= history.current.value.total" @click="historyPage++">下一页</button>
          </div>
        </section>
      </template>
    </ModalSurface>
  </div>
</template>

<style scoped>
.friend-book { max-width: 61rem; margin: auto; }
.book-heading { margin-bottom: .7rem; }
.heading-row, .month-controls { display: flex; align-items: center; justify-content: space-between; gap: .7rem; }
.heading-row { margin: .55rem 0 .7rem; }
h1 { font: 700 clamp(1.7rem, 6vw, 2.9rem) var(--font-serif); }
h2 { font: 600 clamp(1.3rem, 5vw, 2rem) var(--font-hand); color: var(--diary-ink-soft); }
h3 { font: 600 1.2rem var(--font-hand); color: var(--diary-ink-soft); }
.book-tabs { display: flex; gap: clamp(.55rem, 3vw, 1.6rem); align-items: center; flex-wrap: wrap; }
.book-tabs a { font-size: .88rem; padding: .45rem .6rem; border-bottom: 2px solid transparent; }
.book-tabs a[aria-current] { border-color: var(--color-ink); font-weight: 650; }
.book-paper { position: relative; min-height: 16rem; padding: clamp(1rem, 4vw, 2.5rem) clamp(.75rem, 3vw, 2.3rem) 2rem clamp(1.4rem, 6vw, 3.5rem); border: 1px solid var(--color-line); border-radius: .75rem 1.65rem 1.65rem .75rem; background: var(--color-sheet) repeating-linear-gradient(0deg, #48352203 0 1px, transparent 1px 5px); box-shadow: var(--shadow-paper); }
.book-paper::before { content: ''; position: absolute; inset: .45rem auto .45rem clamp(.1rem, 2vw, .8rem); width: .62rem; background: radial-gradient(circle at center, #efebe8 0 2px, #e2ddd8 2.25px 2.75px, transparent 3px) center top / .62rem 1.65rem repeat-y; pointer-events: none; }
.quiet-state { color: var(--color-muted); display: flex; align-items: center; gap: .5rem; min-height: 7rem; }
.quiet-state svg { width: 1.15rem; }
.nutrient-list { display: flex; gap: .45rem .9rem; flex-wrap: wrap; margin: .5rem 0; }
.nutrient-list div { display: grid; gap: .1rem .3rem; }
.nutrient-list dt { color: var(--color-muted); font-size: .72rem; }
.nutrient-list dd { color: var(--diary-ink-soft); font-size: .9rem; }
.nutrient-list small { font-size: .65rem; }
.scraps { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); align-items: start; gap: clamp(.5rem, 3vw, 1.6rem); margin-top: .7rem; }
.scraps > :nth-child(even) { margin-top: 1.15rem; }
.gallery { grid-template-columns: repeat(auto-fit, minmax(min(8rem, 45%), 1fr)); }
.food-entry { display: grid; justify-items: center; gap: .18rem; min-width: 0; padding: .4rem; text-align: center; }
.food-entry strong, .own-caption { color: var(--diary-ink-soft); font: 600 1.1rem var(--font-hand); overflow-wrap: anywhere; }
.food-cover { width: 100%; height: 8rem; }
.catalog-filter { display: flex; flex-wrap: wrap; gap: .45rem; margin-bottom: .65rem; }
.catalog-filter input, .catalog-filter select { max-width: 100%; min-width: 0; border: 1px solid var(--color-line); border-radius: .65rem; padding: .35rem .55rem; background: var(--color-sheet); }
.month-grid { display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)); gap: .2rem; text-align: center; align-items: stretch; }
.month-day { display: grid; align-content: start; justify-items: center; min-height: 2.75rem; gap: .1rem; padding: .22rem; border-top: 1px solid var(--color-line); font-size: .83rem; }
.month-day > :deep(.shared-photo) { height: clamp(1.35rem, 6vw, 4rem); }
.month-day:hover:not(.withheld) { background: var(--color-canvas-hover); }
.withheld { color: #8d8580; }
.calendar-dot { color: var(--color-earth); }
.paired-meal { margin-top: .85rem; padding: .55rem 0; border-block-start: 1px solid var(--color-line); }
.paired-pages { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1rem; margin-top: .5rem; }
.paired-pages section { text-align: center; min-width: 0; overflow-wrap: anywhere; }
.paired-pages section + section { border-left: 1px dashed var(--color-line); padding-left: .55rem; }
.paired-pages h4 { font-size: .9rem; margin-bottom: .45rem; }
.paired-pages h4 small { color: var(--color-muted); margin-left: .25rem; }
.own-photos { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(5.5rem, 100%), 1fr)); height: clamp(5.2rem, 23vw, 10rem); }
.own-photos + .own-caption { margin-top: .15rem; }
.pager { margin-top: 1rem; justify-content: center; }
.detail-photo { height: clamp(8rem, 45vw, 17rem); }
.detail-item { border-top: 1px solid var(--color-line); padding-top: .5rem; }
@media (max-width: 365px) { .paired-pages { grid-template-columns: 1fr; } .paired-pages section + section { border-left: 0; padding-left: 0; } }
</style>
