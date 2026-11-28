import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import { randomUUID } from 'node:crypto'
import { mkdir } from 'node:fs/promises'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

const screenshots = process.env.FOODDIARY_BROWSER_SHARING_REAL === '1'
const screenshotDir = process.env.FOODDIARY_SHARING_EVIDENCE
  ?? fileURLToPath(new URL('../../docs/screenshots/phase-6/', import.meta.url))
const fixtures = new URL('../../docs/ai-benchmark/images/', import.meta.url)
const base = '/api/v1/friends/'

async function openAccount(page: Page, nickname: string) {
  await page.goto('/login')
  const origin = new URL(page.url()).origin
  const username = 'friend_' + randomUUID().slice(0, 8)
  const password = randomUUID()
  const result = await page.request.post('/api/v1/auth/register', {
    headers: { Origin: origin, 'X-FoodDiary-Intent': 'browser' },
    data: { username, nickname, password },
  })
  expect(result.status()).toBe(201)
  const { public_id: id } = await result.json()
  await page.getByLabel('用户名').fill(username)
  await page.getByLabel('密码', { exact: true }).fill(password)
  const login = page.waitForResponse(response => response.url().endsWith('/api/v1/auth/login'))
  await page.getByRole('button', { name: '登录', exact: true }).click()
  const token = (await (await login).json()).access_token
  await expect(page.getByRole('heading', { name: '美食手账' })).toBeVisible()
  return { id, username, password, headers: { Authorization: 'Bearer ' + token } }
}

async function snap(page: Page, name: string, fullPage = false) {
  if (!screenshots) return
  await page.evaluate(async () => {
    if (!document.querySelector('dialog[open]') && document.activeElement instanceof HTMLElement) document.activeElement.blur()
    window.scrollTo(0, 0)
    await document.fonts.ready
  })
  await mkdir(screenshotDir, { recursive: true })
  await page.screenshot({ path: join(screenshotDir, name + '.png'), fullPage, animations: 'disabled' })
}

function today(page: Page) {
  return page.evaluate(() => {
    const parts = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts()
    return ['year', 'month', 'day'].map(field => parts.find(part => part.type === field)?.value).join('-')
  })
}

async function cook(page: Page, date: string, kind: string, name: string, file: string, time: string) {
  await page.goto('/capture?date=' + date)
  await expect(page.getByRole('heading', { name: '记下这一餐' })).toBeVisible()
  await page.getByRole('combobox', { name: /餐次/ }).selectOption(kind)
  await page.getByLabel('用餐时间', { exact: true }).fill(time)
  await page.getByRole('textbox', { name: '食物名称', exact: true }).first().fill(name)
  await page.locator('input[type=file][multiple]').setInputFiles(fileURLToPath(new URL(file, fixtures)))
  await page.getByRole('heading', { name: '食物照片' }).scrollIntoViewIfNeeded()
  await expect(page.getByRole('img', { name: '美食贴纸', exact: true })).toBeVisible({ timeout: 45_000 })
  const saved = page.waitForResponse(response => response.url().endsWith('/api/v1/meals') && response.request().method() === 'POST')
  await page.getByRole('button', { name: '保存记录', exact: true }).click()
  const response = await saved
  expect(response.status()).toBe(201)
  return response.json()
}

test('@sharing 三账号好友关系与授权，自动同步、媒体撤销和双人手账', async ({ browser, baseURL }) => {
  test.setTimeout(180_000)
  const contexts = await Promise.all(Array.from({ length: 3 }, () => browser.newContext({
    baseURL, viewport: { width: 430, height: 932 }, locale: 'zh-CN', timezoneId: 'Asia/Shanghai',
  })))
  const [author, reader, outsider] = await Promise.all(contexts.map(context => context.newPage()))
  try {
    const a = await openAccount(author, '山茶')
    const b = await openAccount(reader, '小满')
    const c = await openAccount(outsider, '栗子')
    const day = await today(author)
    const book = '/friends/' + a.id
    const sharedDay = book + '/diary?date=' + day
    const api = base + a.id
    await author.goto('/friends')
    await expect(author.getByText(a.id)).toBeVisible()
    await author.getByRole('button', { name: '添加饭搭子' }).click()
    await author.getByLabel('好友的完整公开 ID').fill(b.id)
    await author.getByRole('button', { name: '查找好友' }).click()
    await expect(author.getByRole('dialog').getByText('小满')).toBeVisible()
    await snap(author, '02-add-friend')
    await author.getByRole('button', { name: '发送好友申请' }).click()
    await expect(author.getByText('申请已发送。')).toBeVisible()
    await reader.goto('/friends')
    await expect(reader.getByRole('button', { name: '接受', exact: true })).toBeVisible()
    await snap(reader, '03-incoming-request')
    await reader.getByRole('button', { name: '接受', exact: true }).click()
    await expect(reader.getByText('饮食手账暂未共享')).toBeVisible()
    await snap(reader, '04-default-private')
    await reader.getByRole('link', { name: '查看手账', exact: true }).click()
    await expect(reader.getByText('这本手账暂未共享。')).toBeVisible()

    await author.goto('/friends')
    await author.getByRole('link', { name: '共享设置' }).click()
    await author.getByRole('button', { name: '使用推荐预设' }).click()
    await author.getByRole('checkbox', { name: /美食图鉴/ }).check()
    await author.getByRole('button', { name: '保存授权' }).click()
    await expect(author.getByText('共享设置已保存。')).toBeVisible()
    await expect(author.getByText('对方尚未开放任何共享内容。')).toBeVisible()
    if (screenshots) {
      await author.setViewportSize({ width: 1440, height: 1260 })
      await snap(author, '05-directional-settings')
      await author.setViewportSize({ width: 430, height: 932 })
    }
    const ownUnshared = await author.request.get(base + b.id + '/meals?date=' + day, { headers: a.headers })
    expect(ownUnshared.status()).toBe(404)

    await cook(reader, day, 'lunch', '番茄炒鸡蛋', 'tomato-eggs-overhead.jpg', '12:15')
    await reader.goto(sharedDay)
    await expect(reader.getByText('这一天还没有饮食记录。')).toBeVisible()
    const pendingRead = reader.waitForResponse(
      response => response.url().includes(api + '/meals?') && response.status() === 200
        && response.json().then(body => body.items.some((item: { items?: { food_name?: string }[] }) =>
          item.items?.some(food => food.food_name === '家常三菜'))).catch(() => false),
      { timeout: 75_000 },
    )
    const lunch = await cook(author, day, 'lunch', '家常三菜', 'homestyle-lunch.jpg', '12:30')
    await pendingRead
    const lunchTile = reader.getByRole('button', { name: /家常三菜.*午餐/ })
    await expect(lunchTile.getByRole('img', { name: '共享美食贴纸' })).toBeVisible()
    expect(await lunchTile.evaluate(tile => {
      const photo = tile.querySelector('img')!.getBoundingClientRect()
      const title = tile.querySelector('.scrap-title')!.getBoundingClientRect()
      return photo.bottom <= title.top + 5
    })).toBe(true)
    const id = lunch.media[0].id
    const detail = api + '/meals/' + lunch.id
    const media = api + '/media/' + id
    const params = '?meal_id=' + lunch.id
    expect((await reader.request.get(media + '/sticker/thumbnail' + params, { headers: b.headers })).status()).toBe(200)
    for (const path of [media + params, media + '/thumbnail' + params, media + '/sticker/cutout' + params]) {
      expect((await reader.request.get(path, { headers: b.headers })).status()).toBe(404)
    }
    for (const path of [detail, media + '/sticker' + params, api + '/catalog', api + '/calendar?month=' + day.slice(0, 7)]) {
      expect((await outsider.request.get(path, { headers: c.headers })).status()).toBe(404)
    }
    await outsider.goto(sharedDay)
    await expect(outsider.getByText('无法读取该好友的共享内容。')).toBeVisible()

    if (screenshots) {
      await cook(author, day, 'breakfast', '燕麦饼干', 'oat-biscuits.jpg', '08:10')
      await cook(author, day, 'dinner', '番茄鸡蛋', 'tomato-eggs-side.jpg', '18:20')
      await reader.getByRole('button', { name: '刷新共享内容' }).click()
      await expect(reader.getByRole('img', { name: '共享美食贴纸' })).toHaveCount(3)
    }
    await snap(reader, '06-friend-diary')
    await lunchTile.click()
    await expect(reader.getByRole('dialog').getByText('家常三菜', { exact: true })).toBeVisible()
    await expect(reader.getByRole('dialog').getByRole('img', { name: '共享美食贴纸' })).toBeVisible()
    await expect(reader.getByRole('dialog').getByText('热量', { exact: true })).toHaveCount(0)
    await reader.getByRole('button', { name: '关闭弹窗' }).click()
    const nav = reader.getByRole('navigation', { name: '好友手账导航' })
    await nav.getByRole('link', { name: '月历', exact: true }).click()
    await expect(reader.getByRole('link', { name: day, exact: true }).getByRole('img')).toBeVisible()
    await snap(reader, '07-friend-calendar')
    await nav.getByRole('link', { name: '图鉴', exact: true }).click()
    await expect(reader.getByRole('button', { name: /家常三菜/ }).getByRole('img')).toBeVisible()
    await expect(reader.getByText('共享历史')).toHaveCount(0)
    await snap(reader, '08-friend-catalog')
    await nav.getByRole('link', { name: '双人手账' }).click()
    await expect(reader.getByRole('region', { name: '我的记录' }).filter({ hasText: '番茄炒鸡蛋' }).getByRole('img')).toBeVisible()
    await expect(lunchTile.getByRole('img')).toBeVisible()
    await snap(reader, '09-together-phone')
    if (screenshots) {
      await reader.setViewportSize({ width: 1440, height: 1050 })
      await snap(reader, '10-together-desktop', true)
      await reader.setViewportSize({ width: 430, height: 932 })
    }
    await reader.goto('/friends')
    await reader.getByRole('button', { name: '今日预览' }).click()
    await expect(reader.getByRole('img', { name: '共享美食贴纸' }).first()).toBeVisible()
    await snap(reader, '01-friends')
    await reader.goto(sharedDay)
    const sharedImage = lunchTile.getByRole('img', { name: '共享美食贴纸' })
    await expect(sharedImage).toBeVisible()
    const fallback: string[] = []
    reader.on('request', request => {
      const path = new URL(request.url()).pathname
      if (path.startsWith(api + '/media/') && !path.includes('/sticker')) fallback.push(path)
    })
    const stickerRequest = '**' + media + '/sticker/thumbnail?*'
    await reader.route(stickerRequest, request => request.fulfill({ status: 404, json: { error: { code: 'shared_not_found' } } }))
    await reader.getByRole('button', { name: '刷新共享内容' }).click()
    await expect(lunchTile.getByText('贴纸暂不可用')).toBeVisible()
    expect(fallback).toEqual([])
    await reader.unroute(stickerRequest)
    await reader.getByRole('button', { name: '刷新共享内容' }).click()
    await expect(sharedImage).toBeVisible()
    const oldBlob = (await sharedImage.getAttribute('src'))!
    await author.goto('/friends/' + b.id + '/sharing')
    await author.getByRole('checkbox', { name: /美食贴纸/ }).uncheck()
    await author.getByRole('button', { name: '保存授权' }).click()
    await expect(author.getByText('共享设置已保存。')).toBeVisible()
    expect((await reader.request.get(media + '/sticker/thumbnail' + params, { headers: b.headers })).status()).toBe(404)
    await reader.evaluate(() => window.dispatchEvent(new Event('focus')))
    await expect(lunchTile).toBeVisible()
    await expect(sharedImage).toHaveCount(0)
    expect(await reader.evaluate(url => fetch(url).then(() => false, () => true), oldBlob)).toBe(true)
    expect(fallback).toEqual([])
    await snap(reader, '11-partial-sharing')
    await contexts[1].setOffline(true)
    await expect(reader.getByText(/网络已断开/)).toBeVisible()
    await expect(lunchTile).toHaveCount(0)
    await contexts[1].setOffline(false)
    await expect(lunchTile).toBeVisible()

    await author.getByRole('button', { name: '全部停止共享' }).click()
    await author.getByRole('button', { name: '确认停止共享' }).click()
    await expect(author.getByText('已停止向对方共享。')).toBeVisible()
    await reader.getByRole('button', { name: '刷新共享内容' }).click()
    await expect(reader.getByText('这本手账暂未共享。')).toBeVisible()
    await snap(reader, '12-stop-sharing')
    await author.getByRole('button', { name: '解除好友', exact: true }).click()
    await author.getByRole('button', { name: '确认解除' }).click()
    await expect(author.getByRole('heading', { name: '饭搭子', exact: true })).toBeVisible()
    expect((await reader.request.get(detail, { headers: b.headers })).status()).toBe(404)
    expect((await outsider.request.get(detail, { headers: c.headers })).status()).toBe(404)
    await reader.getByRole('button', { name: '刷新共享内容' }).click()
    await expect(reader.getByText('无法读取该好友的共享内容。')).toBeVisible()
    await reader.goto('/me')
    await reader.getByRole('button', { name: '退出登录', exact: true }).click()
    await reader.getByRole('button', { name: '确认退出' }).click()
    await reader.getByLabel('用户名').fill(c.username)
    await reader.getByLabel('密码', { exact: true }).fill(c.password)
    await reader.getByRole('button', { name: '登录', exact: true }).click()
    await expect(reader.getByRole('heading', { name: '美食手账' })).toBeVisible()
    await reader.goto(sharedDay)
    await expect(reader.getByText('无法读取该好友的共享内容。')).toBeVisible()
    await expect(lunchTile).toHaveCount(0)
  } finally {
    await Promise.all(contexts.map(context => context.close()))
  }
})

test('@sharing 断网与返回前台立即重验授权，取消旧图读取', async ({ browser, baseURL }) => {
  const contexts = await Promise.all([browser.newContext({ baseURL }), browser.newContext({ baseURL })])
  const [author, reader] = await Promise.all(contexts.map(context => context.newPage()))
  try {
    const a = await openAccount(author, '复查作者')
    const b = await openAccount(reader, '复查读者')
    const day = await today(author)
    const shared = base + a.id
    const createRequest = await author.request.post(base + 'requests', { headers: a.headers, data: { public_id: b.id } })
    const { id: requestId } = await createRequest.json()
    expect((await reader.request.post(base + 'requests/' + requestId + '/accept', { headers: b.headers })).status()).toBe(200)
    const configPath = base + b.id + '/sharing'
    async function photoAccess(enabled: boolean) {
      const { relationship_id, outgoing } = await (await author.request.get(configPath, { headers: a.headers })).json()
      const result = await author.request.put(configPath, { headers: a.headers, data: {
        relationship_id, version: outgoing.version, permissions: enabled ? { records: true, names: true, photos: true } : {},
      } })
      expect(result.status()).toBe(200)
    }
    async function upload() {
      const data = await import('node:fs/promises').then(fs => fs.readFile(new URL('oat-biscuits.jpg', fixtures)))
      const response = await author.request.post('/api/v1/media/upload', {
        headers: a.headers, multipart: { file: { name: 'sample.jpg', mimeType: 'image/jpeg', buffer: data } },
      })
      expect(response.status()).toBe(201)
      return (await response.json()).id
    }
    const first = await upload()
    const body = { meal_type: 'breakfast', local_date: day, local_time: '08:15', timezone: 'Asia/Shanghai',
      items: [{ food_name: '网络恢复用例' }], media_ids: [first] }
    const saved = await author.request.post('/api/v1/meals', { data: body,
      headers: { ...a.headers, 'Idempotency-Key': randomUUID() } })
    expect(saved.status()).toBe(201)
    const meal = await saved.json()
    await photoAccess(true)
    const url = '/friends/' + a.id + '/diary?date=' + day
    await reader.goto(url)
    const picture = reader.getByRole('img', { name: '共享照片' })
    await expect(picture).toBeVisible()
    const oldBlob = (await picture.getAttribute('src'))!
    await contexts[1].setOffline(true)
    await expect(reader.getByText(/网络已断开/)).toBeVisible()
    await expect(picture).toHaveCount(0)
    expect(await reader.evaluate(blob => fetch(blob).then(() => false, () => true), oldBlob)).toBe(true)
    await photoAccess(false)
    const onConnect = reader.waitForResponse(response => response.url().endsWith(shared + '/sharing'), { timeout: 6_000 })
    await contexts[1].setOffline(false)
    expect((await onConnect).status()).toBe(200)
    await expect(reader.getByText('这本手账暂未共享。')).toBeVisible()
    await photoAccess(true)
    const obsolete = shared + '/media/' + first + '/thumbnail'
    let releaseRequest = () => {}
    const held = new Promise<void>(resolve => { releaseRequest = resolve })
    await reader.route(request => request.pathname === obsolete, async intercepted => {
      await held
      await intercepted.continue().catch(() => {})
    })
    const requested = reader.waitForRequest(request => new URL(request.url()).pathname === obsolete)
    await reader.getByRole('button', { name: '刷新共享内容' }).click()
    await requested
    const cancelled = reader.waitForEvent('requestfailed', { predicate: request => new URL(request.url()).pathname === obsolete, timeout: 6_000 })
    await reader.evaluate(() => {
      Object.defineProperty(document, 'hidden', { configurable: true, value: true })
      document.dispatchEvent(new Event('visibilitychange'))
    })
    try {
      await cancelled
      await expect(reader.getByText('网络恢复用例', { exact: true })).toHaveCount(0)
      const replacement = await upload()
      const updated = await author.request.patch('/api/v1/meals/' + meal.id, { headers: a.headers,
        data: { ...body, media_ids: [replacement], version: meal.version } })
      expect(updated.status()).toBe(200)
      const onReturn = reader.waitForResponse(response => response.url().endsWith(shared + '/sharing'), { timeout: 6_000 })
      const newImage = reader.waitForResponse(response => new URL(response.url()).pathname === shared + '/media/' + replacement + '/thumbnail')
      await reader.evaluate(() => {
        Reflect.deleteProperty(document, 'hidden')
        document.dispatchEvent(new Event('visibilitychange'))
      })
      expect((await onReturn).status()).toBe(200)
      expect((await newImage).status()).toBe(200)
      await expect(picture).toBeVisible()
    } finally { releaseRequest() }
  } finally { await Promise.all(contexts.map(context => context.close())) }
})
