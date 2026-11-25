<script setup lang="ts">
import { Utensils } from 'lucide-vue-next'
import { computed } from 'vue'

const props = defineProps<{ id?: string; name?: string; decorative?: boolean }>()
const stickers = import.meta.glob<string>('../assets/food/*.webp', { eager: true, query: '?url', import: 'default' })
const path = computed(() => stickers['../assets/food/' + props.id + '.webp'])
</script>

<template>
  <span class="sticker" :aria-hidden="decorative || undefined">
    <img v-if="path" :src="path" :alt="decorative ? '' : name ?? '食物贴纸'" decoding="async" draggable="false" />
    <span v-else class="sticker-empty" :class="{ 'sticker-private': !id }"><Utensils aria-hidden="true" /></span>
  </span>
</template>

<style scoped>
.sticker { display: grid; place-items: center; width: 100%; height: 100%; min-width: 0; min-height: 0; position: relative; pointer-events: none; }
.sticker img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: contain; filter: drop-shadow(var(--drop-shadow-sticker)); }
.sticker-empty { display: grid; place-items: center; width: 60%; height: 60%; min-height: 1.65rem; border: 1px dashed var(--color-control-line); border-radius: var(--radius-round); color: var(--color-sage-deep); background: var(--color-leaf-selected); }
.sticker-empty svg { width: 32%; min-width: 1rem; max-width: 1.65rem; stroke-width: 1.4; }
.sticker-private { opacity: .7; }
</style>
