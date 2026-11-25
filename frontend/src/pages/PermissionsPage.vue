<script setup lang="ts">
import { Eye, LockKeyhole, ShieldCheck } from 'lucide-vue-next'
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AvatarBadge from '../components/AvatarBadge.vue'
import ModalSurface from '../components/ModalSurface.vue'
import PageHeading from '../components/PageHeading.vue'
import { newPermissions } from '../mocks/seed'
import { useDiary } from '../stores/diary'
import { permissionKeys } from '../types/domain'
import type { PermissionKey } from '../types/domain'
import { permissionLabels } from '../utils/labels'

const route = useRoute()
const router = useRouter()
const diary = useDiary()
const friend = computed(() => diary.person(String(route.params.id)))
const valid = computed(() => !!friend.value && diary.isFriend(friend.value.id))
const outgoing = computed(() => diary.permissions(diary.account.id, String(route.params.id)))
const incoming = computed(() => diary.permissions(String(route.params.id), diary.account.id))
const incomingKeys = computed(() => permissionKeys.filter(key => incoming.value[key]))
const confirming = ref(false)
const notice = ref('')
const subtitles: Record<PermissionKey, string> = {
  records: '按餐次查看记录和时间',
  names: '显示食物名称',
  photos: '查看记录附带的本地演示照片',
  stickers: '在共享页面显示贴纸',
  catalog: '查看从记录汇总的美食图鉴',
  calories: '显示记录中的演示热量',
  nutrition: '显示重量、蛋白质、碳水及脂肪',
  notes: '阅读餐次与食物备注',
  history: '允许查看当天以外的记录',
}

function change(key: PermissionKey, event: Event) {
  if (!friend.value) return
  diary.changeGrant(friend.value.id, { ...outgoing.value, [key]: (event.target as HTMLInputElement).checked })
  notice.value = '共享设置已保存。'
}
function revoke() {
  if (!friend.value) return
  diary.changeGrant(friend.value.id, newPermissions())
  notice.value = '已停止向对方共享。'
  confirming.value = false
}
function previewAsFriend() {
  const owner = diary.account.id
  if (!friend.value || !valid.value) return
  diary.selectAccount(friend.value.id)
  void router.push({ name: 'friend-diary', params: { id: owner } })
}
</script>

<template>
  <div class="permission-page">
    <RouterLink to="/friends" class="text-action">返回饭搭子</RouterLink>
    <PageHeading title="共享授权" subtitle="前端演示。正式访问控制将在后端实现。">
      <span v-if="friend && valid" class="badge"><ShieldCheck :size="16" /> {{ friend.nickname }}</span>
    </PageHeading>
    <div v-if="!valid || !friend" class="paper-panel empty-state"><LockKeyhole /><p>成为饭搭子后，可以选择各自愿意分享的内容。</p></div>
    <div v-else class="permission-layout">
      <section class="paper-panel panel-pad outgoing">
        <header><AvatarBadge :user="diary.account" size="small" /><div><h2>我共享给{{ friend.nickname }}</h2><p class="caption">仅设置从你发出的权限。</p></div></header>
        <label v-for="key in permissionKeys" :key="key" class="permission-row">
          <span><strong>{{ permissionLabels[key] }}</strong><small>{{ subtitles[key] }}</small></span>
          <input type="checkbox" class="switch-input" :checked="outgoing[key]" :aria-label="permissionLabels[key]" @change="change(key, $event)" />
        </label>
        <div class="toolbar permission-actions">
          <button class="button button-primary" @click="previewAsFriend"><Eye /> 用对方视角查看</button>
          <button class="button button-danger" @click="confirming = true">停止全部共享</button>
        </div>
        <p v-if="notice" class="caption" role="status">{{ notice }}</p>
      </section>
      <aside class="paper-panel panel-pad incoming">
        <header><AvatarBadge :user="friend" size="small" /><div><h2>{{ friend.nickname }}共享给我</h2><p class="caption">此权限由对方独立设置。</p></div></header>
        <div v-if="incomingKeys.length" class="toolbar"><span v-for="key in incomingKeys" :key="key" class="badge">{{ permissionLabels[key] }}</span></div>
        <p v-else class="caption">对方暂未共享。</p>
        <RouterLink class="text-action" :to="{ name: 'friend-diary', params: { id: friend.id } }">查看好友手账</RouterLink>
      </aside>
    </div>
    <ModalSurface :open="confirming" title="停止全部共享" @close="confirming = false">
      <p>{{ friend?.nickname }}将无法再在演示视图中查看你共享的数据。</p>
      <div class="toolbar"><button class="button button-danger" @click="revoke">确认停止共享</button><button class="button" @click="confirming = false">取消</button></div>
    </ModalSurface>
  </div>
</template>

<style scoped>
.permission-layout { display: grid; grid-template-columns: minmax(0, 1.55fr) minmax(0, 1fr); gap: calc(var(--space-unit) * 7.2); align-items: start; }
header { display: flex; gap: calc(var(--space-unit) * 4.8); align-items: center; margin-bottom: calc(var(--space-unit) * 5.2); }
h2 { font: 700 clamp(1.08rem, 2vw, 1.4rem)/1.3 var(--font-serif); }
.permission-row { display: flex; align-items: center; justify-content: space-between; gap: calc(var(--space-unit) * 6.4); min-height: 3.65rem; padding: calc(var(--space-unit) * 4.4) 0; border-top: 1px solid var(--color-line); cursor: pointer; }
.permission-row span { display: grid; gap: calc(var(--space-unit) * 1.04); }
.permission-row strong { font-size: .94rem; }
.permission-row small { color: var(--color-muted); font-size: .8rem; }
.switch-input { appearance: none; position: relative; width: 2.72rem; height: 1.55rem; border-radius: var(--radius-pill); background: var(--color-control-off); border: 1px solid var(--color-control-line); flex: none; cursor: pointer; transition: background .18s; }
.switch-input::after { content: ""; position: absolute; width: 1.08rem; height: 1.08rem; border-radius: var(--radius-round); background: var(--color-sheet); left: .18rem; top: .15rem; box-shadow: var(--shadow-control); transition: transform .18s; }
.switch-input:checked { background: var(--color-sage-deep); border-color: var(--color-sage-deep); }
.switch-input:checked::after { transform: translateX(1.14rem); }
.permission-actions { margin-top: calc(var(--space-unit) * 4.4); }
.outgoing > p { margin-top: calc(var(--space-unit) * 5.2); }
.incoming { background: var(--color-leaf-pale); }
@media (max-width: 670px) { .permission-layout { grid-template-columns: minmax(0, 1fr); } }
</style>
