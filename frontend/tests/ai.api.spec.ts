import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import { mkdir } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import type { AiJob } from '../src/api/aiRepository'
import { photoFile } from './demo-fixtures'

const base = '/api/v1'
const date = '2026-11-26'
const password = 'phase-four-browser-fixture'
const tomato = fileURLToPath(new URL('../src/assets/food/tomato-eggs.webp', import.meta.url))
const rice = fileURLToPath(new URL('../src/assets/food/fried-rice.webp', import.meta.url))
const shots = new URL('../../docs/screenshots/phase-4/', import.meta.url)
const foods = (page: Page) => page.getByRole('textbox', { name: '食物名称' })
const select = (page: Page) => page.locator('input[type=file][multiple]')
const start = (page: Page) => page.getByRole('button', { name: 'AI 识别', exact: true })
const confirm = (page: Page) => page.getByRole('button', { name: '同意并识别' })

async function signIn(page: Page, username: string, nickname = '小禾') {
  await page.goto('/login')
  const origin = new URL(page.url()).origin
  const result = await page.request.post(base + '/auth/register', {
    headers: { Origin: origin, 'X-FoodDiary-Intent': 'browser' },
    data: { username, nickname, password },
  })
  expect(result.status()).toBe(201)
  await page.getByLabel('用户名').fill(username)
  await page.getByLabel('密码', { exact: true }).fill(password)
  const login = page.waitForResponse(response => response.url().endsWith('/auth/login') && response.status() === 200)
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page.getByRole('heading', { name: '美食手账' })).toBeVisible()
  return (await (await login).json()).access_token as string
}

async function openForm(page: Page, photos = [tomato, rice]) {
  await page.goto('/capture?date=' + date)
  await expect(page.getByRole('heading', { name: '记下这一餐' })).toBeVisible()
  if (photos.length) await select(page).setInputFiles(photos)
}

const started = (page: Page) => page.waitForResponse(response =>
  response.url().endsWith('/ai/jobs') && response.request().method() === 'POST' && response.status() === 202,
)

async function recognize(page: Page) {
  await start(page).click()
  await expect(page.getByRole('dialog')).toBeVisible()
  const result = started(page)
  await confirm(page).click()
  return await (await result).json() as AiJob
}

async function save(page: Page, food: string) {
  const response = page.waitForResponse(value => value.url().endsWith('/meals') &&
    value.request().method() === 'POST' && value.status() === 201)
  await page.getByRole('button', { name: '保存记录' }).click()
  await expect(page.getByRole('button', { name: new RegExp('查看记录 .*' + food) })).toBeVisible()
  return await (await response).json()
}

async function logout(page: Page) {
  await page.getByRole('navigation', { name: '主导航' }).getByRole('link', { name: '我的' }).click()
  await page.getByRole('button', { name: '退出登录' }).click()
  await page.getByRole('button', { name: '确认退出' }).click()
  await expect(page.getByRole('heading', { name: '欢迎回来' })).toBeVisible()
}

async function chooseInvalidFixture(page: Page) {
  const png = await page.evaluate(() => {
    const canvas = document.createElement('canvas')
    canvas.width = canvas.height = 96
    const context = canvas.getContext('2d')!
    context.fillStyle = '#0000ff'
    context.fillRect(0, 0, 96, 96)
    return canvas.toDataURL('image/png').split(',')[1]
  })
  await select(page).setInputFiles({ name: 'synthetic-blue.png', mimeType: 'image/png', buffer: Buffer.from(png, 'base64') })
}

test('AI 未配置时原有真实手账可拍照和手动保存', async ({ page }) => {
  await signIn(page, 'ai_disabled')
  await openForm(page, [photoFile])
  await expect(page.getByText('AI 识别暂不可用，你仍可以手动记录。')).toBeVisible()
  await expect(start(page)).toHaveCount(0)
  await foods(page).first().fill('手动咖喱饭')
  expect((await save(page, '手动咖喱饭')).items[0].source).toBe('manual')
})

test('@fake-ai 选择部分图片、授权、双击只创建一次、修改候选并保存', async ({ page }) => {
  await signIn(page, 'ai_happy')
  await openForm(page)
  await page.getByRole('checkbox', { name: '识别照片 2' }).uncheck()
  const writes: string[] = []
  page.on('request', request => {
    if (request.method() === 'POST') writes.push(new URL(request.url()).pathname)
  })
  await start(page).click()
  await expect(page.getByText('本地模拟会使用示例结果')).toBeVisible()
  expect(writes).toHaveLength(0)
  const result = started(page)
  await confirm(page).dblclick()
  const job = await (await result).json()
  expect(job.simulated).toBe(true)
  await expect(page.getByText('正在看看你今天吃了什么……')).toBeVisible()
  await expect(foods(page).nth(1)).toHaveValue('白米饭')
  expect(writes.filter(path => path === base + '/ai/jobs')).toHaveLength(1)
  expect(writes.filter(path => path === base + '/media/upload')).toHaveLength(1)
  await foods(page).nth(1).fill('杂粮饭')
  const meal = await save(page, '杂粮饭')
  expect(meal.media).toHaveLength(2)
  expect(meal.items.map((item: { source: string }) => item.source)).toEqual(['ai', 'ai_edited'])
  expect(meal.items[1].ai_job_id).toBe(job.id)
  await page.getByRole('link', { name: '月历' }).click()
  await expect(page.getByRole('heading', { name: '饮食月历' })).toBeVisible()
})

test('@fake-ai 等待期间填写的人工内容保留并可追加', async ({ page }) => {
  await signIn(page, 'ai_manual_keep')
  await openForm(page)
  await recognize(page)
  await foods(page).first().fill('凉拌黄瓜')
  await page.getByLabel('这一餐的备注').fill('中午的便当')
  await expect(page.getByText('找到了 2 样美食')).toBeVisible()
  await expect(foods(page)).toHaveCount(1)
  await page.getByRole('button', { name: '追加到表单' }).click()
  await expect(foods(page)).toHaveCount(3)
  await expect(foods(page).first()).toHaveValue('凉拌黄瓜')
  await expect(page.getByLabel('这一餐的备注')).toHaveValue('中午的便当')
  expect((await save(page, '凉拌黄瓜')).items[0].source).toBe('manual')
})

test('@fake-ai 模型输出失败降级并计入额度', async ({ page }) => {
  await signIn(page, 'ai_failed')
  await openForm(page, [])
  await chooseInvalidFixture(page)
  await recognize(page)
  await expect(page.getByText('这次识别结果无法使用，你仍可以手动记录。')).toBeVisible()
  await foods(page).first().fill('手动记热茶')
  await save(page, '手动记热茶')
  await openForm(page)
  await start(page).click()
  await confirm(page).click()
  await expect(page.getByText('今天的识别额度已用完，仍可手动记录。')).toBeVisible()
})

test('@fake-ai 用户取消后停止轮询并保存手动记录', async ({ page }) => {
  await signIn(page, 'ai_cancel')
  await openForm(page)
  await recognize(page)
  await page.getByRole('button', { name: '取消识别' }).click()
  await expect(page.getByText('识别已取消。已发送的模型请求可能仍会完成。')).toBeVisible()
  await expect(foods(page).first()).toHaveValue('')
  await foods(page).first().fill('午餐手动记录')
  await save(page, '午餐手动记录')
})

test('@fake-ai 创建回包丢失后以原幂等标识只读恢复任务', async ({ page }) => {
  await signIn(page, 'ai_network_retry')
  await openForm(page, [tomato])
  const path = '**/api/v1/ai/jobs'
  let recovered: AiJob | undefined
  let writes = 0
  page.on('request', request => {
    if (request.method() === 'POST' && request.url().endsWith('/ai/jobs')) writes++
  })
  await page.route(path, async route => {
    const response = await route.fetch()
    expect(response.status()).toBe(202)
    recovered = await response.json() as AiJob
    await route.abort('failed')
  }, { times: 1 })
  await start(page).click()
  const lookup = page.waitForResponse(response => response.url().includes('/ai/jobs/recover?request_key='))
  await confirm(page).click()
  const replay = await (await lookup).json()
  expect(replay.id).toBe(recovered?.id)
  await expect(foods(page).nth(1)).toHaveValue('白米饭')
  expect(writes).toBe(1)
})

test('@fake-ai 更换照片时拒绝应用已经在途的旧结果', async ({ page }) => {
  await signIn(page, 'ai_replace_photo')
  await openForm(page)
  const job = await recognize(page)
  const cancelled = page.waitForResponse(response => response.url().endsWith('/ai/jobs/' + job.id + '/cancel'))
  await page.getByRole('button', { name: '移除照片 1' }).click()
  expect((await (await cancelled).json()).status).toBe('cancelled')
  await select(page).setInputFiles(photoFile)
  await expect(foods(page)).toHaveCount(1)
  await expect(foods(page).first()).toHaveValue('')
  await expect(page.getByText('已填入食物。', { exact: false })).toHaveCount(0)
})

test('@fake-ai 切换账户后旧任务及候选不进入新表单', async ({ page }) => {
  await signIn(page, 'ai_switch_a', '甲')
  await openForm(page)
  const job = await recognize(page)
  await logout(page)
  const token = await signIn(page, 'ai_switch_b', '乙')
  await openForm(page, [photoFile])
  await expect(foods(page).first()).toHaveValue('')
  await expect(page.getByText('番茄炒蛋')).toHaveCount(0)
  const response = await page.request.get(base + '/ai/jobs/' + job.id, { headers: { Authorization: 'Bearer ' + token } })
  expect(response.status()).toBe(404)
  await expect(start(page)).toBeEnabled()
})

test('@fake-ai 移动端显示授权、等待及候选且无横向溢出', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await signIn(page, 'ai_mobile')
  await openForm(page, [tomato])
  await recognize(page)
  await expect(foods(page).nth(1)).toHaveValue('白米饭')
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390)
  await expect(page.getByText('模拟估算', { exact: false }).first()).toBeVisible()
})

async function shot(page: Page, filename: string, fullPage = true) {
  await page.evaluate(async () => document.fonts.ready)
  await page.screenshot({ path: fileURLToPath(new URL(filename, shots)), fullPage,
    type: 'jpeg', quality: 84, animations: 'disabled' })
}

test('@fake-ai @screenshots 私有图片、识别授权、等待、修改、降级及移动端', async ({ page }) => {
  await mkdir(shots, { recursive: true })
  await page.setViewportSize({ width: 1280, height: 860 })
  await signIn(page, 'ai_shot_main')
  await openForm(page)
  await expect(page.getByText('本地模拟识别 · 使用示例结果')).toBeVisible()
  await shot(page, '01-simulated-photo-selection.jpg')
  await start(page).click()
  await expect(page.getByRole('dialog')).toBeVisible()
  await shot(page, '02-simulated-consent.jpg', false)
  const queued = started(page)
  await confirm(page).click()
  await queued
  await expect(page.getByText('正在看看你今天吃了什么……')).toBeVisible()
  await expect(page.getByRole('button', { name: '取消识别' })).toBeVisible()
  await shot(page, '03-simulated-waiting.jpg')
  await expect(foods(page).nth(1)).toHaveValue('白米饭')
  await shot(page, '04-simulated-candidates.jpg')
  await foods(page).nth(1).fill('杂粮饭')
  await page.getByText('营养信息与食物备注').nth(1).click()
  await page.getByLabel('重量 (g)').last().fill('130')
  await shot(page, '05-simulated-edited.jpg')
  await save(page, '杂粮饭')
  await page.getByRole('button', { name: /查看记录 .*杂粮饭/ }).click()
  await expect(page.getByText('模拟估算', { exact: true }).first()).toBeVisible()
  const privatePhotos = page.getByRole('dialog').locator('img')
  await expect(privatePhotos).toHaveCount(2)
  await expect.poll(() => privatePhotos.evaluateAll(images => images.every(image => (image as HTMLImageElement).naturalWidth > 0))).toBe(true)
  await shot(page, '06-saved-private-diary.jpg', false)
  await openForm(page)
  await start(page).click()
  await confirm(page).click()
  await expect(page.getByText('今天的识别额度已用完，仍可手动记录。')).toBeVisible()
  await shot(page, '08-simulated-quota.jpg')
  await logout(page)
  await signIn(page, 'ai_shot_failure')
  await openForm(page, [])
  await chooseInvalidFixture(page)
  await recognize(page)
  await expect(page.getByText('这次识别结果无法使用，你仍可以手动记录。')).toBeVisible()
  await shot(page, '07-simulated-manual-fallback.jpg')
  await logout(page)
  await page.setViewportSize({ width: 390, height: 844 })
  await signIn(page, 'ai_shot_mobile')
  await openForm(page, [tomato])
  await recognize(page)
  await expect(foods(page).nth(1)).toHaveValue('白米饭')
  await shot(page, '09-simulated-mobile.jpg', false)
  await foods(page).first().scrollIntoViewIfNeeded()
  await shot(page, '11-simulated-mobile-foods.jpg', false)
})

test('@fake-ai @screenshots 百炼隐私说明通过受控能力响应检查，无模型调用', async ({ page }) => {
  await mkdir(shots, { recursive: true })
  await page.setViewportSize({ width: 1280, height: 860 })
  await signIn(page, 'ai_shot_privacy')
  await page.route('**/api/v1/ai/capabilities', async route => {
    const response = await route.fetch()
    await route.fulfill({ response, json: {
      ...await response.json(), simulated: false,
      privacy_url: 'https://www.alibabacloud.com/help/en/model-studio/privacy-notice',
    } })
  })
  await openForm(page, [tomato])
  let writes = 0
  page.on('request', request => { if (request.method() === 'POST') writes++ })
  await start(page).click()
  await expect(page.getByText('所选食物照片将发送至阿里云百炼', { exact: false })).toBeVisible()
  await expect(page.getByRole('link', { name: '查看服务商的隐私说明' })).toHaveAttribute('href', /model-studio\/privacy-notice$/)
  await shot(page, '10-qwen-consent-ui-check.jpg', false)
  await page.getByRole('button', { name: '先手动记录' }).click()
  expect(writes).toBe(0)
})

const recoveryShots = new URL('../../docs/screenshots/phase-4.1/', import.meta.url)
async function recoveryShot(page: Page, name: string) {
  await mkdir(recoveryShots, { recursive: true })
  await page.setViewportSize({ width: 1280, height: 920 })
  await page.evaluate(async () => document.fonts.ready)
  await page.screenshot({ path: fileURLToPath(new URL(name + '.jpg', recoveryShots)),
    fullPage: false, type: 'jpeg', quality: 84, animations: 'disabled' })
}

test('@fake-ai @phase41 刷新和关闭标签页后恢复原照片，候选须显式采用', async ({ page, context }) => {
  await signIn(page, 'ai41_refresh')
  await openForm(page, [tomato])
  await recognize(page)
  await page.reload()
  await expect(page.getByRole('button', { name: '恢复这次识别' })).toBeVisible()
  await expect(foods(page).first()).toHaveValue('')
  await recoveryShot(page, '01-restore-after-reload')
  await page.close()
  const reopened = await context.newPage()
  await openForm(reopened, [])
  await reopened.getByRole('button', { name: '恢复这次识别' }).click()
  await expect(reopened.getByText('找到了 2 样美食')).toBeVisible()
  await expect(foods(reopened).first()).toHaveValue('')
  const restoredPhoto = reopened.getByRole('img', { name: '已有照片 1' })
  await expect(restoredPhoto).toBeVisible()
  await expect.poll(() => restoredPhoto.evaluate(image => (image as HTMLImageElement).naturalWidth)).toBeGreaterThan(0)
  await recoveryShot(reopened, '02-recovered-before-apply')
  await reopened.getByRole('button', { name: '追加到表单' }).click()
  expect((await save(reopened, '白米饭')).items[1].source).toBe('ai')
})

test('@fake-ai @phase41 网络中断后只恢复轮询，保留一次创建', async ({ page }) => {
  await signIn(page, 'ai41_network')
  await openForm(page, [tomato])
  let writes = 0
  page.on('request', request => {
    if (request.method() === 'POST' && request.url().endsWith('/ai/jobs')) writes++
  })
  await page.route(/\/ai\/jobs\/[a-f0-9-]{36}$/, route => route.abort('failed'), { times: 1 })
  await recognize(page)
  await expect(page.getByText('连接暂时中断，正在重新查看任务。')).toBeVisible()
  await expect(foods(page).nth(1)).toHaveValue('白米饭')
  expect(writes).toBe(1)
})

test('@fake-ai @phase41 重试回包丢失后按原重试标识恢复', async ({ page }) => {
  await signIn(page, 'ai41_retry')
  await openForm(page, [])
  await chooseInvalidFixture(page)
  const job = await recognize(page)
  await expect(page.getByText('这次识别结果无法使用，你仍可以手动记录。')).toBeVisible()
  let writes = 0
  await page.route('**/ai/jobs/' + job.id + '/retry', async route => {
    writes++
    expect((await route.fetch()).status()).toBe(202)
    await route.abort('failed')
  })
  await page.getByRole('button', { name: '重试识别' }).click()
  const recovered = page.waitForResponse(response => response.url().includes('retry_key='))
  await page.getByRole('button', { name: '同意并重试' }).click()
  expect((await (await recovered).json()).id).toBe(job.id)
  await expect(page.getByText('这次识别结果无法使用，你仍可以手动记录。')).toBeVisible()
  expect(writes).toBe(1)
})

test('@fake-ai @phase41 更换识别输入后保留文本，删除输入解除草稿来源', async ({ page }) => {
  await signIn(page, 'ai41_media')
  await openForm(page, [tomato])
  await recognize(page)
  await expect(foods(page).nth(1)).toHaveValue('白米饭')
  await page.getByRole('button', { name: '移除照片 1' }).click()
  await expect(foods(page).nth(1)).toHaveValue('白米饭')
  await expect(page.getByText('模拟估算', { exact: false })).toHaveCount(0)
  expect((await save(page, '白米饭')).items.map((item: { source: string }) => item.source)).toEqual(['manual', 'manual'])
})

test('@fake-ai @phase41 连续识别需明确替换，零值和人工修正在手账中可见', async ({ page }) => {
  await signIn(page, 'ai41_repeat')
  await openForm(page, [tomato])
  await recognize(page)
  await expect(foods(page).nth(1)).toHaveValue('白米饭')
  await foods(page).first().fill('原来的名称')
  await page.getByRole('button', { name: '重新识别' }).click()
  await confirm(page).click()
  await expect(page.getByText('找到了 2 样美食')).toBeVisible()
  await expect(foods(page).first()).toHaveValue('原来的名称')
  await page.getByRole('button', { name: '替换食物明细' }).click()
  await expect(foods(page).first()).toHaveValue('番茄炒蛋')
  await page.getByText('营养信息与食物备注').nth(1).click()
  await page.getByLabel('热量 (kcal)').last().fill('0')
  await page.getByLabel('分类').last().fill('自定义')
  expect((await save(page, '白米饭')).items[1].source).toBe('ai_edited')
  await page.getByText('展开营养数据').click()
  await expect(page.getByText('含人工修正', { exact: false }).first()).toBeVisible()
  await page.getByRole('button', { name: /查看记录 .*白米饭/ }).click()
  const item = page.getByRole('dialog').getByRole('article').last()
  await expect(item.getByText('已人工修正', { exact: false })).toBeVisible()
  await item.getByText('营养信息').click()
  await expect(item.getByText('热量 0 kcal')).toBeVisible()
  await recoveryShot(page, '03-manually-edited-nutrition')
})

test('@fake-ai @phase41 @offline Worker 未启动时显示状态，仍可手动保存', async ({ page }) => {
  await signIn(page, 'ai41_offline')
  await openForm(page, [tomato])
  await expect(page.getByText('识别服务暂未连接，可以继续手动记录。')).toBeVisible()
  await expect(start(page)).toBeDisabled()
  await recoveryShot(page, '04-worker-offline-manual')
  await foods(page).first().fill('离线服务下手动记')
  expect((await save(page, '离线服务下手动记')).items[0].source).toBe('manual')
})
