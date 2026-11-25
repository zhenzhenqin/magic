import { createRouter, createWebHistory } from 'vue-router'

export const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  scrollBehavior(to, from, saved) {
    return saved ?? (to.path === from.path ? false : { top: 0 })
  },
  routes: [
    { path: '/', name: 'diary', component: () => import('../pages/DiaryPage.vue') },
    { path: '/calendar', name: 'calendar', component: () => import('../pages/CalendarPage.vue') },
    { path: '/catalog', name: 'catalog', component: () => import('../pages/CatalogPage.vue') },
    { path: '/capture', name: 'capture', component: () => import('../pages/CapturePage.vue') },
    { path: '/friends', name: 'friends', component: () => import('../pages/FriendsPage.vue') },
    { path: '/friends/:id/diary', name: 'friend-diary', component: () => import('../pages/DiaryPage.vue') },
    { path: '/friends/:id/catalog', name: 'friend-catalog', component: () => import('../pages/CatalogPage.vue') },
    { path: '/friends/:id/together', name: 'together', component: () => import('../pages/TogetherPage.vue') },
    { path: '/friends/:id/permissions', name: 'permissions', component: () => import('../pages/PermissionsPage.vue') },
    { path: '/me', name: 'profile', component: () => import('../pages/ProfilePage.vue') },
    { path: '/me/stats', name: 'stats', component: () => import('../pages/StatsPage.vue') },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})
