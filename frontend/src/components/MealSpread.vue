<script setup lang="ts">
import { Coffee, Moon, Plus, Sun, Utensils } from 'lucide-vue-next'
import type { Meal, MealItem, MealKind } from '../types/domain'
import { mealKinds } from '../types/domain'
import { mealLabels } from '../utils/labels'
import FoodSticker from './FoodSticker.vue'

defineProps<{ meals: Meal[]; readonly?: boolean }>()
const emit = defineEmits<{ open: [meal: Meal, item: MealItem]; add: [kind: MealKind] }>()
const icons = { breakfast: Coffee, lunch: Sun, dinner: Moon, snack: Utensils }
</script>

<template>
  <div class="meal-spread">
    <section v-for="kind in mealKinds" :key="kind" class="meal-section" :class="kind" :aria-label="mealLabels[kind].label">
      <div class="meal-rail">
        <span class="meal-icon"><component :is="icons[kind]" aria-hidden="true" /></span>
        <h3>{{ mealLabels[kind].label }}</h3>
      </div>
      <div class="meal-content">
        <template v-if="meals.some(meal => meal.kind === kind)">
          <article v-for="meal in meals.filter(meal => meal.kind === kind)" :key="meal.id" class="meal-entry">
            <div class="entry-copy">
              <time>{{ meal.time }}</time>
              <p v-if="meal.note" class="entry-note">{{ meal.note }}</p>
            </div>
            <div class="food-line" :class="{ 'single-food': meal.items.length === 1 }">
              <button v-for="item in meal.items" :key="item.id" class="food-link" @click="emit('open', meal, item)">
                <FoodSticker :id="item.stickerId" decorative />
                <span>{{ item.name }}</span>
              </button>
            </div>
          </article>
        </template>
        <p v-else-if="readonly" class="meal-empty">暂无共享记录</p>
        <button v-else class="meal-empty text-action" @click="emit('add', kind)"><Plus /> 记一笔{{ mealLabels[kind].label }}</button>
      </div>
    </section>
  </div>
</template>

<style scoped>
.meal-spread { border-top: 1px solid var(--color-line); }
.meal-section { display: grid; grid-template-columns: 5rem minmax(0, 1fr); gap: calc(var(--space-unit) * 6.8); min-height: 6rem; padding: calc(var(--space-unit) * 7.2) calc(var(--space-unit) * 1.2); border-bottom: 1px solid var(--color-line); }
.meal-rail { padding-top: calc(var(--space-unit) * 5.2); display: flex; align-items: flex-start; gap: calc(var(--space-unit) * 3.84); flex-direction: column; }
.meal-icon { display: grid; place-items: center; width: 2.32rem; height: 2.32rem; border-radius: var(--radius-round); color: var(--color-earth); background: var(--color-butter); }
.meal-icon svg { width: 1.1rem; height: 1.1rem; stroke-width: 1.55; }
.lunch .meal-icon { background: var(--color-peach-soft); color: var(--color-terracotta); }
.dinner .meal-icon { background: var(--color-leaf); color: var(--color-sage-deep); }
.snack .meal-icon { background: var(--color-rose-soft); color: var(--color-terracotta); }
h3 { font-weight: 700; font-size: .93rem; }
.meal-entry { min-width: 0; display: grid; grid-template-columns: minmax(6rem, .7fr) minmax(0, 1.3fr); align-items: center; gap: calc(var(--space-unit) * 3.6) calc(var(--space-unit) * 5.6); }
.meal-entry + .meal-entry { border-top: 1px dashed var(--color-line); margin-top: calc(var(--space-unit) * 4.8); padding-top: calc(var(--space-unit) * 4.8); }
.entry-copy { display: grid; gap: calc(var(--space-unit) * 4); min-width: 0; }
time { color: var(--color-sage-deep); font: 700 1.05rem/1.2 var(--font-editorial); font-variant-numeric: tabular-nums; }
.entry-note { padding-left: calc(var(--space-unit) * 4.64); border-left: 2px solid var(--color-line-warm); color: var(--color-muted); font-size: .87rem; line-height: 1.65; overflow-wrap: anywhere; }
.food-line { min-width: 0; display: flex; flex-wrap: wrap; justify-content: space-evenly; align-items: end; gap: calc(var(--space-unit) * 3.6); }
.food-link { display: flex; flex-direction: column; align-items: center; flex: 1 1 5.2rem; max-width: 9rem; min-width: 0; gap: calc(var(--space-unit) * 1.2); border-radius: var(--radius-small); padding: calc(var(--space-unit) * 1.2); }
.food-link .sticker { height: 6.25rem; transform: rotate(-7deg); transition: transform .22s var(--ease-gentle); }
.food-link:nth-child(even) .sticker { transform: rotate(8deg) translateY(.18rem); }
.food-link:hover .sticker, .food-link:focus-visible .sticker { transform: rotate(0) translateY(-.25rem); }
.food-link > span:last-child { font-size: .86rem; font-weight: 650; text-align: center; overflow-wrap: anywhere; }
.single-food .food-link { max-width: 10.6rem; }
.single-food .sticker { transform: rotate(5deg); }
.meal-empty { color: var(--color-muted); min-height: 4rem; display: flex; align-items: center; }
@media (max-width: 660px) {
  .meal-section { grid-template-columns: 3.15rem minmax(0, 1fr); padding: calc(var(--space-unit) * 6) 0; gap: calc(var(--space-unit) * 4.4); }
  .meal-entry { grid-template-columns: 1fr; }
  .entry-copy { grid-template-columns: auto minmax(0, 1fr); align-items: baseline; }
  .entry-note { font-size: .8rem; }
  .food-line { justify-content: flex-start; }
  .food-link { max-width: 7.8rem; }
  .food-link .sticker { height: 5.35rem; }
  .single-food .food-link { max-width: 8.75rem; }
}
</style>
