<script setup lang="ts">
import type { SharedMeal } from '../api/sharingRepository'
import { mealLabels } from '../utils/labels'
import SharedPhoto from './SharedPhoto.vue'

defineProps<{ owner: string; meal: SharedMeal }>()
defineEmits<{ open: [id: string] }>()
</script>

<template>
  <button type="button" class="shared-scrap" @click="$emit('open', meal.id)">
    <span v-if="meal.media?.length" class="scrap-photos">
      <SharedPhoto v-for="media in meal.media" :key="media.id" :owner="owner" :media="media" :context="{ meal_id: meal.id }" />
    </span>
    <span class="scrap-title">{{ meal.items?.map(item => item.food_name).filter(Boolean).join('、') || mealLabels[meal.meal_type].label }}</span>
    <span class="caption">{{ mealLabels[meal.meal_type].label }} · {{ meal.local_time }}</span>
  </button>
</template>

<style scoped>
.shared-scrap { display: grid; align-content: start; justify-items: center; gap: .22rem; min-width: 0; width: 100%; padding: .4rem .2rem; text-align: center; }
.shared-scrap:hover .scrap-title { text-decoration: underline; text-underline-offset: .2em; }
.scrap-photos { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(5.5rem, 100%), 1fr)); width: 100%; gap: .35rem; }
.scrap-photos > * { min-height: 3.6rem; height: clamp(5.2rem, 23vw, 10rem); }
.scrap-title { color: var(--diary-ink-soft); font: 600 clamp(1rem, 3.5vw, 1.32rem) var(--font-hand); overflow-wrap: anywhere; }
</style>
