import { expect, test } from '@playwright/test'
import { mkdir } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { demoClock, pickAndRecognize } from './demo-fixtures'

const target = new URL('../../docs/screenshots/phase-1/', import.meta.url)
const screens = [
  ['01-home-mobile', '/', '美食手账', 390, 844],
  ['02-home-desktop', '/', '美食手账', 1440, 900],
  ['03-calendar', '/calendar', '饮食月历', 1440, 1000],
  ['04-catalog', '/catalog', '美食图鉴', 1440, 900],
  ['05-capture', '/capture', '记下这一餐', 1440, 900],
  ['06-friends', '/friends', '饭搭子', 1440, 900],
  ['07-together', '/friends/lan/together', '双人手账', 1440, 900],
  ['08-permissions', '/friends/lan/permissions', '共享授权', 1440, 900],
  ['09-profile', '/me', '我的', 1440, 900],
] as const

for (const [file, route, title, width, height] of screens) {
  test('@screenshots ' + file, async ({ page }) => {
    await page.setViewportSize({ width, height })
    await page.clock.setFixedTime(demoClock)
    await page.goto(route)
    await expect(page.getByRole('heading', { name: title, exact: true, level: 1 })).toBeVisible()
    if (route === '/capture') await pickAndRecognize(page)
    await page.evaluate(async () => {
      await document.fonts.ready
      await Promise.all([...document.images].map(image => image.decode()))
    })
    await mkdir(fileURLToPath(target), { recursive: true })
    await page.screenshot({
      path: fileURLToPath(new URL(file + '.jpg', target)),
      type: 'jpeg',
      quality: 87,
      animations: 'disabled',
      fullPage: file !== '01-home-mobile' && file !== '02-home-desktop',
    })
  })
}
