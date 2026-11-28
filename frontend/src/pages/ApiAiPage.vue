<script setup lang="ts">
import { ArrowLeft, ArrowUpRight, Eye, EyeOff } from 'lucide-vue-next'
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { personalAi } from '../api/personalAi'
import type { Connection } from '../api/personalAi'
import { authMessage } from '../stores/auth'

const api = personalAi()
const route = useRoute()
const state = ref<Connection>()
const key = ref('')
const visible = ref(false)
const limit = ref<number | ''>('')
const busy = ref(false)
const status = ref('')
const error = ref('')

async function run(work: () => Promise<void>) {
  if (busy.value) return
  busy.value = true
  status.value = error.value = ''
  try { await work() } catch (failure) { error.value = authMessage(failure) }
  finally { busy.value = false }
}

function apply(result: Connection) {
  state.value = result
  limit.value = result.daily_limit ?? ''
}

async function load() { apply(await api.read()) }
onMounted(() => run(load))
onBeforeUnmount(() => { key.value = ''; visible.value = false })

const connect = () => run(async () => {
  const candidate = key.value
  key.value = ''
  visible.value = false
  apply(await api.connect(candidate))
  status.value = '测试连接已建立。'
})
const verify = () => run(async () => {
  const balance = await api.balance()
  status.value = balance.simulated ? '模拟余额接口验证通过，可用性为测试数据。' : '余额查询已完成。'
})
const disconnect = () => run(async () => {
  await api.disconnect()
  await load()
  status.value = '当前会话的连接已清除。'
})
const save = () => run(async () => {
  apply(await api.preferences({ daily_limit: limit.value === '' ? null : limit.value }))
  status.value = '识别次数设置已保存。'
})
</script>

<template>
  <div class="editorial-settings">
    <header class="settings-heading"><RouterLink :to="{ name: route.query.welcome ? 'diary' : 'profile' }" class="text-action"><ArrowLeft aria-hidden="true" /> 返回</RouterLink><h1>AI 助手</h1></header>
    <section class="settings-group">
      <h2>{{ route.query.welcome ? '连接你的识别账号' : 'DeepSeek 连接' }}</h2>
      <p>你可以只用拍照、贴纸和手动记录。使用 AI 识别时，你确认的照片会发送至 DeepSeek，推理费用由你自己的 DeepSeek 账户承担。</p>
      <a href="https://platform.deepseek.com/" target="_blank" rel="noopener noreferrer" class="text-action">申请 DeepSeek API Key <ArrowUpRight aria-hidden="true" /></a>
      <p v-if="state?.mode === 'disabled'" class="caption">真实连接等待平台确认授权条件。当前无法提交真实 API Key。</p>
      <template v-else-if="state">
        <p><strong>{{ state.connected ? '测试连接已建立' : '当前会话未连接' }}</strong><span v-if="state.expires_at" class="caption"> · {{ new Date(state.expires_at).toLocaleTimeString() }} 到期</span></p>
        <form class="form-stack" @submit.prevent="connect">
          <label for="personal-ai-key" class="field">测试 API Key</label>
          <div class="key-input">
            <input id="personal-ai-key" v-model="key" :type="visible ? 'text' : 'password'" maxlength="88" autocomplete="off"
              spellcheck="false" autocapitalize="none" placeholder="fd-test-…" required />
            <button type="button" class="icon-button button-quiet" :aria-label="visible ? '隐藏密钥' : '显示密钥'" @click="visible = !visible">
              <EyeOff v-if="visible" aria-hidden="true" /><Eye v-else aria-hidden="true" />
            </button>
          </div>
          <div class="toolbar">
            <button class="button button-primary" :disabled="busy">{{ state.connected ? '替换临时连接' : '临时连接' }}</button>
            <button v-if="state.connected" type="button" class="button" :disabled="busy" @click="verify">验证并查询余额</button>
            <button v-if="state.connected" type="button" class="text-action" :disabled="busy" @click="disconnect">清除连接</button>
          </div>
        </form>
      </template>
      <p class="caption">临时连接随会话结束或授权到期。加密长期保存尚未开放。清除密钥后，已发送给供应商的请求仍可能完成并计费。</p>
    </section>
    <section v-if="state" class="settings-group">
      <h2>FoodDiary 内的使用记录</h2>
      <dl class="usage-sheet">
        <div><dt>今日调用</dt><dd>{{ state.today }}</dd></div>
        <div><dt>累计调用</dt><dd>{{ state.total }}</dd></div>
        <div><dt>输入 Token</dt><dd>{{ state.input_tokens ?? '暂无记录' }}</dd></div>
        <div><dt>输出 Token</dt><dd>{{ state.output_tokens ?? '暂无记录' }}</dd></div>
        <div v-if="state.unknown"><dt>结果未知</dt><dd>{{ state.unknown }}</dd></div>
      </dl>
      <p class="caption">{{ state.mode === 'simulation' ? '当前记录来自本地模拟。' : '' }}平台余额与账单以 DeepSeek 为准。这里的次数限制只适用于 FoodDiary。</p>
      <form class="form-stack" @submit.prevent="save">
        <label class="field limit">个人每日调用次数<input v-model.number="limit" type="number" min="0" :max="state.maximum_daily_limit" :placeholder="String(state.maximum_daily_limit)" /></label>
        <p class="caption">留空沿用服务上限。填写 0 可暂停识别。</p>
        <div><button class="button" :disabled="busy">保存次数设置</button></div>
      </form>
    </section>
    <p v-if="status" class="caption" role="status">{{ status }}</p><p v-if="error" class="form-error" role="alert">{{ error }}</p>
  </div>
</template>

<style scoped>
.key-input { position: relative; }
.key-input input { width: 100%; min-height: var(--tap-size); border: 1px solid var(--color-line); background: var(--color-sheet); border-radius: var(--radius-small); padding: .55rem 3rem .55rem .7rem; }
.key-input button { position: absolute; right: .15rem; top: 0; }
.usage-sheet { display: grid; grid-template-columns: repeat(auto-fit, minmax(7rem, 1fr)); gap: 1.2rem; }
.usage-sheet dt { color: var(--color-muted); font-size: .82rem; }
.usage-sheet dd { margin: .26rem 0 0; font: 500 1.25rem var(--font-hand); }
.limit { max-width: 15rem; }
</style>
