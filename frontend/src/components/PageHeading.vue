<script setup lang="ts">
defineProps<{ title: string; subtitle?: string }>()
</script>

<template>
  <header class="page-heading">
    <div>
      <slot name="context" />
      <h1>{{ title }}</h1>
      <p v-if="subtitle">{{ subtitle }}</p>
    </div>
    <div v-if="$slots.default" class="toolbar"><slot /></div>
  </header>
</template>

<style scoped>
.page-heading { display: flex; justify-content: space-between; align-items: end; flex-wrap: wrap; gap: calc(var(--space-unit) * 5.6) calc(var(--space-unit) * 9.6); margin-bottom: calc(var(--space-unit) * 11.6); }
h1 { font: 700 clamp(2.15rem, 4.5vw, 3.6rem)/1.15 var(--font-serif); letter-spacing: -.055em; }
p { color: var(--color-muted); margin-top: calc(var(--space-unit) * 4.16); line-height: 1.65; }
@media (max-width: 580px) {
  .page-heading { align-items: start; margin-bottom: calc(var(--space-unit) * 9.2); }
  .page-heading p { font-size: .9rem; }
}
</style>
