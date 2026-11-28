import type { NavigationGuard, RouteRecordRaw } from 'vue-router'
import Root from '../layouts/ApiRoot.vue'
import { useAuth } from '../stores/auth'

export { Root }

const empty = () => import('../pages/ApiEmptyPage.vue')
const authPage = () => import('../pages/AuthPage.vue')
const friendBook = () => import('../pages/ApiFriendBookPage.vue')
const friendPath = '/friends/:friendId(fd_[a-f0-9]{32})'
export const routes: RouteRecordRaw[] = [
  { path: '/login', name: 'login', component: authPage },
  { path: '/register', name: 'register', component: authPage },
  { path: '/recover', name: 'recover', component: authPage },
  { path: '/me', name: 'profile', meta: { requiresAuth: true }, component: () => import('../pages/ApiProfilePage.vue') },
  { path: '/me/security', name: 'security', meta: { requiresAuth: true }, component: () => import('../pages/ApiSecurityPage.vue') },
  { path: '/me/ai', name: 'personal-ai', meta: { requiresAuth: true }, component: () => import('../pages/ApiAiPage.vue') },
  { path: '/', name: 'diary', meta: { requiresAuth: true }, component: () => import('../pages/ApiDiaryPage.vue') },
  { path: '/calendar', name: 'calendar', meta: { requiresAuth: true }, component: () => import('../pages/ApiCalendarPage.vue') },
  { path: '/catalog', name: 'catalog', meta: { requiresAuth: true }, component: () => import('../pages/ApiCatalogPage.vue') },
  { path: '/capture', name: 'capture', meta: { requiresAuth: true }, component: () => import('../pages/ApiMealForm.vue') },
  { path: '/friends', name: 'friends', meta: { requiresAuth: true }, component: () => import('../pages/ApiFriendsPage.vue') },
  { path: friendPath + '/sharing', name: 'friend-sharing', meta: { requiresAuth: true }, component: () => import('../pages/ApiSharingPage.vue') },
  { path: friendPath + '/diary', name: 'friend-diary', meta: { requiresAuth: true }, component: friendBook },
  { path: friendPath + '/calendar', name: 'friend-calendar', meta: { requiresAuth: true }, component: friendBook },
  { path: friendPath + '/catalog', name: 'friend-catalog', meta: { requiresAuth: true }, component: friendBook },
  { path: friendPath + '/together', name: 'friend-together', meta: { requiresAuth: true }, component: friendBook },
  ...[
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
