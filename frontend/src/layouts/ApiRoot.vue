<script setup lang="ts">
import { computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppShell from './AppShell.vue'
import { useAuth } from '../stores/auth'
import type { User } from '../types/domain'

const auth = useAuth()
const route = useRoute()
const router = useRouter()
const account = computed<User | undefined>(() => {
  const user = auth.currentUser
  return user ? { id: user.public_id, nickname: user.nickname, initials: Array.from(user.nickname)[0] ?? '食', tone: 'sage' } : undefined
})

watch(() => auth.isAuthenticated, signedIn => {
  if (!signedIn && route.meta.requiresAuth) void router.replace({ name: 'login' })
})
</script>

<template>
  <main v-if="auth.isInitializing && !route.name" class="session-loading" aria-live="polite">正在打开 FoodDiary…</main>
  <AppShell v-else-if="route.meta.requiresAuth && account" :key="account.id" :account="account" />
  <RouterView v-else-if="!route.meta.requiresAuth" />
</template>

<style scoped>
.session-loading { margin: 4rem auto; text-align: center; color: var(--color-muted); }
</style>
