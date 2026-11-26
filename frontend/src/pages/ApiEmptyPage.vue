<script setup lang="ts">
import { BookOpen, Leaf } from 'lucide-vue-next'
import { useRoute } from 'vue-router'
import PageHeading from '../components/PageHeading.vue'

const route = useRoute()
</script>

<template>
  <section>
    <PageHeading :title="String(route.meta.title)" />
    <div class="paper-panel empty-state fresh-page">
      <BookOpen v-if="route.name === 'diary'" aria-hidden="true" />
      <Leaf v-else aria-hidden="true" />
      <h2>{{ route.name === 'diary' ? '这一页还留白' : '这一页正在准备' }}</h2>
      <p>{{ route.name === 'diary' ? '饮食记录将在后续阶段开放。' : '此功能将在后续阶段开放。' }}</p>
    </div>
  </section>
</template>

<style scoped>
.fresh-page { min-height: 15rem; align-content: center; background: var(--color-sheet); background-image: var(--paper-texture); }
h2 { font: 700 1.45rem var(--font-serif); }
</style>
