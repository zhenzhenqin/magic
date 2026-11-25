<script setup lang="ts">
import { BookOpen, Heart, Search, Shell } from 'lucide-vue-next'
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import FoodSticker from '../components/FoodSticker.vue'
import ModalSurface from '../components/ModalSurface.vue'
import PageHeading from '../components/PageHeading.vue'
import { categories } from '../mocks/seed'
import { useDiary } from '../stores/diary'
import type { FoodCategory } from '../types/domain'

const route = useRoute()
const diary = useDiary()
const readonly = computed(() => route.name === 'friend-catalog')
const ownerId = computed(() => readonly.value ? String(route.params.id) : diary.account.id)
const owner = computed(() => diary.person(ownerId.value))
const canView = computed(() => diary.permissions(ownerId.value).catalog)
const selection = ref<FoodCategory | '全部'>('全部')
const search = ref('')
const favorites = ref(false)
const itemId = ref('')
watch([ownerId, () => route.query.favorites], () => {
  selection.value = '全部'
  search.value = ''
  favorites.value = !readonly.value && route.query.favorites === '1'
  itemId.value = ''
}, { immediate: true })
const foods = computed(() => diary.catalog(ownerId.value))
const filtered = computed(() => foods.value.filter(food =>
  (selection.value === '全部' || food.category === selection.value) &&
  (!favorites.value || food.favorite) && food.name.toLowerCase().includes(search.value.trim().toLowerCase())))
const selected = computed(() => foods.value.find(food => food.id === itemId.value))
</script>

<template>
  <div class="catalog-page">
    <RouterLink v-if="readonly" to="/friends" class="text-action">返回饭搭子</RouterLink>
    <PageHeading :title="readonly ? (owner?.nickname ?? '好友') + '的图鉴' : '美食图鉴'"
      :subtitle="readonly ? '好友授权共享 · 只读' : '记录过的味道，慢慢收集。'">
      <span v-if="canView" class="badge"><BookOpen :size="15" /> {{ foods.length }} 样美食</span>
    </PageHeading>
    <div v-if="!canView" class="paper-panel empty-state"><BookOpen /><p>好友尚未授权你查看美食图鉴。</p></div>
    <template v-else>
      <div class="catalog-tools">
        <label class="search-box">
          <Search aria-hidden="true" /><input v-model="search" class="search-input" type="search" aria-label="搜索食物" placeholder="找一道记过的食物" />
        </label>
        <button v-if="!readonly" class="button favorite-filter" :aria-pressed="favorites" @click="favorites = !favorites">
          <Heart :fill="favorites ? 'currentColor' : 'none'" /> 只看收藏
        </button>
      </div>
      <div class="categories" aria-label="食物分类">
        <button v-for="category in ['全部' as const, ...categories]" :key="category" :aria-pressed="selection === category"
          :class="{ chosen: selection === category }" @click="selection = category">{{ category }}</button>
      </div>
      <div v-if="filtered.length" class="sticker-grid">
        <article v-for="(food, index) in filtered" :key="food.id" class="catalog-entry" :class="'tone-' + (index % 4)">
          <button class="catalog-open" @click="itemId = food.id">
            <div class="catalog-art"><FoodSticker :id="food.stickerId" decorative /></div>
            <div class="catalog-name"><strong>{{ food.name }}</strong><span>{{ food.count }} 次记录</span></div>
          </button>
          <button v-if="!readonly" class="catalog-heart icon-button button-quiet" :aria-label="(food.favorite ? '取消收藏 ' : '收藏 ') + food.name"
            :aria-pressed="food.favorite" @click="diary.favorite(food.id)"><Heart :fill="food.favorite ? 'currentColor' : 'none'" /></button>
        </article>
      </div>
      <div v-else class="paper-panel empty-state"><Shell /><p>{{ search || selection !== '全部' ? '没有找到符合条件的食物。' : favorites ? '收藏喜欢的食物后，会在这里看到它们。' : '暂无食物记录。' }}</p></div>
    </template>
    <ModalSurface :open="!!selected" :title="selected?.name ?? '图鉴详情'" @close="itemId = ''">
      <template v-if="selected">
        <div class="detail-art"><FoodSticker :id="selected.stickerId" :name="selected.name" /></div>
        <div class="catalog-detail">
          <div><span>记录次数</span><strong>{{ selected.count }} 次</strong></div>
          <div><span>首次记录</span><strong>{{ selected.firstDate }}</strong></div>
          <div><span>最近记录</span><strong>{{ selected.latestDate }}</strong></div>
        </div>
        <button v-if="!readonly" class="button" @click="diary.favorite(selected.id)"><Heart :fill="selected.favorite ? 'currentColor' : 'none'" />{{ selected.favorite ? '取消收藏' : '收藏美食' }}</button>
      </template>
    </ModalSurface>
  </div>
</template>

<style scoped>
.catalog-tools { display: flex; gap: calc(var(--space-unit) * 4.8); justify-content: space-between; }
.search-box { position: relative; flex: 1; min-width: 0; max-width: 26rem; }
.search-box svg { color: var(--color-muted); position: absolute; width: 1rem; height: 1rem; top: .88rem; left: .75rem; }
.search-box input { padding-left: calc(var(--space-unit) * 16.8); }
.favorite-filter { flex-shrink: 0; }
.favorite-filter[aria-pressed="true"] { background: var(--color-rose-soft); color: var(--color-terracotta); border-color: var(--color-line-rose); }
.categories { margin: calc(var(--space-unit) * 5.6) 0 calc(var(--space-unit) * 9.6); display: flex; gap: calc(var(--space-unit) * 3.2); flex-wrap: wrap; }
.categories button { padding: calc(var(--space-unit) * 2.8) calc(var(--space-unit) * 6.24); min-height: 2.65rem; border-radius: var(--radius-pill); border: 1px solid var(--color-line); font-size: .88rem; color: var(--color-muted); }
.categories button:hover { background: var(--color-canvas-hover); }
.categories .chosen { border-color: var(--color-sage-deep); background: var(--color-sage-deep); color: var(--color-sheet); }
.sticker-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: calc(var(--space-unit) * 6.8); }
.catalog-entry { position: relative; min-width: 0; isolation: isolate; border-radius: var(--radius-card); border: 1px solid var(--color-line-warm); background: var(--color-paper-warm); }
.tone-1 { background: var(--color-leaf-pale); border-color: var(--color-line-leaf); }
.tone-2 { background: var(--color-peach-soft); border-color: var(--color-line-rose); }
.tone-3 { background: var(--color-canvas-hover); border-color: var(--color-line-warm); }
.catalog-open { display: block; width: 100%; text-align: left; padding: calc(var(--space-unit) * 6.24); border-radius: inherit; }
.catalog-art { height: clamp(6.4rem, 11vw, 10rem); padding: calc(var(--space-unit) * 3.6) calc(var(--space-unit) * 2.24) calc(var(--space-unit) * 2.4); }
.catalog-entry .sticker { transform: rotate(-8deg) scale(.96); transition: transform .22s var(--ease-gentle); }
.catalog-entry:nth-child(even) .sticker { transform: rotate(7deg) scale(.96); }
.catalog-open:hover .sticker, .catalog-open:focus-visible .sticker { transform: rotate(0) scale(1.03); }
.catalog-name { display: grid; gap: calc(var(--space-unit) * 1.44); }
.catalog-name strong { overflow-wrap: anywhere; font-size: .92rem; }
.catalog-name span { color: var(--color-muted); font-size: .77rem; }
.catalog-heart { position: absolute; top: .18rem; right: .2rem; }
.catalog-heart[aria-pressed="true"] { color: var(--color-terracotta); }
.detail-art { height: 10rem; padding: calc(var(--space-unit) * 5.6); background: var(--color-paper-warm); border-radius: var(--radius-card); }
.catalog-detail { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: calc(var(--space-unit) * 4); padding: calc(var(--space-unit) * 5.2) 0; }
.catalog-detail div { display: grid; gap: calc(var(--space-unit) * 2); }
.catalog-detail span { color: var(--color-muted); font-size: .8rem; }
.catalog-detail strong { font-size: .9rem; }
@media (max-width: 720px) { .sticker-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
@media (max-width: 500px) {
  .sticker-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: calc(var(--space-unit) * 4.96); }
  .catalog-open { padding: calc(var(--space-unit) * 4.96); }
  .catalog-art { height: 7rem; }
  .categories { gap: calc(var(--space-unit) * 2.56); }
  .categories button { padding-inline: calc(var(--space-unit) * 4.88); }
}
</style>
