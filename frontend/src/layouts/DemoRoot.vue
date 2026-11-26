<script setup lang="ts">
import AppShell from './AppShell.vue'
import { useDiary } from '../stores/diary'

const diary = useDiary()
</script>

<template>
  <AppShell :account="diary.account" demo />
</template>
