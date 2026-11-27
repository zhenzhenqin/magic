<script setup lang="ts">
import { ArrowLeft, HandHeart, LockKeyhole } from 'lucide-vue-next'
import { computed, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { sharingFields, useSharingApi } from '../api/sharingRepository'
import type { Friend, HistoryScope, ShareFlags, ShareKey } from '../api/sharingRepository'
import ModalSurface from '../components/ModalSurface.vue'
import { useApiDay } from '../composables/useApiDay'
import { usePrivateQuery } from '../composables/usePrivateQuery'
import { authMessage } from '../stores/auth'
import { shiftDay } from '../utils/dates'

const route = useRoute()
const router = useRouter()
const api = useSharingApi()
const { today } = useApiDay()
const id = computed(() => String(route.params.friendId ?? ''))
const info = usePrivateQuery(() => id.value, (key, signal) => key ? api.sharing(key, signal) : Promise.resolve(undefined))
const { current: friend } = info
const keys = Object.keys(sharingFields) as ShareKey[]
const flags = reactive(Object.fromEntries(keys.map(key => [key, false])) as ShareFlags)
const scope = ref<HistoryScope>('today')
const scopeDirty = ref(false)
const message = ref('')
const error = ref('')
const busy = ref(false)
const confirmation = ref<'history' | 'stop' | 'remove'>()
const historyOptions = { today: '从今天开始', week: '最近七天', month: '最近三十天', all: '全部历史' }
const historyExplanation = computed(() => scope.value === 'all' ? '对方可以查看全部符合权限的日期。'
  : '对方可查看 ' + shiftDay(today.value, { today: 0, week: -6, month: -29 }[scope.value]) + ' 及之后符合权限的记录。')

function sync(value: Friend | undefined) {
  if (!value) return
  Object.assign(flags, value.outgoing.permissions)
  scope.value = value.outgoing.history_scope
  scopeDirty.value = false
}
watch(friend, sync, { immediate: true })
function available(key: ShareKey) {
  if (key === 'records' || key === 'catalog') return true
  if (key === 'calories' || key === 'nutrition' || key === 'notes') return flags.records
  return flags.records || flags.catalog
}
function change(key: ShareKey, checked: boolean) {
  flags[key] = checked
  keys.filter(item => !available(item)).forEach(item => { flags[item] = false })
  if (!flags.history) { scope.value = 'today'; scopeDirty.value = false }
}
async function perform(action: 'save' | 'stop' | 'remove') {
  const item = friend.value
  if (!item || busy.value) return
  busy.value = true
  error.value = message.value = ''
  try {
    if (action === 'remove') {
      await api.remove(id.value, item.relationship_id)
      await router.push({ name: 'friends' })
    } else {
      const result = action === 'stop'
        ? await api.stop(id.value, item.relationship_id, item.outgoing.version)
        : await api.save(id.value, item.relationship_id, item.outgoing.version, { ...flags },
          scopeDirty.value && flags.history ? scope.value : undefined)
      friend.value = result
      sync(result)
      message.value = action === 'stop' ? '已停止向对方共享。' : '共享设置已保存。'
    }
  } catch (failure) {
    error.value = authMessage(failure)
  } finally {
    confirmation.value = undefined
    busy.value = false
  }
}
function save() {
  if (flags.history && friend.value && friend.value.outgoing.history_scope !== 'today'
    && keys.some(key => flags[key] && !friend.value?.outgoing.permissions[key])) scopeDirty.value = true
  if (flags.history && scopeDirty.value && scope.value !== 'today') confirmation.value = 'history'
  else void perform('save')
}
function preset() {
  keys.forEach(key => { flags[key] = ['records', 'names', 'stickers'].includes(key) })
  scope.value = 'today'
  scopeDirty.value = false
}
</script>

<template>
  <div class="sharing-page">
    <RouterLink class="text-action" :to="{ name: 'friends' }"><ArrowLeft aria-hidden="true" /> 返回饭搭子</RouterLink>
    <header><h1>共享设置</h1><p v-if="friend" class="caption">与 {{ friend.person.nickname }} 分享的内容</p></header>
    <p v-if="info.error.value" class="form-error" role="alert">{{ info.error.value }}</p>
    <p v-else-if="!friend" role="status">正在读取共享设置…</p>
    <div v-else class="permissions-layout">
      <section class="permission-paper form-stack" aria-label="我分享给对方">
        <div class="permission-heading">
          <h2><HandHeart aria-hidden="true" /> 我分享给对方</h2>
          <button class="text-action" type="button" :disabled="busy" @click="preset">使用推荐预设</button>
        </div>
        <label v-for="key in keys" :key="key" class="permission-row">
          <span><strong>{{ sharingFields[key].label }}</strong><small>{{ sharingFields[key].help }}</small></span>
          <input type="checkbox" :checked="flags[key]" :disabled="!available(key) || busy"
            @change="change(key, ($event.target as HTMLInputElement).checked)" />
        </label>
        <label v-if="flags.history" class="field">共享历史范围
          <select v-model="scope" @change="scopeDirty = true">
            <option v-for="(label, value) in historyOptions" :key="value" :value="value">{{ label }}</option>
          </select>
        </label>
        <p class="caption" data-test="outgoing-range">
          {{ friend.outgoing.granted_at ? (friend.outgoing.history_start ? '当前起点 ' + friend.outgoing.history_start : '当前开放全部历史') : '当前未共享。' }}
          起点按你的用餐本地日期计算，授权当天较早的记录也包含在内。
        </p>
        <p v-if="error" class="form-error" role="alert">{{ error }} <button type="button" class="text-action" @click="info.reload()">重新读取</button></p>
        <p v-if="message" class="caption" role="status">{{ message }}</p>
        <div class="toolbar">
          <button type="button" class="button button-primary" :disabled="busy" @click="save">保存授权</button>
          <button type="button" class="button" :disabled="busy || !friend.outgoing.granted_at" @click="confirmation = 'stop'">全部停止共享</button>
        </div>
        <p class="caption">撤销会拦截后续读取。对方之前保存的照片、截图和已在传输的内容可能仍可查看。</p>
      </section>
      <aside class="permission-paper form-stack" aria-label="对方分享给我">
        <h2><LockKeyhole aria-hidden="true" /> 对方分享给我</h2>
        <p v-if="!friend.incoming.granted_at" class="caption">对方尚未开放任何共享内容。</p>
        <ul v-else>
          <li v-for="key in keys.filter(key => friend?.incoming.permissions[key])" :key="key">{{ sharingFields[key].label }}</li>
        </ul>
        <p v-if="friend.incoming.granted_at" class="caption">{{ friend.incoming.history_start ? '从 ' + friend.incoming.history_start + ' 开始' : '全部历史' }}</p>
        <button type="button" class="button button-danger" :disabled="busy" @click="confirmation = 'remove'">解除好友</button>
      </aside>
    </div>
    <ModalSurface :open="!!confirmation" :title="confirmation === 'history' ? '确认扩大历史范围' : confirmation === 'remove' ? '解除好友' : '停止共享'" @close="!busy && (confirmation = undefined)">
      <p>{{ confirmation === 'history' ? historyExplanation : confirmation === 'remove' ? '双方的共享权限会立即失效。重新添加后需要重新授权。' : '停止后，对方发起的新请求将无法读取你的共享内容。' }}</p>
      <div class="toolbar">
        <button type="button" :disabled="busy" class="button button-primary"
          @click="perform(confirmation === 'history' ? 'save' : confirmation === 'remove' ? 'remove' : 'stop')">
          {{ confirmation === 'history' ? '确认共享范围' : confirmation === 'remove' ? '确认解除' : '确认停止共享' }}
        </button>
        <button type="button" :disabled="busy" class="button" @click="confirmation = undefined">取消</button>
      </div>
    </ModalSurface>
  </div>
</template>

<style scoped>
.sharing-page { max-width: 61rem; margin: auto; }
header { margin: .45rem 0 1rem; }
h1 { font: 700 clamp(1.65rem, 6vw, 2.75rem) var(--font-serif); }
h2 { display: flex; align-items: center; gap: .4rem; font: 600 1.23rem var(--font-hand); color: var(--diary-ink-soft); }
h2 svg { width: 1.1rem; }
.permissions-layout { display: grid; grid-template-columns: minmax(0, 2fr) minmax(12rem, 1fr); gap: .85rem; align-items: start; }
.permission-paper { padding: clamp(.9rem, 3vw, 1.55rem); background: var(--color-sheet); border: 1px solid var(--color-line); border-radius: .6rem 1.35rem 1.35rem .6rem; }
.permission-heading, .permission-row { display: flex; align-items: center; justify-content: space-between; gap: .55rem; }
.permission-row { padding: .4rem 0; border-bottom: 1px solid var(--color-line); }
.permission-row small { display: block; margin-top: .16rem; font-size: .76rem; color: var(--color-muted); }
.permission-row input { width: 1.16rem; height: 1.16rem; accent-color: #111; flex: none; margin: .45rem; }
.permission-heading button { font-size: .78rem; }
aside li { padding: .26rem 0; }
@media (max-width: 690px) { .permissions-layout { grid-template-columns: 1fr; } }
</style>
