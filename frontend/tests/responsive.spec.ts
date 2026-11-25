import { expect, test } from '@playwright/test'
import { demoClock } from './demo-fixtures'

const routes = [
  ['/', '美食手账'], ['/calendar', '饮食月历'], ['/catalog', '美食图鉴'],
  ['/capture', '记下这一餐'], ['/friends', '饭搭子'], ['/friends/lan/diary', '阿岚的手账'],
  ['/friends/lan/catalog', '阿岚的图鉴'], ['/friends/lan/together', '双人手账'],
  ['/friends/lan/permissions', '共享授权'], ['/me', '我的'], ['/me/stats', '饮食统计'],
] as const

for (const [width, height] of [[360, 800], [390, 844], [430, 932], [768, 1024], [1440, 900]]) {
  test('响应式与核心路由 ' + width + ' × ' + height, async ({ page }) => {
    await page.setViewportSize({ width, height })
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await page.clock.setFixedTime(demoClock)
    const errors: string[] = []
    page.on('pageerror', error => errors.push(error.message))
    for (const [route, title] of routes) {
      await page.goto(route)
      await expect(page.getByRole('heading', { name: title, exact: true, level: 1 })).toBeVisible()
      const navigation = page.getByRole('navigation', { name: '主导航' })
      await expect(navigation.getByRole('link')).toHaveCount(5)
      const state = await page.evaluate(() => ({
        horizontalOverflow: document.documentElement.scrollWidth > window.innerWidth,
        bottomNavigation: getComputedStyle(document.querySelector('nav')!).position === 'fixed',
        mobileReserved: parseFloat(getComputedStyle(document.querySelector('.page-shell')!).paddingBottom),
        navigationHeight: document.querySelector('nav')!.getBoundingClientRect().height,
        reducedMotion: matchMedia('(prefers-reduced-motion: reduce)').matches,
        stretchedSticker: [...document.querySelectorAll('.sticker img')].some(image => getComputedStyle(image).objectFit !== 'contain'),
      }))
      expect(state.horizontalOverflow, route).toBe(false)
      expect(state.bottomNavigation).toBe(width <= 900)
      if (width <= 900) expect(state.mobileReserved).toBeGreaterThan(state.navigationHeight)
      expect(state.reducedMotion).toBe(true)
      expect(state.stretchedSticker).toBe(false)
    }
    expect(errors).toEqual([])
  })
}
