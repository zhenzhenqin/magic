<script setup lang="ts">
import { BookHeart, Copy, Search, UserRoundPlus } from 'lucide-vue-next'
import { computed, ref } from 'vue'
import { useSharingApi } from '../api/sharingRepository'
import type { Peer } from '../api/sharingRepository'
import ModalSurface from '../components/ModalSurface.vue'
import SharedPhoto from '../components/SharedPhoto.vue'
import { dateInTimezone } from '../composables/useApiDay'
import { usePrivateQuery } from '../composables/usePrivateQuery'
import { useSharingRefresh } from '../composables/useSharingRefresh'
import { authMessage, useAuth } from '../stores/auth'

const api = useSharingApi()
const auth = useAuth()
const adding = ref(false)
const input = ref('')
const target = ref<Peer>()
const busy = ref(false)
const error = ref('')
const notice = ref('')
const previewId = ref('')
const state = useSharingRefresh(() => { list.reload(); queue.reload(); preview.reload() })
const available = () => state.online.value && state.foreground.value
const list = usePrivateQuery(available, (active, signal) => active ? api.list(signal) : Promise.resolve(undefined))
const queue = usePrivateQuery(available, (active, signal) => active ? api.requests(signal) : Promise.resolve(undefined))
const { current: friends } = list
const { current: requests } = queue
const selectedFriend = computed(() => friends.value?.items.find(friend => friend.person.public_id === previewId.value))
const today = () => dateInTimezone(auth.preferences?.timezone ?? 'Asia/Shanghai')
const preview = usePrivateQuery(
  () => selectedFriend.value?.incoming.permissions.records && previewId.value, (id, signal) =>
    id ? api.meals(id, today(), 1, signal, 2) : Promise.resolve(undefined),
)
const statuses = { pending: '等待处理', accepted: '已接受', rejected: '已拒绝', cancelled: '已取消' }

async function copy() {
  if (!friends.value) return
  try {
    await navigator.clipboard.writeText(friends.value.me.public_id)
    notice.value = '公开 ID 已复制。'
  } catch { notice.value = '可以选择下方文字手动复制。' }
}
function close() { if (!busy.value) adding.value = false }
async function find() {
  if (busy.value) return
  target.value = undefined
  await perform(async () => { target.value = await api.lookup(input.value.trim().toLowerCase()) }, false)
}
async function send() {
  if (!target.value) return
  const id = target.value.public_id
  await perform(async () => {
    const item = await api.send(id)
    notice.value = item.direction === 'outgoing' ? '申请已发送。' : '对方已经发来申请，请在收到的申请里处理。'
    target.value = undefined
    input.value = ''
    adding.value = false
  })
}
async function perform(work: () => Promise<void>, reload = true) {
  if (busy.value) return
  busy.value = true
  error.value = notice.value = ''
  try {
    await work()
    if (reload) { list.reload(); queue.reload() }
  } catch (failure) {
    error.value = authMessage(failure)
  } finally { busy.value = false }
}
async function respond(id: string, action: 'accept' | 'reject' | 'cancel') {
  await perform(async () => {
    await api.respond(id, action)
    notice.value = action === 'accept' ? '已成为饭搭子。现在可以各自选择共享范围。' : '申请已更新。'
  })
}
</script>

<template>
  <div class="friends-page">
    <header class="friend-heading">
      <h1>饭搭子</h1>
      <button type="button" class="button button-primary" @click="adding = true; error = ''"><UserRoundPlus aria-hidden="true" /> 添加饭搭子</button>
    </header>
    <section class="friend-paper form-stack" aria-label="饭搭子">
      <p v-if="notice" class="caption" role="status">{{ notice }}</p>
      <p v-if="list.error.value || queue.error.value || (error && !adding)" class="form-error" role="alert">{{ list.error.value || queue.error.value || error }}</p>
      <p v-if="!state.online.value" role="status" class="caption">网络已断开，连接后重新读取饭搭子。</p>
      <section class="inbox" aria-labelledby="requests-heading">
        <h2 id="requests-heading">好友申请</h2>
        <p v-if="!requests?.length" class="caption">这里暂时没有好友申请。</p>
        <article v-for="request in requests" :key="request.id" class="person-row">
          <span class="initial" aria-hidden="true">{{ Array.from(request.person.nickname)[0] }}</span>
          <div class="person-copy"><strong>{{ request.person.nickname }}</strong><p class="caption">{{ request.direction === 'incoming' ? '收到的申请' : '发出的申请' }} · {{ statuses[request.status] }}</p></div>
          <div v-if="request.status === 'pending'" class="toolbar">
            <template v-if="request.direction === 'incoming'">
              <button type="button" class="button button-primary" :disabled="busy" @click="respond(request.id, 'accept')">接受</button>
              <button type="button" class="button" :disabled="busy" @click="respond(request.id, 'reject')">拒绝</button>
            </template>
            <button v-else type="button" class="button" :disabled="busy" @click="respond(request.id, 'cancel')">取消申请</button>
          </div>
        </article>
      </section>
      <div v-if="friends" class="public-id">
        <div><span class="caption">我的公开 ID</span><code>{{ friends.me.public_id }}</code></div>
        <button type="button" class="text-action" aria-label="复制我的公开 ID" @click="copy"><Copy aria-hidden="true" /> 复制</button>
      </div>
      <section class="people" aria-labelledby="friends-heading">
        <h2 id="friends-heading">我的饭搭子</h2>
        <div v-if="friends && !friends.items.length" class="empty-state"><BookHeart aria-hidden="true" /><p>找到饭搭子后，就能各自选择想分享的手账内容。</p></div>
        <article v-for="friend in friends?.items" :key="friend.relationship_id" class="friend-entry">
          <div class="person-row">
            <span class="initial" aria-hidden="true">{{ Array.from(friend.person.nickname)[0] }}</span>
            <div class="person-copy">
              <strong>{{ friend.person.nickname }}</strong>
              <p class="caption">{{ friend.incoming.permissions.records ? '已开放饮食手账' : '饮食手账暂未共享' }}</p>
            </div>
            <RouterLink class="button" :to="{ name: 'friend-sharing', params: { friendId: friend.person.public_id } }">共享设置</RouterLink>
          </div>
          <div class="toolbar friend-actions">
            <RouterLink class="text-action" :to="{ name: 'friend-diary', params: { friendId: friend.person.public_id } }">查看手账</RouterLink>
            <RouterLink class="text-action" :to="{ name: 'friend-catalog', params: { friendId: friend.person.public_id } }">查看图鉴</RouterLink>
            <RouterLink class="text-action" :to="{ name: 'friend-together', params: { friendId: friend.person.public_id } }">双人手账</RouterLink>
            <button v-if="friend.incoming.permissions.records" type="button" class="text-action" :aria-expanded="previewId === friend.person.public_id"
              @click="previewId = previewId === friend.person.public_id ? '' : friend.person.public_id">今日预览</button>
          </div>
          <div v-if="previewId === friend.person.public_id && preview.current.value" class="preview-strip">
            <template v-if="preview.current.value.items.length">
              <article v-for="entry in preview.current.value.items" :key="entry.id">
                <div v-if="entry.media?.length" class="preview-photo"><SharedPhoto :owner="friend.person.public_id" :media="entry.media[0]" :context="{ meal_id: entry.id }" /></div>
                <span>{{ entry.items?.map(item => item.food_name).filter(Boolean).join('、') || entry.local_time }}</span>
              </article>
            </template>
            <p v-else class="caption">今天暂无可查看的记录。</p>
          </div>
        </article>
      </section>
    </section>
    <ModalSurface :open="adding" title="添加饭搭子" @close="close">
      <form class="form-stack" @submit.prevent="find">
        <label class="field">好友的完整公开 ID<input v-model="input" maxlength="35" autocomplete="off" spellcheck="false" placeholder="fd_…" @input="target = undefined" /></label>
        <button type="submit" class="button button-primary" :disabled="busy || !/^fd_[a-f0-9]{32}$/i.test(input.trim())"><Search aria-hidden="true" /> 查找好友</button>
      </form>
      <p v-if="error" class="form-error" role="alert">{{ error }}</p>
      <div v-if="target" class="person-row">
        <span class="initial" aria-hidden="true">{{ Array.from(target.nickname)[0] }}</span>
        <strong class="person-copy">{{ target.nickname }}</strong>
        <button type="button" class="button" :disabled="busy" @click="send">发送好友申请</button>
      </div>
    </ModalSurface>
  </div>
</template>

<style scoped>
.friends-page { max-width: 49rem; margin: auto; }
.friend-heading { display: flex; align-items: center; justify-content: space-between; gap: .7rem; margin-bottom: 1rem; }
h1 { font: 700 clamp(1.65rem, 5vw, 2.35rem) var(--font-serif); }
h2 { font: 600 1.3rem var(--font-hand); color: var(--diary-ink-soft); margin-bottom: .45rem; }
.friend-paper { border-top: 1px solid var(--color-line); padding: 1rem 0; }
.public-id, .person-row { display: flex; align-items: center; gap: .55rem; flex-wrap: wrap; }
.public-id { justify-content: space-between; padding-block: .35rem; border-block: 1px solid var(--color-line); }
.public-id code { display: block; user-select: all; font-size: clamp(.66rem, 2.8vw, .83rem); overflow-wrap: anywhere; }
.initial { width: 2rem; height: 2rem; display: grid; place-items: center; flex: none; border-radius: .62rem; background: var(--color-leaf); color: var(--color-earth); font: 600 1rem var(--font-hand); }
.person-copy { flex: 1; min-width: min(8rem, 100%); overflow-wrap: anywhere; }
.person-row { padding-block: .4rem; }
.inbox article + article, .friend-entry + .friend-entry { border-top: 1px solid var(--color-line); }
.friend-entry { padding-bottom: .5rem; }
.friend-actions { justify-content: flex-start; }
.friend-actions .text-action { font-size: .85rem; }
.preview-strip { display: flex; gap: .8rem; padding-block: .4rem; font-family: var(--font-hand); }
.preview-photo { width: 5.8rem; height: 4.5rem; }
</style>
