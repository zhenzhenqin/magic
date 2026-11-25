<script setup lang="ts">
import { Pencil, Trash2 } from 'lucide-vue-next'
import { ref, watch } from 'vue'
import { usePhotoUrl } from '../composables/usePhotoUrl'
import type { Meal, MealItem } from '../types/domain'
import { mealLabels } from '../utils/labels'
import FoodSticker from './FoodSticker.vue'
import ModalSurface from './ModalSurface.vue'

const props = defineProps<{ meal?: Meal; item?: MealItem; readonly?: boolean }>()
const emit = defineEmits<{ close: []; remove: [id: string] }>()
const confirming = ref(false)
watch(() => props.meal, () => { confirming.value = false })
const photoUrl = usePhotoUrl(() => props.meal?.photo?.id)
</script>

<template>
  <ModalSurface :open="!!meal && !!item" :title="item?.name ?? '食物详情'" @close="emit('close')">
    <template v-if="meal && item">
      <div class="detail-visual">
        <img v-if="photoUrl" :src="photoUrl" alt="记录照片" class="record-photo" />
        <FoodSticker v-else :id="item.stickerId" :name="item.name" />
      </div>
      <p class="caption">{{ meal.date }} · {{ mealLabels[meal.kind].label }} · {{ meal.time }}</p>
      <p v-if="meal.note">{{ meal.note }}</p>
      <p v-if="item.note" class="caption">{{ item.note }}</p>
      <details v-if="item.calories !== undefined || item.weight !== undefined || item.nutrition" class="nutrition-detail">
        <summary>营养信息（演示）</summary>
        <div class="toolbar caption">
          <span v-if="item.weight !== undefined">重量 {{ item.weight }} g</span>
          <span v-if="item.calories !== undefined">热量 {{ item.calories }} kcal</span>
          <template v-if="item.nutrition">
            <span>蛋白质 {{ item.nutrition.protein }} g</span><span>碳水 {{ item.nutrition.carbs }} g</span><span>脂肪 {{ item.nutrition.fat }} g</span>
          </template>
        </div>
      </details>
      <div v-if="!readonly" class="toolbar">
        <RouterLink class="button" :to="{ name: 'capture', query: { edit: meal.id } }"><Pencil /> 编辑记录</RouterLink>
        <button v-if="!confirming" class="button button-danger" @click="confirming = true"><Trash2 /> 删除记录</button>
        <template v-else>
          <span role="status" class="caption">将删除这餐的全部食物。</span>
          <button class="button button-danger" @click="emit('remove', meal.id)">确认删除</button>
          <button class="button" @click="confirming = false">取消</button>
        </template>
      </div>
    </template>
  </ModalSurface>
</template>

<style scoped>
.detail-visual { display: grid; place-items: center; border-radius: var(--radius-card); background: var(--color-paper-warm); height: 11rem; overflow: hidden; }
.detail-visual .sticker { width: 70%; height: 9rem; }
.record-photo { height: 100%; max-height: 11rem; width: 100%; object-fit: contain; }
.nutrition-detail { border-block: 1px solid var(--color-line); padding: calc(var(--space-unit) * 5.2) 0; }
.nutrition-detail summary { font-size: .94rem; font-weight: 650; color: var(--color-sage-deep); }
.nutrition-detail div { margin-top: calc(var(--space-unit) * 3.6); gap: calc(var(--space-unit) * 3.2) calc(var(--space-unit) * 6.4); }
</style>
