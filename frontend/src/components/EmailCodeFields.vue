<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import type { EmailProof, VerificationTicket } from '../api/authRepository'
import { authMessage } from '../stores/auth'

const props = withDefaults(defineProps<{ send: (email: string) => Promise<VerificationTicket>; maySend?: boolean }>(), { maySend: true })
const proof = defineModel<EmailProof>({ required: true })
const emailControl = ref<HTMLInputElement>()
const sending = ref(false)
const remaining = ref(0)
const feedback = ref('')
const error = ref(false)
let timer: ReturnType<typeof setInterval> | undefined
let generation = 0
let active = true

watch(() => proof.value.email, () => {
  generation++
  proof.value = { email: proof.value.email, request_id: '', code: '' }
  feedback.value = ''
})
onBeforeUnmount(() => { active = false; clearInterval(timer) })

function changeCode(code: string) {
  proof.value = { ...proof.value, code }
}

async function send() {
  if (!props.maySend || !emailControl.value?.reportValidity() || sending.value || remaining.value) return
  const email = proof.value.email
  const request = generation
  sending.value = true
  feedback.value = ''
  try {
    const ticket = await props.send(email)
    if (!active || request !== generation) return
    proof.value = { email, request_id: ticket.request_id, code: '' }
    error.value = false
    feedback.value = '验证码已发送，5 分钟内有效。'
    const until = Date.now() + ticket.resend_after * 1000
    remaining.value = ticket.resend_after
    clearInterval(timer)
    timer = setInterval(() => {
      remaining.value = Math.max(0, Math.ceil((until - Date.now()) / 1000))
      if (!remaining.value) clearInterval(timer)
    }, 250)
  } catch (failure) {
    if (active && request === generation) {
      feedback.value = authMessage(failure)
      error.value = true
    }
  } finally {
    sending.value = false
  }
}
</script>

<template>
  <div class="email-fields">
    <label class="field">邮箱地址<input ref="emailControl" :value="proof.email" type="email" maxlength="254" autocomplete="email"
      autocapitalize="none" required @input="proof = { ...proof, email: ($event.target as HTMLInputElement).value }" /></label>
    <div class="code-row">
      <label class="field">邮箱验证码<input :value="proof.code" inputmode="numeric" autocomplete="one-time-code"
        maxlength="6" pattern="[0-9]{6}" required @input="changeCode(($event.target as HTMLInputElement).value)" /></label>
      <button type="button" class="button" :disabled="!maySend || sending || remaining > 0" @click="send">
        {{ remaining ? remaining + ' 秒后重发' : sending ? '正在发送' : '发送验证码' }}
      </button>
    </div>
    <p v-if="feedback" :role="error ? 'alert' : 'status'" :class="error ? 'form-error' : 'caption'">{{ feedback }}</p>
  </div>
</template>

<style scoped>
.email-fields { display: grid; gap: 1rem; }
.code-row { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: .65rem; align-items: end; }
</style>
