import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import { mkdir } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { photoFile } from './demo-fixtures'

const date = '2026-11-26'
const password = 'phase-three-browser-fixture'
const coffeeFile = fileURLToPath(new URL('../src/assets/food/coffee.webp', import.meta.url))
const shots = new URL('../../docs/screenshots/phase-3/', import.meta.url)

async function signIn(page: Page, username: string, nickname?: string) {
  if (nickname) {
    await page.goto('/register')
    await page.getByRole('textbox', { name: '昵称', exact: true }).fill(nickname)
    await page.getByLabel('用户名').fill(username)
    await page.getByLabel('密码', { exact: true }).fill(password)
    await page.getByRole('button', { name: '注册', exact: true }).click()
    await expect(page.getByText('账号已创建，请登录。')).toBeVisible()
  } else {
    await page.goto('/login')
  }
  await page.getByLabel('用户名').fill(username)
  await page.getByLabel('密码', { exact: true }).fill(password)
  const result = page.waitForResponse(response => response.url().endsWith('/auth/login') && response.status() === 200)
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page.getByRole('heading', { name: '美食手账' })).toBeVisible()
  return (await (await result).json()).access_token as string
}

async function startForm(page: Page, day = date) {
  await page.goto('/capture?date=' + day)
  await expect(page.getByRole('heading', { name: '记下这一餐' })).toBeVisible()
}

async function fillMeal(page: Page, first: string, second?: string) {
  await page.getByRole('textbox', { name: '食物名称' }).first().fill(first)
  if (second) {
    await page.getByRole('button', { name: '添加另一种食物' }).click()
    await page.getByRole('textbox', { name: '食物名称' }).nth(1).fill(second)
  }
}

const mediaPicker = (page: Page) => page.locator('input[type=file][multiple]')
const mealButton = (page: Page, name: string) => page.getByRole('button', { name: new RegExp('查看记录 .*' + name) })
async function submit(page: Page) {
  await page.getByRole('button', { name: '保存记录' }).click()
  await expect(page.getByRole('heading', { name: '美食手账' })).toBeVisible()
}

async function logout(page: Page) {
  await page.getByRole('navigation', { name: '主导航' }).getByRole('link', { name: '我的' }).click()
  await expect(page.getByRole('button', { name: '退出登录' })).toBeEnabled()
  await page.getByRole('button', { name: '退出登录' }).click()
  await page.getByRole('button', { name: '确认退出' }).click()
  await expect(page.getByRole('heading', { name: '欢迎回来' })).toBeVisible()
}

async function createViaApi(page: Page, access: string, day: string, name: string) {
  const response = await page.request.post('/api/v1/meals', {
    headers: { Authorization: 'Bearer ' + access, 'Idempotency-Key': crypto.randomUUID() },
    data: {
      meal_type: 'lunch', local_date: day, local_time: '12:30', timezone: 'Asia/Shanghai',
      items: [{ food_name: name }],
    },
  })
  expect(response.status()).toBe(201)
}

async function loadedImage(page: Page, alt: string) {
  const photo = page.getByRole('img', { name: alt, exact: true }).first()
  await expect(photo).toBeVisible()
  await expect.poll(async () => photo.evaluate((image: HTMLImageElement) => image.naturalWidth)).toBeGreaterThan(0)
}

test('真实图片和多食物，跨浏览器恢复、编辑迁日与删除同步', async ({ page, browser, baseURL }) => {
  await signIn(page, 'e2e_meals', '手账测试')
  await startForm(page)
  await mediaPicker(page).setInputFiles([photoFile, coffeeFile])
  await loadedImage(page, '待保存的照片 1')
  await loadedImage(page, '待保存的照片 2')
  await fillMeal(page, '咖喱饭', '拿铁')
  await page.getByLabel('这一餐的备注').fill('两张原创示例图')
  await submit(page)
  await expect(mealButton(page, '咖喱饭')).toBeVisible()
  await page.reload()
  await expect(mealButton(page, '拿铁')).toBeVisible()
  await page.getByRole('link', { name: '月历', exact: true }).click()
  await expect(page.getByRole('link', { name: date + ' 有记录' })).toBeVisible()

  const second = await browser.newContext({ baseURL })
  try {
    const sameAccount = await second.newPage()
    await signIn(sameAccount, 'e2e_meals')
    await sameAccount.goto('/?date=' + date)
    await mealButton(sameAccount, '咖喱饭').click()
    await loadedImage(sameAccount, '记录照片')
    await expect(sameAccount.getByRole('dialog')).toContainText('两张原创示例图')
  } finally {
    await second.close()
  }

  await page.getByRole('link', { name: date + ' 有记录' }).click()
  await mealButton(page, '咖喱饭').click()
  await page.getByRole('link', { name: '编辑记录' }).click()
  await expect(page.getByRole('heading', { name: '编辑饮食' })).toBeVisible()
  await page.getByRole('textbox', { name: '食物名称' }).first().fill('热咖喱')
  await page.getByLabel('记录日期').fill('2026-11-27')
  await page.getByRole('button', { name: '移除照片 2' }).click()
  await mediaPicker(page).setInputFiles(coffeeFile)
  await submit(page)
  await expect(page).toHaveURL(/\?date=2026-11-27$/)
  await expect(mealButton(page, '热咖喱')).toBeVisible()
  await page.getByRole('link', { name: '月历', exact: true }).click()
  await expect(page.getByRole('link', { name: date, exact: true })).toBeVisible()
  await page.getByRole('link', { name: '2026-11-27 有记录' }).click()
  await mealButton(page, '热咖喱').click()
  await page.getByRole('button', { name: '删除记录', exact: true }).click()
  await page.getByRole('button', { name: '确认删除' }).click()
  await expect(page.getByRole('heading', { name: '这一页还留白' })).toBeVisible()
  await page.getByRole('link', { name: '月历', exact: true }).click()
  await expect(page.getByRole('link', { name: '2026-11-27', exact: true })).toBeVisible()
})

test('账号切换隔离真实手账与图片', async ({ page }) => {
  await signIn(page, 'e2e_owner', '甲的手账')
  await startForm(page)
  await mediaPicker(page).setInputFiles(photoFile)
  await fillMeal(page, '甲的记录')
  const saved = page.waitForResponse(r => r.url().endsWith('/api/v1/meals') && r.request().method() === 'POST' && r.status() === 201)
  await submit(page)
  const meal = await (await saved).json()
  await logout(page)
  const b = await signIn(page, 'e2e_other', '乙的手账')
  await page.goto('/?date=' + date)
  await expect(page.getByRole('heading', { name: '这一页还留白' })).toBeVisible()
  const headers = { Authorization: 'Bearer ' + b }
  for (const path of ['/meals/' + meal.id, '/media/' + meal.media[0].id, '/media/' + meal.media[0].id + '/thumbnail']) {
    expect((await page.request.get('/api/v1' + path, { headers })).status()).toBe(404)
  }
  await startForm(page)
  await fillMeal(page, '乙的记录')
  await submit(page)
  await expect(mealButton(page, '乙的记录')).toBeVisible()
  await expect(mealButton(page, '甲的记录')).toHaveCount(0)
})

test('照片请求过期后用轮换会话重新获取', async ({ page }) => {
  await signIn(page, 'e2e_photo_refresh', '照片续期')
  await startForm(page)
  await mediaPicker(page).setInputFiles(photoFile)
  await fillMeal(page, '用餐照片')
  let delayed = false
  await page.route('**/api/v1/media/*/thumbnail', async route => {
    if (!delayed) {
      delayed = true
      await new Promise(resolve => setTimeout(resolve, 4400))
    }
    await route.continue()
  })
  const expired = page.waitForResponse(r => r.url().endsWith('/thumbnail') && r.status() === 401)
  const refreshed = page.waitForResponse(r => r.url().endsWith('/thumbnail') && r.status() === 200)
  await submit(page)
  await expired
  await refreshed
  await expect(mealButton(page, '用餐照片').locator('img')).toBeVisible()
})

test('真实写入后回包丢失可安全重试，双击只保存一餐', async ({ page }) => {
  await signIn(page, 'e2e_retry', '重试手账')
  await startForm(page)
  await fillMeal(page, '一笔记录')
  const keys: string[] = []
  const statuses: number[] = []
  await page.route('**/api/v1/meals', async route => {
    if (route.request().method() !== 'POST') return route.continue()
    keys.push(route.request().headers()['idempotency-key'])
    const result = await route.fetch()
    statuses.push(result.status())
    if (keys.length === 1) await route.abort('connectionreset')
    else await route.fulfill({ response: result })
  })
  await page.getByRole('button', { name: '保存记录' }).evaluate(button => {
    (button as HTMLButtonElement).click()
    ;(button as HTMLButtonElement).click()
  })
  await expect(page.getByRole('alert')).toContainText('无法连接 FoodDiary 服务')
  await expect(page.getByRole('textbox', { name: '食物名称' })).toHaveValue('一笔记录')
  await submit(page)
  await expect(mealButton(page, '一笔记录')).toHaveCount(1)
  expect(statuses).toEqual([201, 200])
  expect(keys[0]).toBe(keys[1])
})

test('隐藏热量和营养设置作用到真实手账，手机端和电脑端布局正常', async ({ page }) => {
  const access = await signIn(page, 'e2e_nutrition', '营养显示')
  const result = await page.request.post('/api/v1/meals', {
    headers: { Authorization: 'Bearer ' + access, 'Idempotency-Key': crypto.randomUUID() },
    data: { meal_type: 'lunch', local_date: date, local_time: '12:30', timezone: 'Asia/Shanghai',
      items: [{ food_name: '样例米饭', calories_kcal: 170, protein_g: 4 }] },
  })
  expect(result.status()).toBe(201)
  await page.goto('/?date=' + date)
  await expect(page.getByText('展开营养数据')).toBeVisible()
  await page.getByRole('navigation').getByRole('link', { name: '我的' }).click()
  await page.getByRole('checkbox', { name: '显示热量' }).uncheck()
  await page.getByRole('checkbox', { name: '显示营养成分' }).uncheck()
  await page.getByRole('button', { name: '保存设置' }).click()
  await expect(page.getByText('个人设置已保存。')).toBeVisible()
  for (const [width, height] of [[390, 844], [1440, 900]]) {
    await page.setViewportSize({ width, height })
    await page.goto('/?date=' + date)
    await expect(mealButton(page, '样例米饭')).toBeVisible()
    await expect(page.getByText('展开营养数据')).toHaveCount(0)
    await mealButton(page, '样例米饭').click()
    await expect(page.getByRole('dialog')).toContainText('样例米饭')
    await expect(page.getByRole('dialog').getByText('营养信息', { exact: true })).toHaveCount(0)
    await page.keyboard.press('Escape')
    for (const path of ['/?date=' + date, '/calendar?date=' + date, '/capture?date=' + date]) {
      await page.goto(path)
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    }
  }
})

test('快速切日期丢弃旧响应，另一标签页登录清除旧账号', async ({ page, context }) => {
  const b = await context.newPage()
  await b.goto('/register')
  await b.getByRole('textbox', { name: '昵称', exact: true }).fill('第二个标签')
  await b.getByLabel('用户名').fill('e2e_tab_b')
  await b.getByLabel('密码', { exact: true }).fill(password)
  await b.getByRole('button', { name: '注册', exact: true }).click()
  await expect(b.getByText('账号已创建，请登录。')).toBeVisible()

  const aToken = await signIn(page, 'e2e_tab_a', '第一个标签')
  await createViaApi(page, aToken, '2026-11-24', '较早的记录')
  await createViaApi(page, aToken, '2026-11-25', '较新的记录')
  let delayed = false
  await page.route('**/api/v1/meals?**', async route => {
    if (route.request().url().includes('2026-11-24')) {
      delayed = true
      await new Promise(resolve => setTimeout(resolve, 700))
    }
    try { await route.continue() } catch { /* the date change may already cancel this request */ }
  })
  await page.goto('/?date=' + date)
  await page.getByRole('button', { name: '2026-11-24' }).click()
  await expect.poll(() => delayed).toBe(true)
  await page.getByRole('button', { name: '2026-11-25' }).click()
  await expect(mealButton(page, '较新的记录')).toBeVisible()
  await expect(mealButton(page, '较早的记录')).toHaveCount(0)

  await b.getByLabel('用户名').fill('e2e_tab_b')
  await b.getByLabel('密码', { exact: true }).fill(password)
  await b.getByRole('button', { name: '登录', exact: true }).click()
  await expect(b.getByRole('heading', { name: '这一页还留白' })).toBeVisible()
  await expect(page.getByRole('heading', { name: '欢迎回来' })).toBeVisible()
  await expect(mealButton(page, '较新的记录')).toHaveCount(0)
  await page.reload()
  await expect(page.getByRole('heading', { name: '欢迎回来' })).toBeVisible()
  await expect(page.getByText('登录状态已变更，请重新确认当前账号。')).toBeVisible()
  await b.reload()
  await expect(b.getByRole('heading', { name: '这一页还留白' })).toBeVisible()
})

async function capture(page: Page, name: string, fullPage = false) {
  await mkdir(fileURLToPath(shots), { recursive: true })
  await page.evaluate(() => document.fonts.ready.then(() => undefined))
  await page.screenshot({
    path: fileURLToPath(new URL(name + '.jpg', shots)), type: 'jpeg', quality: 86, animations: 'disabled', fullPage,
  })
}

test('@screenshots 真实手账、表单、月历、详情与隔离账号', async ({ page, browser, baseURL }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await signIn(page, 'shots_meals_a', '小禾')
  await page.goto('/?date=' + date)
  await expect(page.getByRole('heading', { name: '这一页还留白' })).toBeVisible()
  await capture(page, '01-empty')
  await startForm(page)
  await mediaPicker(page).setInputFiles([photoFile, coffeeFile])
  await loadedImage(page, '待保存的照片 2')
  await capture(page, '02-photo-preview')
  await fillMeal(page, '日式咖喱饭', '燕麦拿铁')
  await page.getByText('营养信息与食物备注', { exact: true }).first().click()
  await page.getByLabel('热量 (kcal)', { exact: true }).first().fill('470')
  await page.getByLabel('蛋白质 (g)', { exact: true }).first().fill('14.5')
  await page.getByLabel('这一餐的备注').fill('午休时给自己留了一点时间。')
  await capture(page, '03-multiple-foods', true)
  await submit(page)
  await expect(mealButton(page, '日式咖喱饭').locator('img')).toHaveCount(2)
  await capture(page, '04-desktop-saved')
  await page.getByRole('link', { name: '月历', exact: true }).click()
  await expect(page.getByRole('link', { name: date + ' 有记录' }).locator('img')).toBeVisible()
  await capture(page, '05-calendar', true)
  await page.getByRole('link', { name: date + ' 有记录' }).click()
  await mealButton(page, '日式咖喱饭').click()
  await loadedImage(page, '记录照片')
  await capture(page, '06-detail')
  await page.getByRole('link', { name: '编辑记录' }).click()
  await expect(page.getByRole('textbox', { name: '食物名称' }).first()).toHaveValue('日式咖喱饭')
  await expect(page.getByRole('img', { name: '已有照片 1' })).toBeVisible()
  await capture(page, '07-edit', true)
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/?date=' + date)
  await expect(mealButton(page, '日式咖喱饭').locator('img').first()).toBeVisible()
  await capture(page, '08-mobile')
  await page.setViewportSize({ width: 1440, height: 900 })
  const summary = page.getByText('展开营养数据', { exact: true })
  const nutrition = page.locator('details').filter({ has: summary })
  await summary.click()
  await expect(nutrition.getByText('470 kcal')).toBeVisible()
  await capture(page, '09-account-a')
  const second = await browser.newContext({ baseURL, viewport: { width: 1440, height: 900 } })
  try {
    const b = await second.newPage()
    await signIn(b, 'shots_meals_b', '阿松')
    await startForm(b)
    await fillMeal(b, '清汤面')
    await b.getByLabel('这一餐的备注').fill('今天的晚饭简单一点。')
    await submit(b)
    await expect(mealButton(b, '清汤面')).toBeVisible()
    await expect(mealButton(b, '日式咖喱饭')).toHaveCount(0)
    await capture(b, '10-account-b')
  } finally {
    await second.close()
  }
})
