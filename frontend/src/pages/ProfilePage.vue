<script setup lang="ts">
import { ChartNoAxesColumn, Heart, RotateCcw, ShieldCheck, UserRound } from 'lucide-vue-next'
import { computed, ref } from 'vue'
import AvatarBadge from '../components/AvatarBadge.vue'
import ModalSurface from '../components/ModalSurface.vue'
import PageHeading from '../components/PageHeading.vue'
import { users } from '../mocks/seed'
import { useDiary } from '../stores/diary'

const diary = useDiary()
const confirming = ref(false)
const busy = ref(false)
const notice = ref('')
const recordedDays = computed(() => new Set(diary.meals().map(meal => meal.date)).size)
const favoriteCount = computed(() => diary.catalog().filter(food => food.favorite).length)
const firstFriend = computed(() => diary.relationships.find(relationship => relationship.status === 'accepted'))
const changeAccount = (event: Event) => diary.selectAccount((event.target as HTMLSelectElement).value)
async function reset() {
  busy.value = true
  try {
    await diary.reset()
    notice.value = '已恢复初始演示数据。'
    confirming.value = false
  } catch {
    notice.value = '重置失败，请检查浏览器存储权限后重试。'
    confirming.value = false
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="profile-page">
    <PageHeading title="我的" />
    <div class="profile-grid">
      <section class="paper-panel panel-pad profile-card">
        <div class="profile-person"><AvatarBadge :user="diary.account" size="large" /><div><h2>{{ diary.account.nickname }}</h2><p class="caption">用户 ID · {{ diary.account.id }}</p></div></div>
        <div class="profile-counts"><div><strong>{{ recordedDays }}</strong><span>记录天数</span></div><div><strong>{{ favoriteCount }}</strong><span>收藏美食</span></div></div>
      </section>
      <section class="paper-panel panel-pad profile-actions" aria-label="手账设置">
        <RouterLink to="/me/stats" class="profile-link"><ChartNoAxesColumn /> 饮食统计</RouterLink>
        <RouterLink :to="{ name: 'catalog', query: { favorites: '1' } }" class="profile-link"><Heart /> 我的收藏</RouterLink>
        <RouterLink to="/friends" class="profile-link"><UserRound /> 好友管理</RouterLink>
        <RouterLink class="profile-link" :to="firstFriend ? { name: 'permissions', params: { id: diary.otherId(firstFriend) } } : '/friends'"><ShieldCheck /> 共享设置</RouterLink>
      </section>
      <section class="paper-panel panel-pad demo-panel">
        <h2>演示设置</h2>
        <label class="field">切换演示账号
          <select :value="diary.account.id" @change="changeAccount"><option v-for="user in users" :key="user.id" :value="user.id">{{ user.nickname }}（{{ user.id }}）</option></select>
        </label>
        <p class="caption">可通过不同视角核对好友共享权限。数据仅保存在此浏览器。</p>
        <div class="toolbar"><button class="button button-danger" @click="confirming = true"><RotateCcw /> 重置演示数据</button><span class="caption">FoodDiary v0.1.0</span></div>
        <p v-if="notice" class="badge" role="status">{{ notice }}</p>
      </section>
    </div>
    <ModalSurface :open="confirming" title="重置演示数据" @close="!busy && (confirming = false)">
      <p>这会清除此浏览器中新增的演示记录、照片和授权设置，并恢复样例。</p>
      <div class="toolbar"><button class="button button-danger" :disabled="busy" @click="reset">确认重置</button><button class="button" :disabled="busy" @click="confirming = false">取消</button></div>
    </ModalSurface>
  </div>
</template>

<style scoped>
.profile-page { max-width: 51rem; margin-inline: auto; }
.profile-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: calc(var(--space-unit) * 7.6); }
.profile-person { display: flex; gap: calc(var(--space-unit) * 6.4); align-items: center; }
h2 { font: 700 1.35rem var(--font-serif); }
.profile-card { background: var(--color-leaf-selected); }
.profile-counts { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); margin-top: calc(var(--space-unit) * 6.8); border-top: 1px solid var(--color-line-leaf); }
.profile-counts div { display: grid; gap: calc(var(--space-unit) * 1.44); padding: calc(var(--space-unit) * 6.4) calc(var(--space-unit) * 2.8) calc(var(--space-unit) * 0.8); }
.profile-counts strong { font: 700 1.75rem var(--font-editorial); color: var(--color-sage-deep); }
.profile-counts span { color: var(--color-muted); font-size: .86rem; }
.profile-actions { display: grid; gap: calc(var(--space-unit) * 1.6); }
.profile-link { min-height: var(--tap-size); padding: calc(var(--space-unit) * 2.8) calc(var(--space-unit) * 4); border-radius: var(--radius-small); display: flex; gap: calc(var(--space-unit) * 6.4); align-items: center; font-size: .9rem; font-weight: 650; }
.profile-link:hover { background: var(--color-leaf); }
.profile-link svg { width: 1.15rem; height: 1.15rem; stroke-width: 1.55; color: var(--color-sage-deep); }
.demo-panel { grid-column: 1 / -1; display: grid; justify-items: start; gap: calc(var(--space-unit) * 5.6); }
@media (max-width: 620px) { .profile-grid { grid-template-columns: minmax(0, 1fr); } }
</style>
