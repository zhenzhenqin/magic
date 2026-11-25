<script setup lang="ts">
import { BookHeart, Coffee, Moon, Sun, Utensils } from 'lucide-vue-next'
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import AvatarBadge from '../components/AvatarBadge.vue'
import DateStrip from '../components/DateStrip.vue'
import FoodSticker from '../components/FoodSticker.vue'
import PageHeading from '../components/PageHeading.vue'
import { useDiaryDate } from '../composables/useDiaryDate'
import { useDiary } from '../stores/diary'
import { mealKinds } from '../types/domain'
import { dayLabel, todayKey, weekdayLabel } from '../utils/dates'
import { mealLabels } from '../utils/labels'

const route = useRoute()
const diary = useDiary()
const { selectedDate, setDate } = useDiaryDate()
const friend = computed(() => diary.person(String(route.params.id)))
const friendAccess = computed(() => diary.permissions(String(route.params.id)))
const participants = computed(() => [diary.account, ...(friend.value ? [friend.value] : [])])
const records = computed(() => participants.value.map(user => diary.meals(selectedDate.value, user.id)))
const recordedDates = computed(() => [...new Set(participants.value.flatMap(user => diary.meals(undefined, user.id).map(meal => meal.date)))])
const icons = { breakfast: Coffee, lunch: Sun, dinner: Moon, snack: Utensils }
</script>

<template>
  <div class="together">
    <RouterLink class="text-action" to="/friends">返回饭搭子</RouterLink>
    <PageHeading title="双人手账" :subtitle="dayLabel(selectedDate) + ' · ' + weekdayLabel(selectedDate)">
      <span v-if="friend" class="badge"><BookHeart :size="16" /> {{ diary.account.nickname }} 与 {{ friend.nickname }}</span>
    </PageHeading>
    <DateStrip :selected="selectedDate" :recorded="recordedDates" @select="setDate" />
    <div class="shared-book paper-panel">
      <div class="book-header">
        <div v-for="user in participants" :key="user.id"><AvatarBadge :user="user" size="small" /><strong>{{ user.nickname }}的这一餐</strong></div>
      </div>
      <section v-for="kind in mealKinds" :key="kind" class="book-section" :aria-label="mealLabels[kind].label">
        <h2><component :is="icons[kind]" aria-hidden="true" />{{ mealLabels[kind].label }}</h2>
        <div class="book-pair">
          <div v-for="(user, index) in participants" :key="user.id" class="page-half" :class="{ 'friend-half': index === 1 }">
            <span class="mobile-user">{{ user.nickname }}</span>
            <p v-if="index === 1 && !friendAccess.records" class="book-empty">对方尚未授权饮食记录</p>
            <p v-else-if="index === 1 && !friendAccess.history && selectedDate !== todayKey()" class="book-empty">对方仅分享当天记录</p>
            <template v-else-if="records[index]?.some(meal => meal.kind === kind)">
              <article v-for="meal in records[index].filter(meal => meal.kind === kind)" :key="meal.id">
                <time>{{ meal.time }}</time>
                <div class="book-items">
                  <div v-for="item in meal.items" :key="item.id"><FoodSticker :id="item.stickerId" decorative /><span>{{ item.name }}</span></div>
                </div>
                <p v-if="meal.note" class="book-note">{{ meal.note }}</p>
              </article>
            </template>
            <p v-else class="book-empty">这餐暂时留白</p>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.shared-book { margin-top: calc(var(--space-unit) * 8); position: relative; padding: calc(var(--space-unit) * 7.2); }
.book-header, .book-pair { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); }
.book-header { border-bottom: 1px solid var(--color-line); padding-bottom: calc(var(--space-unit) * 5.6); }
.book-header > div { display: flex; align-items: center; justify-content: center; gap: calc(var(--space-unit) * 4); text-align: center; font-size: .88rem; }
.book-section { padding: calc(var(--space-unit) * 6) 0; }
.book-section + .book-section { border-top: 1px solid var(--color-line); }
.book-section h2 { display: flex; align-items: center; justify-content: center; gap: calc(var(--space-unit) * 3.04); font: 700 1rem var(--font-serif); color: var(--color-sage-deep); }
.book-section h2 svg { width: 1rem; height: 1rem; stroke-width: 1.55; }
.book-pair { margin-top: calc(var(--space-unit) * 3.2); }
.page-half { min-width: 0; padding: calc(var(--space-unit) * 2.4) clamp(calc(var(--space-unit) * 3.6), 2vw, calc(var(--space-unit) * 9.6)); }
.friend-half { border-left: 1px dashed var(--color-line-warm); }
.page-half article + article { margin-top: calc(var(--space-unit) * 4.4); }
time { color: var(--color-sage-deep); font: 700 .95rem var(--font-editorial); }
.book-items { display: flex; flex-wrap: wrap; gap: calc(var(--space-unit) * 4.4); justify-content: center; }
.book-items > div { flex: 0 1 6.9rem; max-width: 44%; min-width: 0; text-align: center; font-size: .84rem; font-weight: 650; overflow-wrap: anywhere; }
.book-items .sticker { height: 5.2rem; transform: rotate(-7deg); }
.friend-half .sticker { transform: rotate(8deg); }
.book-note, .book-empty { margin-top: calc(var(--space-unit) * 3.84); color: var(--color-muted); font-size: .85rem; line-height: 1.55; text-align: center; overflow-wrap: anywhere; }
.mobile-user { display: none; }
@media (max-width: 390px) {
  .book-items > div { flex-basis: 100%; max-width: 100%; }
  .book-items .sticker { height: 4.65rem; }
}
</style>
