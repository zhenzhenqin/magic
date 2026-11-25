<script setup lang="ts">
import type { User } from '../types/domain'

defineProps<{ user: User; size?: 'small' | 'large' }>()
</script>

<template>
  <span class="avatar" :class="[user.tone, size]" aria-hidden="true">{{ user.initials }}</span>
</template>

<style scoped>
.avatar { display: inline-grid; place-items: center; width: 3rem; height: 3rem; border-radius: var(--radius-round); font: 700 1.1rem var(--font-serif); flex: none; color: var(--color-text-strong); background: var(--color-leaf); }
.avatar.peach { color: var(--color-terracotta); background: var(--color-peach-soft); }
.avatar.butter { color: var(--color-earth); background: var(--color-butter); }
.avatar.small { width: 2.15rem; height: 2.15rem; font-size: .92rem; }
.avatar.large { width: 4.15rem; height: 4.15rem; font-size: 1.75rem; }
</style>
