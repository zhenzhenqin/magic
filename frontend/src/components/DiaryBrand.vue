<template>
  <span class="diary-brand">
    <svg viewBox="0 0 36 36" fill="none" aria-hidden="true">
      <path d="M7 7h19a3 3 0 0 1 3 3v19H11a4 4 0 0 1-4-4V7Z" fill="currentColor" opacity=".1" />
      <path d="M7 7h19a3 3 0 0 1 3 3v19H11a4 4 0 0 1-4-4V7Zm0 17h22m-16-8c1.9-3.8 7.8-4.1 10 0-2.1 3.8-7.8 4.1-10 0Z" stroke="currentColor" stroke-width="1.45" stroke-linecap="round" stroke-linejoin="round" />
      <path d="M18 16h.03" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
    </svg>
    <span>FoodDiary</span>
  </span>
</template>

<style scoped>
.diary-brand { display: inline-flex; align-items: center; gap: .55rem; font: 700 1.42rem/1 var(--font-editorial); letter-spacing: -.055em; white-space: nowrap; }
svg { flex: none; width: 2rem; height: 2rem; color: var(--color-sage-deep); }
</style>
