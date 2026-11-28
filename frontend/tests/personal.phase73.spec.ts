import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import { createHash } from 'node:crypto'
import { readFile } from 'node:fs/promises'
import { join } from 'node:path'

const evidence = process.env.FOODDIARY_73_EVIDENCE!
const api = '/api/v1'
const password = 'phase73-browser-fixture-only'
const screen = (page: Page, name: string) => page.screenshot({ path: join(evidence, name + '.png'), scale: 'css' })
const body = (page: Page) => page.locator('body').evaluate(node => ({ available: node.clientWidth, layout: node.scrollWidth }))

async function code(page: Page, email: string) {
  await page.getByLabel('邮箱地址').fill(email)
  await page.getByRole('button', { name: '发送验证码', exact: true }).click()
  await expect(page.getByText('验证码已发送，5 分钟内有效。')).toBeVisible()
  const filename = createHash('sha256').update(email).digest('hex') + '.txt'
  await page.getByLabel('邮箱验证码', { exact: true }).fill(await readFile(join(evidence, 'mock-inbox', filename), 'utf8'))
}

test('邮箱注册与登录、个人 AI、真实 ONNX 贴纸及好友同步', async ({ page, browser, baseURL }) => {
  const origin = { Origin: baseURL!, 'X-FoodDiary-Intent': 'browser' }
  await page.goto('/login')
  await expect(page.getByRole('button', { name: '邮箱验证码登录' })).toBeVisible()
  await screen(page, '01-password-login')
  const exploration = await page.addStyleTag({ content: `
    :root:has(.api-theme), .api-theme { --color-paper: #f5f5f5; --color-paper-warm: #ededed; --color-ink: #222; --color-line: #d3d3d3; --color-sage-deep: #222; --diary-ink-soft: #444; --paper-texture: none; }
    .auth-cover { background: #ebebeb; border: 0; }
    .auth-cover .sticker { transform: none; }
    .auth-cover figcaption { font-family: var(--font-sans); letter-spacing: .08em; }` })
  await screen(page, '00-exploration-monochrome')
  await exploration.evaluate(node => { node.parentNode?.removeChild(node) })
  await page.goto('/register')
  const email = 'author-' + crypto.randomUUID().slice(0, 8) + '@example.test'
  await page.getByLabel('昵称').fill('纸上食记')
  await page.getByLabel('用户名').fill('phase73_author_' + crypto.randomUUID().slice(0, 8))
  const username = await page.getByLabel('用户名').inputValue()
  await code(page, email)
  await page.getByLabel('密码', { exact: true }).fill(password)
  await page.getByRole('button', { name: '注册', exact: true }).click()
  await expect(page.getByText('账号已创建，请登录。')).toBeVisible()
  await page.getByLabel('用户名或已验证邮箱').fill(email)
  await page.getByLabel('密码', { exact: true }).fill(password)
  const loggedIn = page.waitForResponse(response => response.url().endsWith('/auth/login') && response.request().method() === 'POST')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  const author = await (await loggedIn).json()
  const authorHeaders = { Authorization: 'Bearer ' + author.access_token }
  await expect(page.getByRole('heading', { name: '美食手账' })).toBeVisible()
  await page.getByRole('link', { name: '了解如何连接' }).click()
  await expect(page.getByLabel('测试 API Key')).toBeVisible()
  await screen(page, '03-first-ai-connection')
  await page.getByLabel('测试 API Key').fill('fd-test-browser-only')
  await expect(page.getByLabel('测试 API Key')).toHaveAttribute('type', 'password')
  await page.getByRole('button', { name: '临时连接' }).click()
  await expect(page.getByRole('button', { name: '验证并查询余额' })).toBeVisible()
  await expect(page.getByLabel('测试 API Key')).toHaveValue('')
  await page.getByRole('button', { name: '验证并查询余额' }).click()
  await expect(page.getByText('模拟余额接口验证通过')).toBeVisible()
  await page.goto('/me/ai')
  await expect(page.getByRole('button', { name: '清除连接' })).toBeVisible()
  await screen(page, '04-ai-settings')
  await page.getByRole('button', { name: '清除连接' }).click()
  await expect(page.getByText('当前会话的连接已清除。')).toBeVisible()

  const reader = await browser.newContext({ baseURL, viewport: { width: 390, height: 844 }, locale: 'zh-CN', timezoneId: 'Asia/Shanghai',
    recordVideo: { dir: join(evidence, 'friend-video'), size: { width: 390, height: 844 } } })
  try {
    const friendPage = await reader.newPage()
    await friendPage.goto('/login')
    await friendPage.getByRole('button', { name: '邮箱验证码登录' }).click()
    await expect(friendPage.getByLabel('邮箱地址')).toBeVisible()
    await screen(friendPage, '02-email-code-login')
    await code(friendPage, 'reader@example.test')
    const loggedReader = friendPage.waitForResponse(response => response.url().endsWith('/auth/email/login'))
    await friendPage.getByRole('button', { name: '登录', exact: true }).click()
    const friend = await (await loggedReader).json()
    const friendHeaders = { Authorization: 'Bearer ' + friend.access_token }
    const sent = await page.request.post(api + '/friends/requests', {
      headers: authorHeaders, data: { public_id: friend.user.public_id },
    })
    expect(sent.status()).toBe(202)
    expect((await friendPage.request.post(api + '/friends/requests/' + (await sent.json()).id + '/accept',
      { headers: friendHeaders })).ok()).toBe(true)
    const sharing = api + '/friends/' + friend.user.public_id + '/sharing'
    const grant = async (permissions: Record<string, boolean>) => {
      const { relationship_id, outgoing: { version } } = await (await page.request.get(sharing, { headers: authorHeaders })).json()
      expect((await page.request.put(sharing, { headers: authorHeaders, data: { relationship_id, version, permissions } })).ok()).toBe(true)
    }
    await grant({ records: true, names: true, stickers: true })
    await page.goto('/')
    await page.getByRole('button', { name: '暂时跳过' }).click()
    await expect(page.getByLabel('首次使用 AI 助手')).toHaveCount(0)
    await page.getByRole('link', { name: '拍照', exact: true }).click()
    const shutter = page.getByRole('button', { name: '按下快门' })
    await expect(shutter).toBeEnabled()
    await screen(page, '05-camera')
    const before = Date.now()
    await shutter.tap()
    const day = await page.locator('input[type=date]').inputValue()
    const shared = '/friends/' + author.user.public_id + '/diary?date=' + day
    const visit = friendPage.goto(shared)
    await expect(page.getByRole('img', { name: '刚刚拍下的照片' })).toBeVisible()
    await screen(page, '06-captured')
    await expect(page.locator('.cutout-outline img')).toHaveAttribute('src', /^blob:/)
    await screen(page, '07-cutout-reveal')
    await expect(page.locator('.capture-stage')).toHaveAttribute('data-stage', 'ready')
    const elapsed = Date.now() - before
    await page.getByRole('textbox', { name: '食物名称' }).first().fill('家常三菜')
    await screen(page, '08-sticker-confirmation')
    await visit
    await expect(friendPage.getByText('这一天还没有饮食记录。')).toBeVisible()
    const saved = page.waitForResponse(response => response.url().endsWith('/meals') && response.request().method() === 'POST')
    await page.getByRole('button', { name: '贴进手账' }).click()
    const { id, media } = await (await saved).json()
    await expect(page.locator('.landing-sticker')).toBeVisible()
    await screen(page, '09-placement')
    await expect(page.locator('.landing-sticker')).toHaveCount(0)
    await expect(page.getByRole('button', { name: '查看记录 家常三菜' }).locator('[data-sticker]')).toBeVisible()
    await page.reload()
    await expect(page.getByRole('button', { name: '查看记录 家常三菜' })).toBeVisible()
    await screen(page, '10-diary')
    await page.getByRole('link', { name: '月历', exact: true }).click()
    await expect(page.getByRole('heading', { name: '饮食月历' })).toBeVisible()
    await expect(page.getByRole('link', { name: day + ' 有记录' })).toBeVisible()
    await screen(page, '11-calendar')
    await page.getByRole('link', { name: '图鉴', exact: true }).click()
    await expect(page.getByRole('button', { name: /家常三菜/ }).first()).toBeVisible()
    await screen(page, '12-catalog')
    await expect(friendPage.getByRole('img', { name: '共享美食贴纸' })).toBeVisible()
    await screen(friendPage, '13-friend-diary')
    await page.getByRole('navigation', { name: '主导航' }).getByRole('link', { name: '饭搭子' }).click()
    await expect(page.getByRole('region', { name: '我的饭搭子' }).getByText('阅读搭子')).toBeVisible()
    await screen(page, '14-friends')
    await page.getByRole('navigation', { name: '主导航' }).getByRole('link', { name: '我的' }).click()
    await expect(page.getByRole('heading', { name: '个人设置' })).toBeVisible()
    await screen(page, '15-profile')
    await page.getByRole('link', { name: '账号安全' }).click()
    await expect(page.getByText(email)).toBeVisible()
    await screen(page, '16-account-security')
    const dimensions = await body(page)
    expect(dimensions.layout).toBeLessThanOrEqual(dimensions.available)
    const photoPath = api + '/friends/' + author.user.public_id + '/media/' + media[0].id + '/sticker?meal_id=' + id
    expect((await friendPage.request.get(photoPath, { headers: friendHeaders })).status()).toBe(200)
    await grant({})
    expect((await friendPage.request.get(photoPath, { headers: friendHeaders })).status()).toBe(404)
    await friendPage.reload()
    await expect(friendPage.getByRole('img', { name: '共享美食贴纸' })).toHaveCount(0)
    await friendPage.setViewportSize({ width: 430, height: 932 })
    expect((await body(friendPage)).layout).toBeLessThanOrEqual(430)
    await page.setViewportSize({ width: 1280, height: 900 })
    await page.goto('/')
    await expect(page.getByRole('button', { name: '查看记录 家常三菜' })).toBeVisible()
    await screen(page, '17-diary-desktop')
    expect((await page.request.post(api + '/auth/login', { headers: origin, data: { username, password } })).status()).toBe(200)
    console.log('Camera flow in the local browser fixture took ' + elapsed + ' ms from shutter to ready sticker')
  } finally {
    await reader.close()
  }
})
