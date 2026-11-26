import { createRouter, createWebHistory } from 'vue-router'
import { beforeEach, routes } from '@fooddiary/runtime'

export const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  scrollBehavior(to, from, saved) {
    return saved ?? (to.path === from.path ? false : { top: 0 })
  },
  routes: [...routes, { path: '/:pathMatch(.*)*', redirect: '/' }],
})

if (beforeEach) router.beforeEach(beforeEach)
