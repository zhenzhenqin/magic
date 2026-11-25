<script setup lang="ts">
import { BookHeart, HandHeart, Plus, UserRoundPlus } from 'lucide-vue-next'
import { computed, ref } from 'vue'
import AvatarBadge from '../components/AvatarBadge.vue'
import FoodSticker from '../components/FoodSticker.vue'
import ModalSurface from '../components/ModalSurface.vue'
import PageHeading from '../components/PageHeading.vue'
import { users } from '../mocks/seed'
import { useDiary } from '../stores/diary'
import { dayLabel } from '../utils/dates'

const diary = useDiary()
const adding = ref(false)
const search = ref('')
const notice = ref('')
const friends = computed(() => diary.relationships.flatMap(relationship => {
  const user = diary.person(diary.otherId(relationship))
  if (relationship.status !== 'accepted' || !user) return []
  const meals = diary.meals(undefined, user.id)
  const latest = meals.reduce<string | undefined>((current, meal) => !current || meal.updatedAt > current ? meal.updatedAt : current, undefined)
  const stickers = meals.filter(meal => meal.date === meals[0]?.date).flatMap(meal => meal.items).filter(item => item.stickerId).slice(0, 3)
  return [{ user, latest, stickers, incoming: diary.permissions(user.id), outgoing: diary.permissions(diary.account.id, user.id) }]
}))
const pending = computed(() => diary.relationships.flatMap(relationship => {
  const user = diary.person(diary.otherId(relationship))
  return user && relationship.status === 'pending' ? [{ relationship, user }] : []
}))
const available = computed(() => users.filter(user => user.id !== diary.account.id &&
  !diary.relationships.some(rel => diary.otherId(rel) === user.id && rel.status !== 'rejected') &&
  (user.id.toLowerCase().includes(search.value.trim().toLowerCase()) || user.nickname.includes(search.value.trim()))))
function add(id: string) {
  if (!diary.requestFriend(id)) return
  notice.value = '已发送演示申请。可切换到对方账号处理。'
  adding.value = false
  search.value = ''
}
function answer(id: string, status: 'accepted' | 'rejected') {
  diary.answerRequest(id, status)
  notice.value = status === 'accepted' ? '已接受申请。双方可以各自设置共享范围。' : '已拒绝申请。'
}
function lastSeen(value: string) {
  return dayLabel(value.slice(0, 10)) + ' ' + value.slice(11, 16)
}
</script>

<template>
  <div>
    <PageHeading title="饭搭子" subtitle="把日常的好味道，留给愿意互相分享的人。">
      <button class="button button-primary" @click="adding = true"><Plus /> 添加好友</button>
    </PageHeading>
    <p v-if="notice" class="notice badge" role="status">{{ notice }}</p>
    <div v-if="friends.length" class="friend-grid">
      <article v-for="friend in friends" :key="friend.user.id" class="friend-paper paper-panel">
        <header><AvatarBadge :user="friend.user" /><div><h2>{{ friend.user.nickname }}</h2><p class="caption">{{ friend.latest ? '更新于 ' + lastSeen(friend.latest) : '暂无可查看的更新' }}</p></div></header>
        <div class="friend-art" :class="friend.user.tone">
          <FoodSticker v-for="item in friend.stickers" :key="item.id" :id="item.stickerId" decorative />
          <div v-if="!friend.stickers.length" class="preview-state"><BookHeart /><span>{{ friend.incoming.records ? '暂无共享贴纸' : '对方尚未分享饮食记录' }}</span></div>
        </div>
        <div class="toolbar friend-actions">
          <RouterLink :to="{ name: 'friend-diary', params: { id: friend.user.id } }" class="button">好友手账</RouterLink>
          <RouterLink :to="{ name: 'friend-catalog', params: { id: friend.user.id } }" class="button">好友图鉴</RouterLink>
          <RouterLink :to="{ name: 'together', params: { id: friend.user.id } }" class="button button-primary">双人手账</RouterLink>
        </div>
        <div class="friend-access">
          <span class="caption">{{ friend.outgoing.records ? '已向对方分享记录' : '未向对方分享记录' }}</span>
          <RouterLink :to="{ name: 'permissions', params: { id: friend.user.id } }" class="text-action">共享授权</RouterLink>
        </div>
      </article>
    </div>
    <div v-else class="paper-panel empty-state"><HandHeart /><p>还没有饭搭子。可以给演示账号发一条好友申请。</p></div>
    <section v-if="pending.length" class="requests">
      <h2>好友申请</h2>
      <article v-for="{ relationship, user } in pending" :key="relationship.id" class="request paper-panel">
        <AvatarBadge :user="user" size="small" />
        <div class="request-copy"><strong>{{ user.nickname }}</strong><p class="caption">{{ relationship.recipientId === diary.account.id ? '想成为你的饭搭子' : '等待对方处理' }}</p></div>
        <div v-if="relationship.recipientId === diary.account.id" class="toolbar">
          <button class="button button-primary" @click="answer(relationship.id, 'accepted')">接受</button>
          <button class="button" @click="answer(relationship.id, 'rejected')">拒绝</button>
        </div>
      </article>
    </section>
    <ModalSurface :open="adding" title="添加饭搭子" @close="adding = false">
      <label class="field">昵称或演示 ID<input v-model="search" type="search" placeholder="例如 小鱼" /></label>
      <p v-if="!available.length" class="caption">没有可添加的演示账号。</p>
      <div v-for="user in available" :key="user.id" class="candidate">
        <AvatarBadge :user="user" size="small" /><div><strong>{{ user.nickname }}</strong><p class="caption">@{{ user.id }}</p></div>
        <button class="button button-primary" @click="add(user.id)"><UserRoundPlus /> 发送申请</button>
      </div>
    </ModalSurface>
  </div>
</template>

<style scoped>
.notice { margin-bottom: calc(var(--space-unit) * 6.8); }
.friend-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: calc(var(--space-unit) * 8); }
.friend-paper { padding: calc(var(--space-unit) * 8); min-width: 0; }
.friend-paper header { display: flex; align-items: center; gap: calc(var(--space-unit) * 5.6); }
h2 { font: 700 1.35rem/1.3 var(--font-serif); }
.friend-art { min-height: 8.2rem; margin: calc(var(--space-unit) * 6.8) 0; padding: calc(var(--space-unit) * 4); display: flex; align-items: center; gap: calc(var(--space-unit) * 1.2); border-radius: var(--radius-card); background: var(--color-leaf-pale); }
.friend-art.peach { background: var(--color-peach-soft); }
.friend-art.butter { background: var(--color-paper-warm); }
.friend-art .sticker { flex: 1 1 0; height: 6.8rem; transform: rotate(-7deg); }
.friend-art .sticker:nth-child(2) { transform: rotate(9deg) translateY(.36rem); }
.preview-state { min-height: 6.9rem; width: 100%; display: grid; justify-items: center; align-content: center; gap: calc(var(--space-unit) * 3.2); color: var(--color-muted); font-size: .88rem; text-align: center; }
.preview-state svg { width: 1.4rem; height: 1.4rem; stroke-width: 1.45; }
.friend-actions { gap: calc(var(--space-unit) * 2.8); }
.friend-actions .button { flex: 1 0 auto; padding-inline: calc(var(--space-unit) * 3.84); }
.friend-access { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: calc(var(--space-unit) * 2.4); margin-top: calc(var(--space-unit) * 2); }
.requests { display: grid; gap: calc(var(--space-unit) * 5.6); margin-top: calc(var(--space-unit) * 12); }
.request, .candidate { display: flex; flex-wrap: wrap; align-items: center; gap: calc(var(--space-unit) * 5.2); }
.request { padding: calc(var(--space-unit) * 6) calc(var(--space-unit) * 7.2); }
.request-copy, .candidate div { flex: 1; min-width: 4rem; }
.candidate + .candidate { border-top: 1px solid var(--color-line); padding-top: calc(var(--space-unit) * 5.2); }
@media (max-width: 600px) { .friend-grid { grid-template-columns: minmax(0, 1fr); } }
</style>
