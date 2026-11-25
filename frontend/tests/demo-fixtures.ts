import { expect } from '@playwright/test'
import type { Page } from '@playwright/test'
import { fileURLToPath } from 'node:url'

export const photoFile = fileURLToPath(new URL('../src/assets/food/curry.webp', import.meta.url))
export const demoDay = '2026-11-25'
export const demoClock = new Date(demoDay + 'T12:00:00+08:00')

export async function pickAndRecognize(page: Page) {
  await page.locator('input[type=file]').setInputFiles(photoFile)
  const preview = page.getByRole('img', { name: '所选食物图片预览' })
  await expect(preview).toBeVisible()
  await expect.poll(async () => preview.evaluate((image: HTMLImageElement) => image.naturalWidth)).toBeGreaterThan(0)
  await page.getByRole('button', { name: '模拟 AI 识别' }).click()
  await expect(page.getByLabel('食物名称')).toHaveValue('日式咖喱饭')
}

export async function account(page: Page, id: string) {
  await page.goto('/me')
  await page.getByLabel('切换演示账号').selectOption(id)
}
