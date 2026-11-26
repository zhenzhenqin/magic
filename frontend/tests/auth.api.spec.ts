import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import { mkdir } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'

const password = 'phase-two-browser-fixture'
const screenshotRoot = new URL('../../docs/screenshots/phase-2/', import.meta.url)
const report = new URL('../playwright-report/phase-2-api/index.html', import.meta.url)

async function register(page: Page, username: string, nickname: string) {
  await page.goto('/register')
  await expect(page.getByRole('heading', { name: '开始你的手账' })).toBeVisible()
  await page.getByRole('textbox', { name: '昵称', exact: true }).fill(nickname)
  await page.getByLabel('用户名').fill(username)
  await page.getByLabel('密码', { exact: true }).fill(password)
  await page.getByRole('button', { name: '注册', exact: true }).click()
  await expect(page.getByText('账号已创建，请登录。')).toBeVisible()
}

async function login(page: Page, username: string) {
  await page.getByLabel('用户名').fill(username)
  await page.getByLabel('密码', { exact: true }).fill(password)
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page.getByRole('heading', { name: '美食手账' })).toBeVisible()
}

async function logout(page: Page) {
  await page.getByRole('button', { name: '退出登录' }).click()
  await page.getByRole('button', { name: '确认退出' }).click()
  await expect(page.getByRole('heading', { name: '欢迎回来' })).toBeVisible()
}

async function profile(page: Page) {
  await page.getByRole('navigation', { name: '主导航' }).getByRole('link', { name: '我的' }).click()
  await expect(page.getByRole('heading', { name: '个人设置' })).toBeVisible()
  await expect(page.getByRole('button', { name: '保存设置' })).toBeEnabled()
}

test('真实注册、登录、HttpOnly 会话与刷新恢复', async ({ page, context }) => {
  await page.goto('/me')
  await expect(page).toHaveURL(/\/login$/)
  await register(page, 'browser_reader', '手账读者')
  await page.getByRole('button', { name: '显示密码' }).click()
  await expect(page.getByLabel('密码', { exact: true })).toHaveAttribute('type', 'text')
  await page.getByRole('button', { name: '隐藏密码' }).click()
  await login(page, 'browser_reader')
  const initial = (await context.cookies()).find(cookie => cookie.name === 'fooddiary_refresh')
  expect(initial).toMatchObject({ httpOnly: true, sameSite: 'Strict', path: '/api/v1/auth', secure: false })
  await page.reload()
  await expect(page.getByRole('heading', { name: '这一页还留白' })).toBeVisible()
  const rotated = (await context.cookies()).find(cookie => cookie.name === 'fooddiary_refresh')
  expect(!!rotated && rotated.value !== initial?.value).toBe(true)
  const stores = await page.evaluate(() => ({ local: localStorage.length, temporary: sessionStorage.length }))
  expect(stores).toEqual({ local: 0, temporary: 0 })
  await profile(page)
  await expect(page.getByRole('textbox', { name: '昵称', exact: true })).toHaveValue('手账读者')
})

test('个人资料和设置、退出确认、两个真实账号隔离', async ({ page }) => {
  await register(page, 'browser_alice', '甲账号')
  await login(page, 'browser_alice')
  await profile(page)
  await page.getByRole('textbox', { name: '昵称', exact: true }).fill('甲的私人昵称')
  await page.getByRole('button', { name: '保存昵称' }).click()
  await expect(page.getByText('昵称已保存。')).toBeVisible()
  await page.getByLabel('时区').fill('UTC')
  await page.getByRole('checkbox', { name: '显示热量' }).uncheck()
  await page.getByRole('button', { name: '保存设置' }).click()
  await expect(page.getByText('个人设置已保存。')).toBeVisible()
  await page.reload()
  await expect(page.getByRole('textbox', { name: '昵称', exact: true })).toHaveValue('甲的私人昵称')
  await expect(page.getByLabel('时区')).toHaveValue('UTC')
  await expect(page.getByRole('checkbox', { name: '显示热量' })).not.toBeChecked()
  await logout(page)
  await register(page, 'browser_bob', '乙账号')
  await login(page, 'browser_bob')
  await profile(page)
  await expect(page.getByRole('textbox', { name: '昵称', exact: true })).toHaveValue('乙账号')
  await expect(page.getByLabel('时区')).toHaveValue('Asia/Shanghai')
  await expect(page.getByRole('checkbox', { name: '显示热量' })).toBeChecked()
  await expect(page.getByText('甲的私人昵称')).toHaveCount(0)
})

test('Access Token 到期自动刷新，整个会话到期回到登录', async ({ page, context }) => {
  await register(page, 'browser_expiry', '会话测试')
  await login(page, 'browser_expiry')
  const now = (await context.cookies()).find(cookie => cookie.name === 'fooddiary_refresh')!
  // A real server clock controls both JWT and cookie expiry.
  await new Promise(resolve => setTimeout(resolve, 4500))
  const refresh = page.waitForResponse(response => response.url().endsWith('/auth/refresh') && response.status() === 200)
  await profile(page)
  await refresh
  const renewed = (await context.cookies()).find(cookie => cookie.name === 'fooddiary_refresh')
  expect(!!renewed && renewed.value !== now.value).toBe(true)
  await expect.poll(async () => (await context.cookies()).some(cookie => cookie.name === 'fooddiary_refresh'), {
    timeout: 16_000, intervals: [500, 1_000],
  }).toBe(false)
  await page.reload()
  await expect(page).toHaveURL(/\/login$/)
  await expect(page.getByRole('heading', { name: '欢迎回来' })).toBeVisible()
})

test('后端不可用时提示，认证失败时保持在登录页', async ({ page }) => {
  await page.route('**/api/v1/auth/**', route => route.abort('connectionfailed'))
  await page.goto('/login')
  await expect(page.getByText('无法连接 FoodDiary 服务，请检查连接后重试。')).toBeVisible()
  await page.getByLabel('用户名').fill('unknown_user')
  await page.getByLabel('密码', { exact: true }).fill(password)
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('无法连接 FoodDiary 服务')
  await page.unrouteAll()
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('用户名或密码不正确')
  await expect(page).toHaveURL(/\/login$/)
})

test('API 模式隔离已有 Demo 本地状态和深链接', async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem('fooddiary.demo.v1', JSON.stringify({ activeUserId: 'lin', privateNote: '只属于演示空间' }))
  })
  await register(page, 'browser_isolated', '真实手账用户')
  await login(page, 'browser_isolated')
  await expect(page.getByRole('heading', { name: '这一页还留白' })).toBeVisible()
  await page.goto('/friends/lan/diary')
  await expect(page.getByRole('heading', { name: '这一页正在准备' })).toBeVisible()
  for (const name of ['小林', '阿岚', '黄油可颂', '切换演示账号', '只属于演示空间']) {
    await expect(page.getByText(name, { exact: true })).toHaveCount(0)
  }
  await expect(page.getByRole('navigation').getByRole('link')).toHaveCount(5)
  expect(await page.evaluate(() => JSON.parse(localStorage.getItem('fooddiary.demo.v1')!).privateNote)).toBe('只属于演示空间')
})

for (const [width, height] of [[390, 844], [1440, 900]]) {
  test('API 模式响应式 ' + width + ' × ' + height, async ({ page }) => {
    await page.setViewportSize({ width, height })
    await page.goto('/login')
    await expect(page.getByRole('heading', { name: '欢迎回来' })).toBeVisible()
    const checkOverflow = () => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)
    expect(await checkOverflow()).toBe(true)
    const username = 'layout_' + width
    await register(page, username, '布局测试')
    await login(page, username)
    expect(await checkOverflow()).toBe(true)
    await profile(page)
    expect(await checkOverflow()).toBe(true)
  })
}

async function capture(page: Page, name: string) {
  await mkdir(fileURLToPath(screenshotRoot), { recursive: true })
  await page.evaluate(() => document.fonts.ready.then(() => undefined))
  await page.screenshot({
    path: fileURLToPath(new URL(name + '.jpg', screenshotRoot)), type: 'jpeg', quality: 87,
    animations: 'disabled', fullPage: name === '05-swagger',
  })
}

test('@screenshots 登录、注册、真实个人中心与手账空状态', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/login')
  await expect(page.getByRole('heading', { name: '欢迎回来' })).toBeVisible()
  await capture(page, '01-login')
  await page.goto('/register')
  await expect(page.getByRole('heading', { name: '开始你的手账' })).toBeVisible()
  await capture(page, '02-register')
  await register(page, 'screenshot_reader', '纸上食记')
  await login(page, 'screenshot_reader')
  await capture(page, '04-diary-empty')
  await profile(page)
  await capture(page, '03-profile')
})

test('@screenshots Swagger 和实际测试报告', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('http://127.0.0.1:' + (process.env.FOODDIARY_BACKEND_PORT ?? '18020') + '/docs')
  await expect(page.locator('.swagger-ui .info .title')).toContainText('FoodDiary API', { timeout: 20_000 })
  await capture(page, '05-swagger')
  await page.goto(report.href)
  await expect(page.getByRole('link', { name: /^Passed\d+$/ })).toBeVisible({ timeout: 12_000 })
  await expect(page.getByRole('link', { name: 'Failed0' })).toBeVisible()
  await capture(page, '06-test-results')
})
