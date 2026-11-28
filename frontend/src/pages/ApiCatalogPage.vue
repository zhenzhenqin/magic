<script setup lang="ts">
import { BookOpen, ChevronLeft, ChevronRight, Heart, Search, Utensils } from 'lucide-vue-next'
import { computed, reactive, ref, watch } from 'vue'
import { useCatalogApi } from '../api/catalogRepository'
import type { CatalogQuery, FoodEntry } from '../api/catalogRepository'
import ModalSurface from '../components/ModalSurface.vue'
import PrivatePhoto from '../components/PrivatePhoto.vue'
import { usePrivateQuery } from '../composables/usePrivateQuery'
import { authMessage } from '../stores/auth'
import { mealLabels } from '../utils/labels'

const api = useCatalogApi()
const filter = reactive<CatalogQuery>({ search: '', category: '', favorites: false, sort: 'recent', page: 1 })
const query = usePrivateQuery(() => ({ ...filter }), api.list)
const { current: catalog, pending, error } = query
const categories = ref<string[]>([])
watch(catalog, result => { if (result) categories.value = result.categories })
watch(() => [filter.search, filter.category, filter.favorites, filter.sort], () => { filter.page = 1 })
const selected = ref('')
const historyPage = ref(1)
const detailQuery = usePrivateQuery(() => selected.value, (id, signal) => id ? api.entry(id, signal) : Promise.resolve(undefined))
const historyQuery = usePrivateQuery(() => [selected.value, historyPage.value] as const, ([id, page], signal) =>
  id ? api.history(id, page, signal) : Promise.resolve(undefined))
const { current: entry } = detailQuery
const { current: history } = historyQuery
const editing = ref(false)
const merging = ref(false)
const mergeSearch = ref('')
const target = ref('')
const mergeQuery = usePrivateQuery(() => merging.value ? mergeSearch.value : undefined, (search, signal) => search === undefined
  ? Promise.resolve(undefined) : api.list({ search, category: '', favorites: false, sort: 'recent', page: 1, limit: 12 }, signal))
const mergeResults = computed(() => mergeQuery.current.value?.items.filter(value => value.id !== selected.value) ?? [])
const form = reactive({ display_name: '', category: '' })
const busy = ref(false)
const message = ref('')
const operationError = ref('')

function open(id: string) {
  selected.value = id
  historyPage.value = 1
  editing.value = merging.value = false
  operationError.value = message.value = ''
}
function close() {
  if (!busy.value) open('')
}
function startEdit(item: FoodEntry) {
  form.display_name = item.display_name
  form.category = item.category ?? ''
  editing.value = true
}
async function perform(work: () => Promise<FoodEntry>, confirmation: string) {
  if (busy.value) return
  busy.value = true
  operationError.value = ''
  message.value = ''
  try {
    const result = await work()
    if (selected.value && result.id !== selected.value) open(result.id)
    detailQuery.reload()
    historyQuery.reload()
    query.reload()
    message.value = confirmation
  } catch (failure) {
    operationError.value = authMessage(failure)
  } finally {
    busy.value = false
  }
}
function favorite(item: FoodEntry) {
  void perform(() => api.patch(item.id, { is_favorite: !item.is_favorite }), item.is_favorite ? '已取消收藏。' : '已收藏。')
}
async function save() {
  await perform(() => api.patch(selected.value, { display_name: form.display_name, category: form.category || null }), '图鉴已更新。')
  if (!operationError.value) editing.value = false
}
function chooseCover(id: string) {
  void perform(() => api.patch(selected.value, { cover_media_id: id }), '已更换代表照片。')
}
function startMerge() {
  mergeSearch.value = target.value = ''
  merging.value = true
}
function combine() {
  if (target.value) void perform(() => api.merge(selected.value, target.value), '已合并，原用餐记录保留。')
}
</script>

<template>
  <div class="catalog">
    <header class="catalog-header">
      <div><h1>美食图鉴</h1><p v-if="catalog">收录 {{ catalog.collected }} 种美食</p></div>
      <BookOpen aria-hidden="true" />
    </header>
    <form class="catalog-filters" role="search" @submit.prevent>
      <label class="search-box"><Search aria-hidden="true" /><input v-model.trim="filter.search" maxlength="80" placeholder="搜索食物名称" aria-label="搜索食物名称" /></label>
      <label><span class="sr-only">分类</span><select v-model="filter.category"><option value="">全部分类</option><option v-for="category in categories" :key="category">{{ category }}</option></select></label>
      <label><span class="sr-only">排序</span><select v-model="filter.sort"><option value="recent">最近收集</option><option value="occasions">食用次数</option></select></label>
      <button type="button" class="button" :aria-pressed="filter.favorites" @click="filter.favorites = !filter.favorites">
        <Heart aria-hidden="true" :class="{ filled: filter.favorites }" /> 收藏
      </button>
    </form>
    <section class="catalog-paper" aria-label="美食收藏册">
      <p v-if="pending" class="caption" role="status">正在翻阅收藏册…</p>
      <div v-else-if="error" class="empty-state"><p>{{ error }}</p><button class="button" @click="query.reload()">重新读取</button></div>
      <div v-else-if="!catalog?.items.length" class="empty-state">
        <BookOpen aria-hidden="true" />
        <h2>{{ filter.search || filter.category || filter.favorites ? '没有符合条件的美食' : '收藏册还留着空白' }}</h2>
        <RouterLink v-if="!filter.search && !filter.category && !filter.favorites" class="button button-primary" to="/capture">记下第一餐</RouterLink>
      </div>
      <div v-else class="catalog-grid">
        <article v-for="item in catalog.items" :key="item.id" class="catalog-scrap">
          <button class="catalog-item" @click="open(item.id)">
            <span class="cover"><PrivatePhoto v-if="item.cover_media_id" :id="item.cover_media_id" :presentation="item.cover_use_original ? undefined : 'thumbnail'" alt="" /><Utensils v-else aria-hidden="true" /></span>
            <strong>{{ item.display_name }}</strong>
            <small v-if="item.occasions">{{ item.occasions }} 次用餐<span v-if="item.cover_whole_meal"> · 整餐图</span></small>
            <small v-else>已无有效记录</small>
          </button>
          <button type="button" class="icon-button favorite" :disabled="busy" :aria-label="(item.is_favorite ? '取消收藏 ' : '收藏 ') + item.display_name"
            :aria-pressed="item.is_favorite" @click="favorite(item)"><Heart aria-hidden="true" :class="{ filled: item.is_favorite }" /></button>
        </article>
      </div>
      <p v-if="!selected && operationError" class="form-error" role="alert">{{ operationError }}</p>
      <div v-if="catalog && catalog.total > catalog.limit" class="toolbar pagination">
        <button class="icon-button" aria-label="上一页图鉴" :disabled="filter.page === 1" @click="filter.page--"><ChevronLeft /></button>
        <span>{{ filter.page }} / {{ Math.ceil(catalog.total / catalog.limit) }}</span>
        <button class="icon-button" aria-label="下一页图鉴" :disabled="filter.page * catalog.limit >= catalog.total" @click="filter.page++"><ChevronRight /></button>
      </div>
    </section>
    <ModalSurface :open="!!selected" :title="entry?.display_name ?? '食物详情'" @close="close">
      <p v-if="detailQuery.error.value" class="form-error" role="alert">{{ detailQuery.error.value }}</p>
      <p v-else-if="!entry" class="caption" role="status">正在读取详情…</p>
      <template v-else>
        <div v-if="entry.cover_media_id" class="detail-cover">
          <PrivatePhoto :id="entry.cover_media_id" :presentation="entry.cover_use_original ? undefined : 'sticker'" :alt="entry.display_name + ' 代表照片'" />
        </div>
        <p v-if="entry.cover_whole_meal" class="caption">代表图为所在整餐。</p>
        <p class="caption">{{ entry.category || '未分类' }} · {{ entry.occasions }} 次用餐 · {{ entry.details }} 条食物明细</p>
        <p class="caption" v-if="entry.occasions">首次 {{ entry.first_eaten }} · 最近 {{ entry.last_eaten }}</p>
        <p class="caption" v-else>已无有效用餐记录。</p>
        <p v-if="operationError" class="form-error" role="alert">{{ operationError }}</p>
        <p v-if="message" class="caption" role="status">{{ message }}</p>
        <div v-if="!editing && !merging" class="toolbar">
          <button type="button" class="button" :disabled="busy" @click="favorite(entry)">{{ entry.is_favorite ? '取消收藏' : '收藏' }}</button>
          <button type="button" class="button" @click="startEdit(entry)">编辑图鉴</button>
          <button type="button" class="button" @click="startMerge">合并到另一项</button>
        </div>
        <form v-if="editing" class="form-stack" @submit.prevent="save">
          <label class="field">显示名称<input v-model.trim="form.display_name" maxlength="80" required /></label>
          <label class="field">分类<input v-model.trim="form.category" maxlength="40" /></label>
          <div class="toolbar"><button class="button button-primary" :disabled="busy">保存图鉴</button><button type="button" class="button" @click="editing = false">取消</button></div>
        </form>
        <form v-if="merging" class="form-stack" @submit.prevent="combine">
          <label class="field">查找合并目标<input v-model.trim="mergeSearch" maxlength="80" /></label>
          <label class="field">合并到<select v-model="target" aria-label="合并到"><option value="" disabled>选择图鉴条目</option><option v-for="item in mergeResults" :key="item.id" :value="item.id">{{ item.display_name }}</option></select></label>
          <p class="caption">历史记录会汇入所选条目，每餐仍保留原来的食物名称。</p>
          <div class="toolbar"><button class="button button-primary" :disabled="!target || busy">确认合并</button><button type="button" class="button" @click="merging = false">取消</button></div>
        </form>
        <section class="catalog-history" aria-label="饮食历史">
          <h3>饮食历史</h3>
          <p v-if="historyQuery.error.value" class="form-error">{{ historyQuery.error.value }}</p>
          <ul v-if="history">
            <li v-for="item in history.items" :key="item.meal_id">
              <RouterLink class="text-action" :to="{ name: 'diary', query: { date: item.local_date, meal: item.meal_id } }">{{ item.local_date }} · {{ mealLabels[item.meal_type].label }}</RouterLink>
              <span v-if="editing" class="cover-options">
                <button v-for="(id, index) in item.media_ids" :key="id" type="button" class="button" :disabled="busy" @click="chooseCover(id)">封面照片 {{ index + 1 }}</button>
              </span>
            </li>
          </ul>
          <div v-if="history && history.total > history.limit" class="toolbar pagination">
            <button class="button" :disabled="historyPage === 1" @click="historyPage--">前一页历史</button>
            <button class="button" :disabled="historyPage * history.limit >= history.total" @click="historyPage++">后一页历史</button>
          </div>
        </section>
      </template>
    </ModalSurface>
  </div>
</template>

<style scoped>
.catalog { max-width: 57rem; margin: auto; }
.catalog-header { display: flex; justify-content: space-between; align-items: center; margin: .4rem 0 .85rem; }
.catalog-header h1 { font: 700 clamp(1.7rem, 5vw, 2.85rem)/1.12 var(--font-serif); }
.catalog-header p { margin-top: .35rem; font: 600 1rem var(--font-hand); color: var(--diary-ink-soft); }
.catalog-header svg { width: 1.6rem; stroke-width: 1.4; color: var(--diary-ink-soft); }
.catalog-filters { display: flex; flex-wrap: wrap; gap: .4rem; align-items: center; margin-bottom: .8rem; }
.search-box { display: flex; align-items: center; min-width: 12rem; gap: .4rem; flex: 1; }
.search-box svg { width: 1rem; flex: none; }
.search-box input { width: 100%; border: 1px solid var(--color-control-line); border-radius: .45rem; min-height: 2.5rem; padding: .4rem .55rem; background: var(--color-sheet); }
.catalog-filters select { max-width: min(36vw, 12rem); }
.catalog-paper { min-height: 23rem; padding: clamp(.55rem, 3vw, 1.45rem); border: 1px solid var(--color-line); border-radius: .55rem 1.7rem 1.7rem .55rem; background-color: var(--color-sheet); background-image: var(--paper-texture); box-shadow: var(--shadow-paper); }
.catalog-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: .75rem .85rem; }
.catalog-scrap { position: relative; min-width: 0; text-align: center; padding-top: .6rem; }
.catalog-scrap:nth-child(even) { margin-top: .45rem; }
.catalog-item { display: grid; gap: .16rem; place-items: center; text-align: center; padding: .3rem .35rem .65rem; width: 100%; border-radius: .55rem; }
.catalog-item:hover { background: #efeae44d; }
.cover { display: grid; place-items: center; width: min(100%, 12.5rem); height: clamp(4.9rem, 24vw, 9.5rem); color: #aaa097; margin-bottom: .35rem; }
.catalog-scrap:nth-child(4n) .cover { width: 90%; }
.catalog-item strong { font: 600 clamp(1rem, 4.2vw, 1.48rem)/1.2 var(--font-hand); color: var(--diary-ink-soft); overflow-wrap: anywhere; }
.catalog-item small { color: var(--color-muted); font-size: .75rem; }
.favorite { position: absolute; top: 0; right: 0; box-shadow: none; background: transparent; border-color: transparent; }
.favorite:hover { background: var(--color-leaf-pale); }
.favorite svg { width: 1rem; stroke-width: 1.6; }
.filled { fill: #80675a; color: #80675a; }
.detail-cover { height: clamp(7rem, 37vw, 13rem); }
.catalog-history { border-top: 1px solid var(--color-line); padding-top: .5rem; }
.catalog-history ul { padding: 0; list-style: none; }
.catalog-history li { display: flex; flex-wrap: wrap; align-items: center; gap: .35rem; border-bottom: 1px solid var(--color-line); }
.cover-options { display: flex; gap: .2rem; flex-wrap: wrap; }
.pagination { justify-content: center; }
@media (max-width: 620px) {
  .catalog-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .47rem .65rem; }
  .search-box { flex-basis: 100%; }
  .cover { height: clamp(4.5rem, 21vw, 7.2rem); }
}
</style>
