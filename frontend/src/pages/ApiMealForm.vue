<script setup lang="ts">
import { ImagePlus, Plus, Trash2, Camera, X } from 'lucide-vue-next'
import { computed, onScopeDispose, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ApiError } from '../api/client'
import { nutrientFields, useDiaryApi } from '../api/diaryRepository'
import type { MealInput, MealItemInput } from '../api/diaryRepository'
import PageHeading from '../components/PageHeading.vue'
import PrivatePhoto from '../components/PrivatePhoto.vue'
import { useApiDay } from '../composables/useApiDay'
import { usePrivateQuery } from '../composables/usePrivateQuery'
import { authMessage } from '../stores/auth'
import { mealKinds } from '../types/domain'
import type { MealKind } from '../types/domain'
import { mealLabels } from '../utils/labels'

interface DraftPhoto { key: string; id?: string; file?: File; preview?: string }
const route = useRoute()
const router = useRouter()
const api = useDiaryApi()
const { selected, timezone } = useApiDay()
const identifier = computed(() => typeof route.query.edit === 'string' ? route.query.edit : undefined)
const lookup = usePrivateQuery(() => identifier.value, (id, signal) => id ? api.meal(id, signal) : Promise.resolve(undefined))
const { current: saved, pending: loading, error: loadError } = lookup
const requested = route.query.kind as MealKind
const defaultKind = mealKinds.includes(requested) ? requested : 'lunch'
const blank = (): MealItemInput => ({
  food_name: '', category: null, weight_g: null, calories_kcal: null, protein_g: null, carbohydrates_g: null, fat_g: null, note: '',
})
const fields = { weight_g: { label: '重量', unit: 'g' }, ...nutrientFields }
const draft = reactive<MealInput>({
  meal_type: defaultKind, local_date: selected.value, local_time: mealLabels[defaultKind].time, timezone: timezone.value,
  note: '', items: [blank()], media_ids: [],
})
const photos = ref<DraftPhoto[]>([])
const error = ref('')
const progress = ref('')
const picking = ref<HTMLInputElement>()
const camera = ref<HTMLInputElement>()
let saveAttempt: { key: string; body: string; uncertain: boolean } | undefined
let active = true

watch(timezone, zone => { if (!identifier.value) draft.timezone = zone })
watch(selected, date => {
  if (!identifier.value && !route.query.date) draft.local_date = date
})
watch(saved, meal => {
  if (!meal) return
  photos.value.forEach(dispose)
  photos.value = meal.media.map(photo => ({ key: photo.id, id: photo.id }))
  Object.assign(draft, {
    meal_type: meal.meal_type, local_date: meal.local_date, local_time: meal.local_time.slice(0, 5),
    timezone: meal.timezone, note: meal.note,
    items: meal.items.map(({ id: _id, source: _source, ...item }) => {
      const { food_name, category, weight_g, calories_kcal, protein_g, carbohydrates_g, fat_g, note } = item
      return { food_name, category, weight_g, calories_kcal, protein_g, carbohydrates_g, fat_g, note }
    }),
  })
  saveAttempt = undefined
})

function dispose(photo: DraftPhoto) { if (photo.preview) URL.revokeObjectURL(photo.preview) }
onScopeDispose(() => {
  active = false
  photos.value.forEach(dispose)
})

function choose(event: Event) {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files ?? [])
  input.value = ''
  error.value = ''
  if (files.length + photos.value.length > 5) { error.value = '一餐最多选择 5 张照片。'; return }
  if (files.some(file => file.size > 10 * 1024 * 1024)) { error.value = '单张照片最多 10 MiB。'; return }
  photos.value.push(...files.map(file => ({ key: crypto.randomUUID(), file, preview: URL.createObjectURL(file) })))
}

function removePhoto(index: number) {
  dispose(photos.value[index])
  photos.value.splice(index, 1)
}

function collect(): MealInput {
  return {
    ...draft, media_ids: photos.value.map(photo => photo.id).filter((id): id is string => !!id),
    items: draft.items.map(item => {
      const clean = { ...item, food_name: item.food_name.trim(), category: item.category?.trim() || null }
      for (const key of Object.keys(fields) as (keyof typeof fields)[]) {
        clean[key] = typeof clean[key] === 'number' ? clean[key] : null
      }
      return clean
    }),
  }
}

async function submit() {
  if (progress.value || (identifier.value && !saved.value)) return
  error.value = ''
  try {
    if (draft.items.some(item => !item.food_name.trim())) {
      error.value = '请为每个食物填写名称。'
      return
    }
    if (saveAttempt?.uncertain && photos.value.some(photo => !photo.id)) {
      error.value = '上次保存结果未知。请还原更改后重试，或先回手账核对。'
      return
    }
    let index = 0
    for (const photo of photos.value) {
      index++
      if (photo.id || !photo.file) continue
      progress.value = '正在上传图片 ' + index + ' / ' + photos.value.length
      photo.id = (await api.upload(photo.file)).id
      if (!active) return
    }
    const input = collect()
    const fingerprint = JSON.stringify(input)
    if (!saved.value && saveAttempt?.uncertain && saveAttempt.body !== fingerprint) {
      error.value = '上次保存结果未知。请还原更改后重试，或先回手账核对。'
      return
    }
    progress.value = '正在保存…'
    let result
    if (saved.value) {
      result = await api.edit(saved.value.id, input, saved.value.version)
    } else {
      if (saveAttempt?.body !== fingerprint) saveAttempt = { key: crypto.randomUUID(), body: fingerprint, uncertain: false }
      saveAttempt.uncertain = true
      result = await api.create(input, saveAttempt.key)
    }
    if (active) await router.push({ name: 'diary', query: { date: result.local_date } })
  } catch (failure) {
    if (saveAttempt && failure instanceof ApiError && failure.status > 0 && failure.status < 500) saveAttempt.uncertain = false
    error.value = authMessage(failure)
  } finally {
    progress.value = ''
  }
}
</script>

<template>
  <div>
    <RouterLink class="text-action" :to="{ name: 'diary', query: { date: draft.local_date } }">返回手账</RouterLink>
    <PageHeading :title="identifier ? '编辑饮食' : '记下这一餐'" subtitle="从照片或食物名称开始，记下这一餐。" />
    <p v-if="identifier && loading" class="caption" role="status">正在读取记录…</p>
    <div v-else-if="identifier && loadError" class="paper-panel empty-state"><p>{{ loadError }}</p><button class="button" @click="lookup.reload()">重新读取</button></div>
    <form v-else class="capture-grid" @submit.prevent="submit">
      <section class="paper-panel panel-pad form-stack">
        <h2>食物照片</h2>
        <input ref="picking" type="file" accept="image/jpeg,image/png,image/webp" multiple hidden @change="choose" />
        <input ref="camera" type="file" accept="image/*" capture="environment" hidden @change="choose" />
        <div v-if="photos.length" class="previews" aria-label="上传预览">
          <figure v-for="(photo, index) in photos" :key="photo.key" class="preview">
            <img v-if="photo.preview" :src="photo.preview" :alt="'待保存的照片 ' + (index + 1)" />
            <PrivatePhoto v-else-if="photo.id" :id="photo.id" :alt="'已有照片 ' + (index + 1)" />
            <button type="button" class="icon-button remove-image" :aria-label="'移除照片 ' + (index + 1)" :disabled="!!progress" @click="removePhoto(index)"><X /></button>
          </figure>
        </div>
        <p class="caption">JPEG、PNG 或 WebP，每餐最多 5 张，每张不超过 10 MiB。</p>
        <div class="toolbar">
          <button type="button" class="button" :disabled="!!progress || photos.length >= 5" @click="picking?.click()"><ImagePlus /> 选择本地图片</button>
          <button type="button" class="button" :disabled="!!progress || photos.length >= 5" @click="camera?.click()"><Camera /> 拍一张</button>
        </div>
        <p v-if="!photos.length" class="caption">也可以只填写食物信息。</p>
      </section>
      <section class="paper-panel panel-pad">
        <fieldset class="form-stack" :disabled="!!progress" aria-label="饮食信息">
          <div class="field-grid">
            <label class="field">记录日期<input v-model="draft.local_date" type="date" required min="1900-01-01" max="2200-12-31" /></label>
            <label class="field">餐次<select v-model="draft.meal_type"><option v-for="kind in mealKinds" :key="kind" :value="kind">{{ mealLabels[kind].label }}</option></select></label>
          </div>
          <label class="field">用餐时间<input v-model="draft.local_time" type="time" required /></label>
          <p class="caption">记录时区 {{ draft.timezone }}</p>
          <fieldset v-for="(item, index) in draft.items" :key="index" class="food-form form-stack">
            <legend>食物 {{ index + 1 }}</legend>
            <div class="field-grid">
              <label class="field">食物名称<input v-model="item.food_name" maxlength="80" required /></label>
              <label class="field">分类<input v-model="item.category" maxlength="40" placeholder="可选" /></label>
            </div>
            <details :open="identifier ? true : undefined">
              <summary>营养信息与食物备注</summary>
              <div class="field-grid nutrient-fields">
                <label v-for="(field, key) in fields" :key="key" class="field">{{ field.label }} ({{ field.unit }})
                  <input v-model.number="item[key]" type="number" min="0" max="100000" step="0.01" inputmode="decimal" />
                </label>
              </div>
              <label class="field">食物备注<input v-model="item.note" maxlength="500" /></label>
            </details>
            <button v-if="draft.items.length > 1" type="button" class="text-action" @click="draft.items.splice(index, 1)"><Trash2 /> 移除食物 {{ index + 1 }}</button>
          </fieldset>
          <button type="button" class="text-action" :disabled="draft.items.length >= 30" @click="draft.items.push(blank())"><Plus /> 添加另一种食物</button>
          <label class="field">这一餐的备注<textarea v-model="draft.note" maxlength="1000" placeholder="记下想留住的细节" /></label>
          <p v-if="error" class="form-error" role="alert">{{ error }}</p>
          <button type="submit" class="button button-primary">{{ progress || '保存记录' }}</button>
        </fieldset>
        <button v-if="identifier && error" class="text-action" @click="lookup.reload()">重新读取服务端记录</button>
      </section>
    </form>
  </div>
</template>

<style scoped>
.capture-grid { display: grid; grid-template-columns: minmax(0, .85fr) minmax(0, 1.15fr); align-items: start; gap: 1rem; }
h2, legend { font: 700 1.17rem var(--font-serif); }
fieldset { min-width: 0; }
.previews { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .55rem; }
.preview { position: relative; margin: 0; min-width: 0; aspect-ratio: 4/3; border: 4px solid var(--color-sheet); border-radius: var(--radius-small); background: var(--color-canvas-hover); }
.preview img { width: 100%; height: 100%; object-fit: cover; border-radius: var(--radius-small); }
.remove-image { position: absolute; right: .2rem; top: .2rem; z-index: 1; }
.food-form { padding: .65rem; border: 1px solid var(--color-line); border-radius: var(--radius-card); background: var(--color-rail); }
.food-form legend { padding-inline: .35rem; }
.nutrient-fields { margin-block: .65rem; }
@media (max-width: 690px) { .capture-grid { grid-template-columns: minmax(0, 1fr); } }
</style>
