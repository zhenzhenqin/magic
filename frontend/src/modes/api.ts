import type { NavigationGuard, RouteRecordRaw } from 'vue-router'
import Root from '../layouts/ApiRoot.vue'
import { useAuth } from '../stores/auth'

export { Root }

const empty = () => import('../pages/ApiEmptyPage.vue')
const authPage = () => import('../pages/AuthPage.vue')
export const routes: RouteRecordRaw[] = [
  { path: '/login', name: 'login', component: authPage },
  { path: '/register', name: 'register', component: authPage },
  { path: '/me', name: 'profile', meta: { requiresAuth: true }, component: () => import('../pages/ApiProfilePage.vue') },
  { path: '/', name: 'diary', meta: { requiresAuth: true }, component: () => import('../pages/ApiDiaryPage.vue') },
  { path: '/calendar', name: 'calendar', meta: { requiresAuth: true }, component: () => import('../pages/ApiCalendarPage.vue') },
  { path: '/capture', name: 'capture', meta: { requiresAuth: true }, component: () => import('../pages/ApiMealForm.vue') },
  ...[
    ['/catalog', 'catalog', '美食图鉴'],
    ['/friends', 'friends', '饭搭子'],
    ['/friends/:pathMatch(.*)*', 'friend-pages', '饭搭子'],
    ['/me/stats', 'stats', '饮食统计'],
  ].map(([path, name, title]) => ({ path, name, meta: { title, requiresAuth: true }, component: empty })),
]

export const beforeEach: NavigationGuard = async to => {
  const auth = useAuth()
  await auth.initialize()
  if (to.meta.requiresAuth && !auth.isAuthenticated) return { name: 'login' }
  if (!to.meta.requiresAuth && auth.isAuthenticated) return { name: 'diary' }
}
