import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import { fileURLToPath } from 'node:url'

const date = '2026-11-27'
const photo = fileURLToPath(new URL('../../docs/ai-benchmark/images/homestyle-lunch.jpg', import.meta.url))
const pick = (page: Page) => page.locator('input[type=file][multiple]')

async function login(page: Page, username: string, register = true) {
  await page.goto('/login')
  const password = 'phase-five-sticker-fixture'
  const origin = new URL(page.url()).origin
  if (register) {
    const result = await page.request.post('/api/v1/auth/register', {
      headers: { Origin: origin, 'X-FoodDiary-Intent': 'browser' },
      data: { username, nickname: '贴纸测试', password },
    })
    expect(result.status()).toBe(201)
  }
  await page.getByLabel('用户名').fill(username)
  await page.getByLabel('密码', { exact: true }).fill(password)
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page.getByRole('heading', { name: '美食手账' })).toBeVisible()
}

async function form(page: Page, name: string) {
  await page.goto('/capture?date=' + date)
  await expect(page.getByRole('heading', { name: '记下这一餐' })).toBeVisible()
  await page.getByRole('textbox', { name: '食物名称' }).first().fill(name)
}

const save = (page: Page) => page.getByRole('button', { name: '保存记录' }).click()

test('@stickers 原图、抠图、贴纸可切换，月历与图鉴共享已确认记录', async ({ page, browser, baseURL }) => {
  await login(page, 'stickerview')
  await form(page, '家常三菜')
  await expect(page.getByText('AI 识别暂不可用，你仍可以手动记录。')).toHaveCount(0)
  await pick(page).setInputFiles(photo)
  await expect(page.getByText('AI 识别暂不可用，你仍可以手动记录。')).toBeVisible()
  await expect(page.getByText('正在制作你的美食贴纸…')).toBeVisible()
  await expect(page.getByRole('img', { name: '美食贴纸' })).toBeVisible({ timeout: 15000 })
  await page.getByRole('button', { name: '原图', exact: true }).click()
  await expect(page.getByRole('img', { name: '待保存的照片 1' })).toBeVisible()
  await page.getByRole('button', { name: '抠图', exact: true }).click()
  await expect(page.getByRole('img', { name: '透明抠图' })).toBeVisible()
  await save(page)
  const entry = page.getByRole('button', { name: '查看记录 家常三菜' })
  await expect(entry.locator('[data-sticker]')).toBeVisible()
  await page.getByRole('link', { name: '月历', exact: true }).click()
  await expect(page.getByRole('link', { name: date + ' 有记录' }).locator('[data-sticker]')).toBeVisible()
  await page.goto('/catalog')
  await expect(page.getByText('收录 1 种美食')).toBeVisible()
  await page.getByRole('button', { name: '收藏 家常三菜' }).click()
  await expect(page.getByRole('button', { name: '取消收藏 家常三菜' })).toBeVisible()
  const separate = await browser.newContext({ baseURL })
  try {
    const second = await separate.newPage()
    await login(second, 'stickerview', false)
    await second.goto('/catalog')
    await expect(second.getByRole('button', { name: '取消收藏 家常三菜' })).toBeVisible()
  } finally { await separate.close() }
  await form(page, '清蒸米饭')
  await save(page)
  await page.goto('/catalog')
  await page.getByRole('button', { name: /清蒸米饭.*次用餐/ }).click()
  const modal = page.getByRole('dialog')
  await modal.getByRole('button', { name: '合并到另一项' }).click()
  await modal.getByLabel('合并到', { exact: true }).selectOption({ label: '家常三菜' })
  await modal.getByRole('button', { name: '确认合并' }).click()
  await expect(modal.getByText('已合并，原用餐记录保留。')).toBeVisible()
  await expect(modal.getByText('2 次用餐', { exact: false })).toBeVisible()
})

test('@stickers 制作中可保存，失败后保留原图并可手动裁剪', async ({ page }) => {
  await login(page, 'stickersafe')
  await form(page, '制作中保存')
  await pick(page).setInputFiles(photo)
  await expect(page.getByText('正在制作你的美食贴纸…')).toBeVisible()
  await save(page)
  await expect(page.getByRole('button', { name: '查看记录 制作中保存' })).toBeVisible()
  await form(page, '原图保留')
  const bytes = await page.evaluate(() => {
    const image = document.createElement('canvas')
    image.width = image.height = 100
    const c = image.getContext('2d')!
    c.fillStyle = '#0000ff'
    c.fillRect(0, 0, 100, 100)
    return image.toDataURL('image/png').split(',')[1]
  })
  await pick(page).setInputFiles({ name: 'blue.png', mimeType: 'image/png', buffer: Buffer.from(bytes, 'base64') })
  await expect(page.getByText('这次没能完整取出食物，可以先使用原图。')).toBeVisible({ timeout: 15000 })
  await expect(page.getByRole('img', { name: '待保存的照片 1' })).toBeVisible()
  await page.getByRole('button', { name: '手动裁剪', exact: true }).click()
  await page.getByRole('button', { name: '使用裁剪' }).click()
  await expect(page.getByText('手动裁剪已保存。')).toBeVisible({ timeout: 15000 })
  await save(page)
  await expect(page.getByRole('button', { name: '查看记录 原图保留' })).toBeVisible()
})
