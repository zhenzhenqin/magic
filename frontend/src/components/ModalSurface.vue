<script setup lang="ts">
import { X } from 'lucide-vue-next'
import { nextTick, onBeforeUnmount, ref, useId, watch } from 'vue'

const props = defineProps<{ open: boolean; title: string }>()
const emit = defineEmits<{ close: [] }>()
const dialog = ref<HTMLDialogElement>()
const titleId = useId()
let opener: HTMLElement | null = null
watch(() => props.open, async open => {
  await nextTick()
  if (props.open !== open || !dialog.value) return
  if (open && !dialog.value.open) {
    opener = document.activeElement instanceof HTMLElement ? document.activeElement : null
    dialog.value.showModal()
  } else if (!open && dialog.value.open) {
    dialog.value.close()
    opener?.focus()
  }
}, { immediate: true })
onBeforeUnmount(() => dialog.value?.close())
</script>

<template>
  <Teleport to="body">
    <dialog ref="dialog" class="modal paper-panel" :aria-labelledby="titleId" @cancel.prevent="emit('close')" @click.self="emit('close')">
      <section class="modal-content">
        <header>
          <h2 :id="titleId">{{ title }}</h2>
          <button class="icon-button button-quiet" aria-label="关闭弹窗" autofocus @click="emit('close')"><X /></button>
        </header>
        <slot />
      </section>
    </dialog>
  </Teleport>
</template>

<style scoped>
.modal { width: min(31rem, calc(100% - 1.6rem)); max-height: min(45rem, calc(100dvh - 2rem)); margin: auto; padding: 0; color: var(--color-ink); overflow: auto; }
.modal::backdrop { background: var(--color-backdrop); }
.modal-content { padding: calc(var(--space-unit) * 9.6); display: grid; gap: calc(var(--space-unit) * 6.4); }
header { display: flex; align-items: center; justify-content: space-between; gap: calc(var(--space-unit) * 4); }
h2 { font: 700 1.6rem/1.3 var(--font-serif); }
</style>
