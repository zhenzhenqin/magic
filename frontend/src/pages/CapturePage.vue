<script setup lang="ts">
import { Camera, ImagePlus, Plus, ScanLine, Trash2, X } from 'lucide-vue-next'
import { computed, onScopeDispose, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { mediaRepository } from '../api/mediaRepository'
import { mockRepository } from '../api/mockRepository'
import FoodSticker from '../components/FoodSticker.vue'
import PageHeading from '../components/PageHeading.vue'
import { usePhotoUrl } from '../composables/usePhotoUrl'
import { foods, sampleItem } from '../mocks/seed'
import { useDiary } from '../stores/diary'
import type { Meal, MealItem, MealKind, MediaAsset } from '../types/domain'
import { mealKinds } from '../types/domain'
import { isDateKey, todayKey } from '../utils/dates'
import { mealLabels } from '../utils/labels'
import { preparePhoto } from '../utils/photos'

const diary = useDiary()
const route = useRoute()
const router = useRouter()
const existing = computed(() => diary.meals().find(meal => meal.id === route.query.edit))
const emptyItem = (): MealItem => ({ id: crypto.randomUUID(), foodId: '', name: '', category: '其他' })
const date = ref('')
const kind = ref<MealKind>('lunch')
const time = ref('')
const note = ref('')
const items = ref<MealItem[]>([])
const input = ref<HTMLInputElement>()
const localImage = ref<File>()
const localUrl = ref('')
const existingPhoto = ref<MediaAsset>()
const persistedUrl = usePhotoUrl(() => existingPhoto.value?.id)
const preview = computed(() => localUrl.value || persistedUrl.value)
const busy = ref(false)
const saving = ref(false)
const recognized = ref(false)
const error = ref('')
let selection = 0

function clearLocal() {
  if (localUrl.value) URL.revokeObjectURL(localUrl.value)
  localImage.value = undefined
  localUrl.value = ''
  selection++
  busy.value = false
}
watch([() => route.query, () => diary.account.id], () => {
  const meal = existing.value
  const requestedKind = route.query.kind as MealKind
  date.value = meal?.date ?? (isDateKey(route.query.date) ? route.query.date : todayKey())
  kind.value = meal?.kind ?? (mealKinds.includes(requestedKind) ? requestedKind : 'lunch')
  time.value = meal?.time ?? mealLabels[kind.value].time
  note.value = meal?.note ?? ''
  items.value = meal?.items.map(item => ({ ...item })) ?? [emptyItem()]
  clearLocal()
  existingPhoto.value = meal?.photo
  recognized.value = false
  error.value = ''
}, { immediate: true })
onScopeDispose(clearLocal)

function choose(event: Event) {
  const control = event.target as HTMLInputElement
  const file = control.files?.[0]
  control.value = ''
  if (!file) return
  if (!file.type.startsWith('image/') || file.size > 20 * 1024 * 1024) {
    error.value = '请选择小于或等于 20 MiB 的图片。'
    return
  }
  clearLocal()
  error.value = ''
  recognized.value = false
  localImage.value = file
  localUrl.value = URL.createObjectURL(file)
}
function removePhoto() {
  clearLocal()
  existingPhoto.value = undefined
  recognized.value = false
}
async function recognize() {
  if (!preview.value || busy.value) return
  busy.value = true
  const token = selection
  const suggestions = await mockRepository.recognize()
  if (selection !== token) return
  items.value = suggestions
  recognized.value = true
  busy.value = false
}
const validNumber = (value?: number) => typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : undefined
function normalize(item: MealItem): MealItem {
  const name = item.name.trim()
  const seed = foods.find(food => food.name === name)
  const defaultItem = seed && sampleItem(seed.id, item.id)
  return { ...item, name, foodId: seed?.id ?? 'custom-' + name.toLowerCase(),
    category: seed?.category ?? '其他', stickerId: seed?.id, note: item.note?.trim(),
    weight: validNumber(item.weight), calories: validNumber(item.calories), nutrition: defaultItem?.nutrition }
}
async function save() {
  if (saving.value) return
  error.value = ''
  const mealItems = items.value.filter(item => item.name.trim()).map(normalize)
  if (!mealItems.length || !isDateKey(date.value) || !/^\d{2}:\d{2}$/.test(time.value)) {
    error.value = '请输入至少一项食物名称，并补全日期和时间。'
    return
  }
  const ownerId = diary.account.id
  const mealDate = date.value
  const id = existing.value?.id ?? crypto.randomUUID()
  let newPhoto: MediaAsset | undefined
  saving.value = true
  try {
    if (localImage.value) {
      const photo = await preparePhoto(localImage.value)
      newPhoto = { id: crypto.randomUUID(), name: localImage.value.name, mimeType: photo.type }
      await mediaRepository.save(newPhoto.id, photo)
    }
    const meal: Meal = { id, ownerId, date: mealDate, kind: kind.value, time: time.value, items: mealItems,
      note: note.value.trim(), photo: newPhoto ?? existingPhoto.value, updatedAt: new Date().toISOString() }
    if (!diary.saveMeal(meal)) throw new Error('Account changed')
  } catch {
    if (newPhoto) await mediaRepository.delete(newPhoto.id).catch(() => {})
    error.value = '无法保存记录，请检查图片格式和浏览器存储空间。'
    return
  } finally {
    saving.value = false
  }
  await router.push({ name: 'diary', query: { date: mealDate } })
}
</script>

<template>
  <div class="capture-page">
    <RouterLink class="text-action" :to="{ name: 'diary', query: { date } }">返回手账</RouterLink>
    <PageHeading :title="existing ? '编辑记录' : '记下这一餐'" subtitle="上传照片，或从食物名称开始。" />
    <div v-if="route.query.edit && !existing" class="paper-panel empty-state"><p>当前演示账号下没有这条记录。</p></div>
    <form v-else class="capture-layout" @submit.prevent="save">
      <section class="paper-panel panel-pad photo-panel">
        <h2><Camera /> 食物照片</h2>
        <input ref="input" type="file" accept="image/*" aria-label="选择本地图片" class="file-input" tabindex="-1" @change="choose" />
        <div v-if="preview" class="photo-preview">
          <img :src="preview" alt="所选食物图片预览" @error="error = '图片无法预览，请选择常见格式的图片。'; removePhoto()" />
          <button type="button" class="icon-button photo-clear" aria-label="移除照片" :disabled="saving" @click="removePhoto"><X /></button>
        </div>
        <button v-else type="button" class="photo-picker" @click="input?.click()"><ImagePlus /><strong>选择本地图片</strong><span>最多 20 MiB</span></button>
        <div class="toolbar">
          <button v-if="preview" type="button" class="button" :disabled="saving" @click="input?.click()">更换图片</button>
          <button v-if="preview" type="button" class="button button-primary" :disabled="busy || saving" @click="recognize"><ScanLine /> {{ busy ? '正在演示识别…' : '模拟 AI 识别' }}</button>
        </div>
        <p class="caption">仅为演示。照片保存在此浏览器，不会上传。</p>
        <p v-if="recognized" class="badge" role="status">已填入演示识别结果，可编辑</p>
      </section>
      <section class="paper-panel panel-pad form-stack">
        <fieldset :disabled="saving" class="form-stack">
          <legend class="visually-hidden">编辑饮食记录</legend>
          <div class="field-grid">
            <label class="field">记录日期<input v-model="date" type="date" required /></label>
            <label class="field">餐次<select v-model="kind" @change="time = mealLabels[kind].time"><option v-for="key in mealKinds" :key="key" :value="key">{{ mealLabels[key].label }}</option></select></label>
          </div>
          <label class="field">用餐时间<input v-model="time" type="time" required /></label>
          <article v-for="(item, index) in items" :key="item.id" class="food-form">
            <header><h2>{{ items.length > 1 ? '食物 ' + (index + 1) : '食物' }}</h2>
              <FoodSticker v-if="item.stickerId" :id="item.stickerId" decorative />
              <button v-if="items.length > 1" type="button" class="icon-button button-quiet" :aria-label="'移除食物 ' + (index + 1)" @click="items.splice(index, 1)"><Trash2 /></button></header>
            <label class="field">食物名称<input v-model="item.name" type="text" maxlength="60" placeholder="例如 日式咖喱饭" /></label>
            <div class="field-grid">
              <label class="field">重量 (g)<input v-model.number="item.weight" type="number" min="0" max="100000" step="any" inputmode="decimal" /></label>
              <label class="field">热量 (kcal)<input v-model.number="item.calories" type="number" min="0" max="100000" step="any" inputmode="decimal" /></label>
            </div>
            <label class="field">食物备注<input v-model="item.note" type="text" maxlength="120" placeholder="可选" /></label>
          </article>
          <button type="button" class="text-action" @click="items.push(emptyItem())"><Plus /> 添加另一种食物</button>
          <label class="field">这一餐的备注<textarea v-model="note" maxlength="300" placeholder="记下想留住的细节" /></label>
          <p v-if="error" class="form-error" role="alert">{{ error }}</p>
          <button class="button button-primary" type="submit" :disabled="saving || busy">{{ saving ? '正在保存…' : '保存记录' }}</button>
        </fieldset>
      </section>
    </form>
  </div>
</template>

<style scoped>
.capture-layout { display: grid; grid-template-columns: minmax(0, .9fr) minmax(0, 1.1fr); gap: calc(var(--space-unit) * 8); align-items: start; }
.photo-panel { display: grid; gap: calc(var(--space-unit) * 6.4); }
.photo-panel h2 { display: flex; align-items: center; gap: calc(var(--space-unit) * 3.52); }
h2 { font: 700 1.17rem var(--font-serif); }
h2 svg { width: 1.1rem; height: 1.1rem; stroke-width: 1.6; }
.photo-picker { display: grid; justify-items: center; align-content: center; gap: calc(var(--space-unit) * 3.84); padding: calc(var(--space-unit) * 6.4); min-height: 12.8rem; background: var(--color-leaf-pale); border: 1px dashed var(--color-control-line); border-radius: var(--radius-card); color: var(--color-sage-deep); }
.photo-picker:hover { background: var(--color-leaf); }
.photo-picker svg { width: 2rem; height: 2rem; stroke-width: 1.35; }
.photo-picker span { font-size: .8rem; }
.file-input, .visually-hidden { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; white-space: nowrap; overflow: hidden; clip-path: inset(50%); }
.photo-preview { position: relative; height: clamp(10rem, 25vw, 16rem); background: var(--color-canvas-hover); border-radius: var(--radius-card); overflow: hidden; }
.photo-preview img { width: 100%; height: 100%; object-fit: contain; }
.photo-clear { position: absolute; top: .45rem; right: .45rem; }
.food-form { padding: calc(var(--space-unit) * 6); display: grid; gap: calc(var(--space-unit) * 5.2); border-radius: var(--radius-card); border: 1px solid var(--color-line); background: var(--color-rail); }
.food-form header { display: flex; align-items: center; min-height: 2rem; justify-content: space-between; gap: calc(var(--space-unit) * 4); }
.food-form header .sticker { width: 3.75rem; height: 2.5rem; margin-left: auto; }
fieldset { min-width: 0; }
@media (max-width: 690px) { .capture-layout { grid-template-columns: minmax(0, 1fr); } .photo-picker { min-height: 9.5rem; } }
</style>
