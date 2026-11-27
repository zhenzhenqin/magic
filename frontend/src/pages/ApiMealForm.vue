<script setup lang="ts">
import { ImagePlus, Plus, Trash2, Camera, X, Sparkles, LoaderCircle } from 'lucide-vue-next'
import { computed, onScopeDispose, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ApiError } from '../api/client'
import { nutrientFields, useDiaryApi } from '../api/diaryRepository'
import type { MealInput, MealItemInput } from '../api/diaryRepository'
import type { AiCandidate } from '../api/aiRepository'
import { stickerRunning } from '../api/stickerRepository'
import ModalSurface from '../components/ModalSurface.vue'
import PageHeading from '../components/PageHeading.vue'
import PrivatePhoto from '../components/PrivatePhoto.vue'
import { useApiDay } from '../composables/useApiDay'
import { usePrivateQuery } from '../composables/usePrivateQuery'
import { useDraftStickers } from '../composables/useDraftStickers'
import { useMealRecognition } from '../composables/useMealRecognition'
import type { DraftPhoto } from '../composables/useMealRecognition'
import { authMessage } from '../stores/auth'
import { mealKinds } from '../types/domain'
import type { MealKind } from '../types/domain'
import { mealLabels } from '../utils/labels'

interface DraftItem extends MealItemInput {
  draftKey: string
  source?: 'manual' | 'ai' | 'ai_edited'
  simulated?: boolean
  uncertainty?: string | null
  aiMedia?: string[]
}
const route = useRoute()
const router = useRouter()
const api = useDiaryApi()
const { selected, timezone } = useApiDay()
const identifier = computed(() => typeof route.query.edit === 'string' ? route.query.edit : undefined)
const lookup = usePrivateQuery(() => identifier.value, (id, signal) => id ? api.meal(id, signal) : Promise.resolve(undefined))
const { current: saved, pending: loading, error: loadError } = lookup
const requested = route.query.kind as MealKind
const defaultKind = mealKinds.includes(requested) ? requested : 'lunch'
const blank = (): DraftItem => ({
  draftKey: crypto.randomUUID(), food_name: '', category: null, weight_g: null, calories_kcal: null,
  protein_g: null, carbohydrates_g: null, fat_g: null, note: '',
})
const fields = { weight_g: { label: '重量', unit: 'g' }, ...nutrientFields }
const emptyDraft = (): Omit<MealInput, 'items'> & { items: DraftItem[] } => ({
  meal_type: defaultKind, local_date: selected.value, local_time: mealLabels[defaultKind].time, timezone: timezone.value,
  note: '', items: [blank()], media_ids: [],
})
const draft = reactive(emptyDraft())
const photos = ref<DraftPhoto[]>([])
const uploadScope = new AbortController()
const uploads = new Map<string, Promise<string>>()
let uploadTail = Promise.resolve()
function uploadPhoto(photo: DraftPhoto): Promise<string> {
  if (photo.id) return Promise.resolve(photo.id)
  const pending = uploads.get(photo.key)
  if (pending) return pending
  const file = photo.file
  if (!file) return Promise.reject(new Error('Missing photo'))
  const task = uploadTail.then(async () => {
    if (uploadScope.signal.aborted || !photos.value.some(value => value.key === photo.key)) throw new Error('Photo removed')
    photo.id = (await api.upload(file, uploadScope.signal)).id
    return photo.id
  }).finally(() => uploads.delete(photo.key))
  uploadTail = task.then(() => {}, () => {})
  uploads.set(photo.key, task)
  return task
}
const { states: stickerStates, enabled: stickersEnabled, online: stickersOnline, simulated: stickersSimulated,
  auto: autoSticker, run: runSticker, check: checkStickerWorker } = useDraftStickers(() => photos.value, uploadPhoto)
const cropTarget = ref<DraftPhoto>()
const cropLabels = { left: '左边距', top: '上边距', width: '宽度', height: '高度' }
const cropDraft = reactive({ left: 8, top: 8, width: 84, height: 84 })
const validCrop = computed(() => cropDraft.left >= 0 && cropDraft.top >= 0 && cropDraft.width >= 3 && cropDraft.height >= 3
  && cropDraft.left + cropDraft.width <= 100 && cropDraft.top + cropDraft.height <= 100)
function openCrop(photo: DraftPhoto) {
  Object.assign(cropDraft, { left: 8, top: 8, width: 84, height: 84 })
  cropTarget.value = photo
}
function applyCrop() {
  const target = cropTarget.value
  if (!target || !validCrop.value) return
  const { left, top, width, height } = cropDraft
  void runSticker(target, 'retry', { left: left / 100, top: top / 100, width: width / 100, height: height / 100 })
  cropTarget.value = undefined
}
const {
  capabilities, capabilityError, maxImages, selected: selectedPhotos, picked, job, candidates, applied, waiting,
  error: recognitionError, jobMessage, dialog, canResume, togglePhoto, run, recovered, canRestore, restore,
  recoveryError, explicitlyRestored, workerOnline, refreshRecovery,
} = useMealRecognition(() => photos.value, () => identifier.value, value => { photos.value = value }, uploadPhoto)
const mayCancel = computed(() => job.value?.status === 'pending' || job.value?.status === 'running')
const isEmpty = (item: DraftItem) => !item.id && !item.ai_reference && !item.food_name.trim()
  && !item.category?.trim() && !item.note.trim() && Object.keys(fields).every(key => item[key as keyof typeof fields] == null)
const hasExistingFood = computed(() => draft.items.some(item => !isEmpty(item)))
const error = ref('')
const maySaveWithoutSource = ref(false)
const progress = ref('')
const picking = ref<HTMLInputElement>()
const camera = ref<HTMLInputElement>()
let saveAttempt: { key: string; body: string; uncertain: boolean } | undefined
let active = true
let formVersion = 0

watch(timezone, zone => { if (!identifier.value) draft.timezone = zone })
watch(selected, date => {
  if (!identifier.value && !route.query.date) draft.local_date = date
})
watch(identifier, () => {
  formVersion++
  photos.value.forEach(dispose)
  photos.value = []
  Object.assign(draft, emptyDraft())
  error.value = progress.value = ''
  maySaveWithoutSource.value = false
  saveAttempt = undefined
}, { flush: 'sync' })
watch(saved, meal => {
  if (!meal) return
  photos.value.forEach(dispose)
  photos.value = meal.media.map(photo => ({ key: photo.id, id: photo.id }))
  Object.assign(draft, {
    meal_type: meal.meal_type, local_date: meal.local_date, local_time: meal.local_time.slice(0, 5),
    timezone: meal.timezone, note: meal.note,
    items: meal.items.map(({ id, source, ai_provider, ...item }) => {
      const { food_name, category, weight_g, calories_kcal, protein_g, carbohydrates_g, fat_g, note } = item
      return { id, source, simulated: ai_provider === 'fake', draftKey: id,
        food_name, category, weight_g, calories_kcal, protein_g, carbohydrates_g, fat_g, note }
    }),
  })
  saveAttempt = undefined
})

function dispose(photo: DraftPhoto) { if (photo.preview) URL.revokeObjectURL(photo.preview) }
onScopeDispose(() => {
  active = false
  uploadScope.abort()
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
  const photo = photos.value[index]
  dispose(photo)
  photos.value.splice(index, 1)
  if (photo.id) {
    for (const item of draft.items) {
      if (item.aiMedia?.includes(photo.id)) clearReference(item)
    }
  }
}

function applyCandidates(mode: 'append' | 'replace') {
  const recognized = job.value
  if (!recognized || !candidates.value.length) return
  const existing = mode === 'append' ? draft.items.filter(item => !isEmpty(item)) : []
  if (existing.length + candidates.value.length > 30) return
  draft.items = [...existing, ...candidates.value.map(({ id, uncertainty, ...candidate }: AiCandidate): DraftItem => ({
    ...candidate, draftKey: id, uncertainty, ai_reference: { job_id: recognized.id, candidate_id: id },
    simulated: recognized.simulated, source: 'ai', note: '', aiMedia: recognized.media_ids,
  }))]
  applied.value = true
}

watch(candidates, foods => {
  if (foods.length && !explicitlyRestored.value && !hasExistingFood.value && !progress.value && !saveAttempt?.uncertain) {
    applyCandidates('replace')
  }
})

function startRecognition() {
  if (capabilities.value?.available && workerOnline.value && selectedPhotos.value.length && !waiting.value && !progress.value) {
    dialog.value = 'start'
  }
}

function collect(): MealInput {
  return {
    ...draft, media_ids: photos.value.map(photo => photo.id).filter((id): id is string => !!id),
    items: draft.items.map(({ draftKey: _key, source: _source, simulated: _simulated, uncertainty: _uncertainty, aiMedia: _media, ...item }) => {
      const clean = { ...item, food_name: item.food_name.trim(), category: item.category?.trim() || null }
      for (const key of Object.keys(fields) as (keyof typeof fields)[]) {
        clean[key] = typeof clean[key] === 'number' ? clean[key] : null
      }
      return clean
    }),
  }
}

async function submit() {
  if (progress.value || (waiting.value && !job.value) || (identifier.value && !saved.value)) return
  const version = formVersion
  error.value = ''
  maySaveWithoutSource.value = false
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
      await uploadPhoto(photo)
      if (!active || version !== formVersion) return
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
    if (active && version === formVersion) await router.push({ name: 'diary', query: { date: result.local_date } })
  } catch (failure) {
    if (!active || version !== formVersion) return
    if (saveAttempt && failure instanceof ApiError && failure.status > 0 && failure.status < 500) saveAttempt.uncertain = false
    error.value = authMessage(failure)
    maySaveWithoutSource.value = failure instanceof ApiError
      && ['ai_job_not_found', 'ai_candidate_not_found', 'ai_candidate_unavailable', 'ai_candidate_used', 'ai_candidate_context'].includes(failure.code)
  } finally {
    if (version === formVersion) progress.value = ''
  }
}

function clearReference(item: DraftItem) {
  delete item.ai_reference
  delete item.source
  delete item.uncertainty
  delete item.simulated
  delete item.aiMedia
}

function keepAsManual() {
  draft.items.filter(item => item.ai_reference).forEach(clearReference)
  error.value = ''
  maySaveWithoutSource.value = false
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
            <PrivatePhoto v-if="photo.id && stickerStates[photo.key]?.job?.ready && stickerStates[photo.key]?.mode !== 'original'"
              :id="photo.id" class="preview-sticker" :presentation="stickerStates[photo.key].mode === 'cutout' ? 'cutout' : 'sticker'"
              :revision="stickerStates[photo.key].job?.result_id" :alt="stickerStates[photo.key].mode === 'cutout' ? '透明抠图' : '美食贴纸'" />
            <img v-else-if="photo.preview" :src="photo.preview" :alt="'待保存的照片 ' + (index + 1)" />
            <PrivatePhoto v-else-if="photo.id" :id="photo.id" :alt="'已有照片 ' + (index + 1)" />
            <button type="button" class="icon-button remove-image" :aria-label="'移除照片 ' + (index + 1)" :disabled="!!progress" @click="removePhoto(index)"><X /></button>
            <label v-if="capabilities?.available" class="photo-choice">
              <input type="checkbox" :checked="picked.includes(photo.key)"
                :disabled="!!progress || (!picked.includes(photo.key) && picked.length >= maxImages)"
                :aria-label="'识别照片 ' + (index + 1)"
                @change="togglePhoto(photo.key, ($event.target as HTMLInputElement).checked)" /> 参与识别
            </label>
            <figcaption v-if="stickersEnabled" class="sticker-controls">
              <p v-if="stickerStates[photo.key]?.busy || stickerRunning(stickerStates[photo.key]?.job)" role="status"><LoaderCircle class="spin" aria-hidden="true" /> 正在制作你的美食贴纸…</p>
              <p v-else-if="stickerStates[photo.key]?.error || stickerStates[photo.key]?.job?.status === 'failed'" role="status">这次没能完整取出食物，可以先使用原图。</p>
              <p v-else-if="stickerStates[photo.key]?.job?.ready" role="status">{{ stickerStates[photo.key]?.job?.manual ? '手动裁剪已保存。' : '美食贴纸做好啦。' }}</p>
              <div v-if="stickerStates[photo.key]?.job?.ready" class="sticker-modes" aria-label="图片预览方式">
                <button v-for="mode in (['original', 'cutout', 'sticker'] as const)" :key="mode" type="button" class="text-action"
                  :aria-pressed="stickerStates[photo.key].mode === mode" @click="stickerStates[photo.key].mode = mode">{{ { original: '原图', cutout: '抠图', sticker: '贴纸' }[mode] }}</button>
              </div>
              <button v-if="stickerRunning(stickerStates[photo.key]?.job)" type="button" class="text-action" @click="runSticker(photo, 'cancel')">取消制作</button>
              <div v-else-if="stickersOnline && !stickerStates[photo.key]?.busy" class="sticker-modes">
                <button v-if="stickerStates[photo.key]?.job" type="button" class="text-action" @click="runSticker(photo, 'retry')">重新生成</button>
                <button v-else type="button" class="text-action" @click="runSticker(photo, 'make')">制作贴纸</button>
                <button v-if="photo.id && stickerStates[photo.key]?.job" type="button" class="text-action" @click="openCrop(photo)">手动裁剪</button>
              </div>
            </figcaption>
          </figure>
        </div>
        <p class="caption">JPEG、PNG 或 WebP，每餐最多 5 张，每张不超过 10 MiB。</p>
        <div class="toolbar">
          <button type="button" class="button" :disabled="!!progress || photos.length >= 5" @click="picking?.click()"><ImagePlus /> 选择本地图片</button>
          <button type="button" class="button" :disabled="!!progress || photos.length >= 5" @click="camera?.click()"><Camera /> 拍一张</button>
        </div>
        <p v-if="!photos.length" class="caption">也可以只填写食物信息。</p>
        <div v-if="stickersEnabled" class="sticker-options">
          <label><input v-model="autoSticker" type="checkbox" /> 自动制作贴纸</label>
          <span v-if="stickersSimulated" class="caption">模拟抠图</span>
          <button v-if="!stickersOnline" class="text-action" type="button" @click="checkStickerWorker">贴纸暂不可用 · 检查状态</button>
        </div>
        <div v-if="recovered" class="recognition form-stack">
          <p class="caption" role="status">{{ ['pending', 'running'].includes(recovered.status) ? '有一项识别尚未完成。' : '找到了上次的识别任务。' }}</p>
          <p v-if="!canRestore" class="caption">当前餐次或照片与上次不匹配，恢复前请核对。</p>
          <div class="toolbar">
            <button v-if="canRestore" type="button" class="button" :disabled="waiting || !!progress" @click="restore">恢复这次识别</button>
            <button v-if="['pending', 'running'].includes(recovered.status)" type="button" class="text-action"
              :disabled="waiting" @click="run('cancel', recovered)">取消上次识别</button>
          </div>
        </div>
        <div v-else-if="recoveryError" class="toolbar">
          <button type="button" class="text-action" @click="refreshRecovery">重新检查未完成的识别</button>
        </div>
        <div v-if="photos.length || (capabilities?.available && workerOnline === false)" class="recognition form-stack" aria-label="AI 食物识别">
          <p v-if="capabilities && !capabilities.available" class="caption">AI 识别暂不可用，你仍可以手动记录。</p>
          <p v-else-if="capabilityError" class="caption">暂时无法检查 AI 识别，仍可手动记录。</p>
          <template v-else-if="capabilities?.available">
            <p v-if="capabilities.simulated" class="caption">本地模拟识别 · 使用示例结果</p>
            <p v-if="workerOnline === false" class="caption" role="status">
              {{ mayCancel ? '识别服务暂未连接，任务已保留，可以继续手动记录。' : '识别服务暂未连接，可以继续手动记录。' }}
            </p>
            <p v-else-if="waiting && !recognitionError" class="caption ai-wait" role="status"><LoaderCircle /> 正在看看你今天吃了什么……</p>
            <p v-if="recognitionError || jobMessage" class="caption" role="status">{{ recognitionError || jobMessage }}</p>
            <div class="toolbar">
              <button v-if="!mayCancel && !job?.can_retry" type="button" class="button"
                :disabled="!workerOnline || waiting || !!progress || !selectedPhotos.length" @click="startRecognition"><Sparkles /> {{ job?.status === 'succeeded' ? '重新识别' : 'AI 识别' }}</button>
              <button v-if="mayCancel" type="button" class="text-action" @click="run('cancel')">取消识别</button>
              <button v-if="canResume" type="button" class="button" :disabled="waiting" @click="run('resume')">继续查看结果</button>
              <button v-if="job?.can_retry" type="button" class="button" :disabled="!workerOnline || waiting || !!progress" @click="dialog = 'retry'">重试识别</button>
            </div>
            <div v-if="candidates.length" class="form-stack">
              <p>找到了 {{ candidates.length }} 样美食</p>
              <p class="caption">{{ candidates.map(food => food.food_name).join('、') }}</p>
              <p class="caption">份量和营养信息是估算结果，可以修改哦。</p>
              <p v-for="warning in job?.result?.warnings" :key="warning" class="caption">{{ warning }}</p>
              <div class="toolbar">
                <button type="button" class="button" :disabled="!!progress || draft.items.filter(item => !isEmpty(item)).length + candidates.length > 30"
                  @click="applyCandidates('append')">追加到表单</button>
                <button type="button" class="text-action" :disabled="!!progress" @click="applyCandidates('replace')">替换食物明细</button>
              </div>
            </div>
            <template v-if="applied">
              <p class="caption" role="status">已填入食物。份量和营养信息是估算结果，可以修改哦。</p>
              <p v-for="warning in job?.result?.warnings" :key="warning" class="caption">{{ warning }}</p>
            </template>
            <p v-if="!waiting && !job" class="caption">同一道菜的多个角度可一起识别，最多选择 {{ maxImages }} 张。</p>
          </template>
        </div>
      </section>
      <section class="paper-panel panel-pad">
        <fieldset class="form-stack" :disabled="!!progress" aria-label="饮食信息">
          <div class="field-grid">
            <label class="field">记录日期<input v-model="draft.local_date" type="date" required min="1900-01-01" max="2200-12-31" /></label>
            <label class="field">餐次<select v-model="draft.meal_type"><option v-for="kind in mealKinds" :key="kind" :value="kind">{{ mealLabels[kind].label }}</option></select></label>
          </div>
          <label class="field">用餐时间<input v-model="draft.local_time" type="time" required /></label>
          <p class="caption">记录时区 {{ draft.timezone }}</p>
          <fieldset v-for="(item, index) in draft.items" :key="item.draftKey" class="food-form form-stack">
            <legend>食物 {{ index + 1 }}</legend>
            <p v-if="item.source && item.source !== 'manual'" class="caption">
              {{ item.simulated ? '模拟估算' : item.source === 'ai_edited' ? 'AI 估算 · 已人工修正' : 'AI 估算' }}
              <span v-if="item.uncertainty"> · {{ item.uncertainty }}</span>
            </p>
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
          <button v-if="maySaveWithoutSource" type="button" class="text-action" @click="keepAsManual">将这次识别结果转为手动明细</button>
          <button type="submit" class="button button-primary" :disabled="waiting && !job">{{ progress || '保存记录' }}</button>
        </fieldset>
        <button v-if="identifier && error" class="text-action" @click="lookup.reload()">重新读取服务端记录</button>
      </section>
    </form>
    <ModalSurface :open="!!cropTarget" title="手动裁剪照片" @close="cropTarget = undefined">
      <div v-if="cropTarget" class="form-stack">
        <div class="crop-preview">
          <img v-if="cropTarget.preview" :src="cropTarget.preview" alt="待裁剪原图" />
          <PrivatePhoto v-else-if="cropTarget.id" :id="cropTarget.id" original natural alt="待裁剪原图" />
          <div class="crop-box" :style="{ left: cropDraft.left + '%', top: cropDraft.top + '%', width: cropDraft.width + '%', height: cropDraft.height + '%' }"></div>
        </div>
        <label v-for="(label, key) in cropLabels" :key="key" class="field">
          {{ label }}（%）<input v-model.number="cropDraft[key]" type="number" :min="key === 'width' || key === 'height' ? 3 : 0" max="100" />
        </label>
        <button type="button" class="button button-primary" :disabled="!validCrop" @click="applyCrop">使用裁剪</button>
      </div>
    </ModalSurface>
    <ModalSurface :open="!!dialog" :title="dialog === 'retry' ? '再试一次识别' : '用照片识别食物'" @close="dialog = undefined">
      <p v-if="capabilities?.simulated">本地模拟会使用示例结果，所选照片将留在本地测试环境。</p>
      <template v-else>
        <p>所选食物照片将发送至{{ capabilities?.provider === 'deepseek' ? ' DeepSeek 服务' : '阿里云百炼' }}，用于识别食物及估算营养。建议选择只包含食物的照片。</p>
        <p class="caption">取消识别后，已经发送的请求可能仍会完成。</p>
        <a v-if="capabilities?.privacy_url" class="text-action" :href="capabilities.privacy_url"
          target="_blank" rel="noopener noreferrer">查看服务商的隐私说明</a>
      </template>
      <p v-if="dialog === 'retry' && job?.error_code === 'ai_result_unknown'" class="caption">上次调用可能已经计费，再次识别可能产生新的费用。</p>
      <div class="toolbar">
        <button type="button" class="button button-primary" @click="run(dialog === 'retry' ? 'retry' : 'start')">同意并{{ dialog === 'retry' ? '重试' : '识别' }}</button>
        <button type="button" class="text-action" @click="dialog = undefined">先手动记录</button>
      </div>
    </ModalSurface>
  </div>
</template>

<style scoped>
.capture-grid { display: grid; grid-template-columns: minmax(0, .85fr) minmax(0, 1.15fr); align-items: start; gap: 1rem; }
h2, legend { font: 700 1.17rem var(--font-serif); }
fieldset { min-width: 0; }
.previews { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .55rem; }
.preview { position: relative; margin: 0; min-width: 0; border: 4px solid var(--color-sheet); border-radius: var(--radius-small); background: var(--color-canvas-hover); overflow: hidden; }
.preview > img, .preview > .private-photo { width: 100%; height: auto; aspect-ratio: 4/3; object-fit: cover; border-radius: var(--radius-small); }
.preview > .preview-sticker { background: #f7f4ef; }
.sticker-controls { padding: .34rem .38rem; font-size: .74rem; display: grid; gap: .18rem; align-content: start; }
.sticker-controls p { display: flex; align-items: center; gap: .15rem; }
.sticker-controls svg { width: .75rem; height: .75rem; flex: none; }
.sticker-modes, .sticker-options { display: flex; flex-wrap: wrap; align-items: center; gap: .44rem; }
.sticker-modes .text-action { min-height: 1.6rem; padding: .08rem .18rem; font-size: .73rem; }
.sticker-modes [aria-pressed="true"] { text-decoration: underline; text-underline-offset: .18rem; }
.crop-preview { position: relative; }
.crop-preview > img { width: 100%; height: auto; display: block; }
.crop-box { position: absolute; border: 2px dashed white; box-shadow: 0 0 0 1px #111, 0 0 0 60vmax #0005; pointer-events: none; }
.crop-preview { overflow: hidden; }
.remove-image { position: absolute; right: .2rem; top: .2rem; z-index: 1; }
.photo-choice { position: absolute; inset: auto auto .2rem .2rem; display: flex; align-items: center; gap: .3rem; min-height: 1.7rem; padding: .15rem .4rem; background: var(--color-sheet); border-radius: var(--radius-small); font-size: .78rem; }
.photo-choice input { accent-color: var(--color-sage-deep); }
.recognition { border-top: 1px solid var(--color-line); padding-top: .8rem; }
.recognition .toolbar:empty { display: none; }
.ai-wait { display: flex; align-items: center; gap: .4rem; }
.ai-wait svg { width: 1rem; height: 1rem; }
@media (prefers-reduced-motion: no-preference) {
  .ai-wait svg { animation: turn 2s linear infinite; }
  @keyframes turn { to { transform: rotate(360deg); } }
}
.food-form { padding: .65rem; border: 1px solid var(--color-line); border-radius: var(--radius-card); background: var(--color-rail); }
.food-form legend { padding-inline: .35rem; }
.nutrient-fields { margin-block: .65rem; }
@media (max-width: 690px) { .capture-grid { grid-template-columns: minmax(0, 1fr); } }
</style>
