<script setup lang="ts">
import { BookOpen, Camera, HeartHandshake, LibraryBig, Sprout, UserRound } from 'lucide-vue-next'
import { useRoute } from 'vue-router'
import AvatarBadge from '../components/AvatarBadge.vue'
import DiaryBrand from '../components/DiaryBrand.vue'
import type { User } from '../types/domain'

defineProps<{ account: User; demo?: boolean }>()
const route = useRoute()
const navigation = [
  { label: '手账', to: '/', icon: BookOpen, section: ['/', '/calendar'] },
  { label: '图鉴', to: '/catalog', icon: LibraryBig, section: ['/catalog'] },
  { label: '拍照', to: '/capture', icon: Camera, section: ['/capture'] },
  { label: '饭搭子', to: '/friends', icon: HeartHandshake, section: ['/friends'] },
  { label: '我的', to: '/me', icon: UserRound, section: ['/me'] },
]
const isActive = (section: string[]) => section.some(path => route.path === path || (path !== '/' && route.path.startsWith(path + '/')))
</script>

<template>
  <a href="#main" class="skip-link">跳转到主要内容</a>
  <div class="app-frame" :class="{ 'api-theme': !demo }">
    <aside class="rail">
      <RouterLink to="/" class="brand" aria-label="FoodDiary 美食手账">
        <DiaryBrand v-if="!demo" />
        <template v-else><span class="brand-mark"><Sprout aria-hidden="true" /></span><span>FoodDiary<small>美 食 手 账</small></span></template>
      </RouterLink>
      <nav class="navigation" aria-label="主导航">
        <RouterLink v-for="item in navigation" :key="item.to" :to="!demo && item.to === '/capture' ? { name: 'capture', query: { camera: '1' } } : item.to"
          class="nav-link" :class="{ 'nav-active': isActive(item.section), 'nav-camera': item.to === '/capture', 'nav-secondary': item.to === '/friends' || item.to === '/me' }"
          :aria-current="isActive(item.section) ? 'page' : undefined">
          <span class="nav-icon" aria-hidden="true">
            <i v-if="!demo && item.to === '/capture'" class="capture-mark"></i>
            <component v-else :is="item.icon" />
          </span>
          <span>{{ item.label }}</span>
        </RouterLink>
        <div v-if="!demo" class="mobile-tools mobile-secondary">
          <RouterLink to="/friends" class="mobile-account" aria-label="饭搭子"><HeartHandshake aria-hidden="true" /><span>饭搭子</span></RouterLink>
          <RouterLink to="/me" class="mobile-account" aria-label="我的"><UserRound aria-hidden="true" /><span>我的</span></RouterLink>
        </div>
      </nav>
      <RouterLink to="/me" class="rail-account" :aria-label="demo ? '当前演示账号' : '当前账号'">
        <AvatarBadge :user="account" size="small" />
        <span><strong>{{ account.nickname }}</strong><small>{{ demo ? '演示账号' : '个人账号' }}</small></span>
      </RouterLink>
    </aside>
    <header class="mobile-header">
      <RouterLink to="/" class="brand" aria-label="FoodDiary 美食手账">
        <DiaryBrand v-if="!demo" />
        <template v-else><span class="brand-mark"><Sprout aria-hidden="true" /></span><span>FoodDiary</span></template>
      </RouterLink>
      <RouterLink v-if="demo" to="/me" class="mobile-account" :aria-label="'演示账号 ' + account.nickname">
        <AvatarBadge :user="account" size="small" />
      </RouterLink>
    </header>
    <main id="main" class="workspace" tabindex="-1">
      <div class="page-shell">
        <RouterView />
      </div>
    </main>
  </div>
</template>

<style scoped>
.skip-link { position: fixed; top: .4rem; left: .4rem; z-index: 6; padding: calc(var(--space-unit) * 4.8); border-radius: var(--radius-small); background: var(--color-sheet); transform: translateY(-200%); }
.skip-link:focus { transform: none; }
.app-frame { min-height: 100dvh; }
.rail { width: var(--rail-width); padding: calc(var(--space-unit) * 16.8) calc(var(--space-unit) * 10.4) calc(var(--space-unit) * 12.8); position: fixed; inset: 0 auto 0 0; background: var(--color-rail); border-right: 1px solid var(--color-line); display: flex; flex-direction: column; z-index: 2; }
.brand { display: inline-flex; align-items: center; gap: calc(var(--space-unit) * 5.6); align-self: start; font: 700 1.55rem/.98 var(--font-editorial); letter-spacing: -.045em; white-space: nowrap; }
.brand-mark { width: 2.4rem; height: 2.4rem; display: grid; flex: none; place-items: center; border-radius: var(--radius-brand); background: var(--color-sage-deep); color: var(--color-sheet); transform: rotate(-6deg); }
.brand-mark svg { width: 1.45rem; height: 1.45rem; stroke-width: 1.6; transform: rotate(6deg); }
.brand small { display: block; margin-top: calc(var(--space-unit) * 2.8); color: var(--color-muted); font: 600 .69rem/1.2 var(--font-sans); letter-spacing: .04em; }
.navigation { display: grid; gap: calc(var(--space-unit) * 3.04); margin-top: calc(var(--space-unit) * 25.2); }
.nav-link { display: flex; align-items: center; gap: calc(var(--space-unit) * 7.2); padding: calc(var(--space-unit) * 2) calc(var(--space-unit) * 6.4); min-height: 3.05rem; border-radius: var(--radius-small); color: var(--color-muted); font-size: .95rem; font-weight: 650; transition: background .18s; }
.nav-link:hover { background: var(--color-canvas-hover); color: var(--color-ink); }
.nav-icon { display: grid; place-items: center; }
.nav-icon svg { width: 1.2rem; height: 1.2rem; stroke-width: 1.65; }
.nav-active { color: var(--color-sage-deep); background: var(--color-leaf-selected); }
.nav-camera .nav-icon { color: var(--color-sage-deep); }
.rail-account { display: flex; align-items: center; gap: calc(var(--space-unit) * 5.2); border-top: 1px solid var(--color-line); padding: calc(var(--space-unit) * 7.2) calc(var(--space-unit) * 2) 0; margin-top: auto; }
.rail-account strong, .rail-account small { display: block; font-size: .875rem; }
.rail-account small { font-size: .75rem; color: var(--color-muted); }
.workspace { margin-left: var(--rail-width); }
.page-shell { width: 100%; max-width: var(--page-width); margin-inline: auto; padding: calc(var(--space-unit) * 20.8) clamp(calc(var(--space-unit) * 12), 4.1vw, calc(var(--space-unit) * 35.2)) calc(var(--space-unit) * 24); }
.mobile-header { display: none; }
.mobile-secondary { display: none; }
.api-theme .brand-mark { transform: none; border-radius: .7rem .7rem .7rem .2rem; }
.api-theme .brand-mark svg { transform: none; }
.capture-mark { position: relative; display: block; width: 1.04rem; height: .77rem; border: 1.5px solid currentColor; border-radius: .27rem .27rem .34rem .27rem; }
.capture-mark::before { position: absolute; content: ""; inset: 50% auto auto 50%; width: .37rem; height: .37rem; border: 1.3px solid currentColor; border-radius: 50%; transform: translate(-50%,-50%); }
.capture-mark::after { position: absolute; content: ""; width: .31rem; border-top: 1.5px solid currentColor; left: .11rem; top: -.21rem; }
.api-theme .workspace .page-shell { max-width: 66rem; }
@media (min-width: 901px) {
  .api-theme .rail { position: sticky; inset: 0 0 auto; display: flex; flex-direction: row; align-items: center; gap: 1.35rem; width: 100%; padding: .55rem max(2.1rem, calc((100vw - 70rem) / 2)); border: 0; border-bottom: 1px solid var(--color-line); background: var(--color-paper); }
  .api-theme .brand { align-self: center; }
  .api-theme .navigation { display: flex; align-items: center; gap: .35rem; margin: 0 auto; }
  .api-theme .nav-link { padding-inline: .65rem; min-height: var(--tap-size); gap: .4rem; font-size: .87rem; border-bottom: 2px solid transparent; border-radius: 0; }
  .api-theme .nav-active { background: transparent; border-color: var(--color-sage); }
  .api-theme .rail-account { padding: 0; border: 0; margin: 0; }
  .api-theme .rail-account small { display: none; }
  .api-theme .workspace { margin-left: 0; }
}
@media (max-width: 900px) {
  .rail { display: contents; }
  .rail > .brand, .rail-account { display: none; }
  .workspace { margin: 0; }
  .mobile-header { display: flex; justify-content: space-between; align-items: center; min-height: 4.2rem; padding: max(calc(var(--space-unit) * 5.2), env(safe-area-inset-top)) max(calc(var(--space-unit) * 9.2), env(safe-area-inset-right)) calc(var(--space-unit) * 4.4) max(calc(var(--space-unit) * 9.2), env(safe-area-inset-left)); }
  .mobile-header .brand { align-self: center; font-size: 1.28rem; }
  .mobile-header .brand-mark { width: 1.95rem; height: 1.95rem; }
  .mobile-header .brand-mark svg { width: 1.16rem; height: 1.16rem; }
  .mobile-account { display: grid; place-items: center; min-width: var(--tap-size); min-height: var(--tap-size); }
  .navigation { position: fixed; z-index: 4; inset: auto 0 0; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 0; margin: 0; min-height: var(--mobile-nav-height); align-items: center; padding: calc(var(--space-unit) * 2) max(calc(var(--space-unit) * 2.8), env(safe-area-inset-right)) max(calc(var(--space-unit) * 2.8), env(safe-area-inset-bottom)) max(calc(var(--space-unit) * 2.8), env(safe-area-inset-left)); border-top: 1px solid var(--color-line); background: var(--color-sheet); }
  .nav-link { min-width: 0; flex-direction: column; justify-content: center; gap: calc(var(--space-unit) * 1.76); padding: calc(var(--space-unit) * 2); font-size: .72rem; line-height: 1.2; white-space: nowrap; margin-inline: calc(var(--space-unit) * 0.96); }
  .nav-active { background: transparent; font-weight: 800; }
  .nav-active .nav-icon { background: var(--color-leaf); border-radius: var(--radius-pill); padding: calc(var(--space-unit) * 1.92) calc(var(--space-unit) * 4.24); }
  .nav-camera .nav-icon { color: var(--color-sheet); background: var(--color-sage-deep); padding: calc(var(--space-unit) * 4.4) calc(var(--space-unit) * 5.2); border-radius: var(--radius-card); margin-top: -calc(var(--space-unit) * 6.8); }
  .nav-camera .nav-icon svg { width: 1.25rem; height: 1.25rem; }
  .page-shell { padding: calc(var(--space-unit) * 8) max(calc(var(--space-unit) * 8.8), env(safe-area-inset-right)) calc(var(--mobile-nav-height) + env(safe-area-inset-bottom) + calc(var(--space-unit) * 10.4)) max(calc(var(--space-unit) * 8.8), env(safe-area-inset-left)); }
  .api-theme .mobile-header { position: sticky; top: 0; z-index: 3; background-color: var(--color-paper); padding-inline: max(.95rem, env(safe-area-inset-left)) max(.95rem, env(safe-area-inset-right)); border-bottom: 1px solid var(--color-line); }
  .api-theme .mobile-secondary { display: flex; position: fixed; top: max(.7rem, env(safe-area-inset-top)); right: max(.95rem, env(safe-area-inset-right)); gap: .4rem; align-items: center; }
  .api-theme .mobile-account { display: inline-flex; align-items: center; justify-content: center; gap: .3rem; font-size: .72rem; padding-inline: .2rem; }
  .mobile-account svg { width: 1.05rem; height: 1.05rem; stroke-width: 1.6; }
  .api-theme .navigation { grid-template-columns: 1fr 1.2fr 1fr; background: var(--color-paper); }
  .api-theme .nav-secondary { display: none; }
  .api-theme .nav-camera { order: 2; min-height: 3.35rem; width: min(100%, 7.4rem); margin-inline: auto; color: var(--color-sheet); background: var(--color-sage-deep); border-radius: .85rem; flex-direction: row; gap: .5rem; }
  .api-theme .nav-camera .nav-icon { background: none; padding: 0; margin: 0; }
  .api-theme .nav-camera:active { transform: scale(.94); }
  .api-theme .nav-link[href="/catalog"] { order: 3; }
  .api-theme .page-shell { padding-top: .65rem; }
}
</style>
