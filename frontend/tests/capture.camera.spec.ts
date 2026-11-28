import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import { fileURLToPath } from 'node:url'
import { join } from 'node:path'

const evidence = process.env.FOODDIARY_CAMERA_EVIDENCE!
const photo = fileURLToPath(new URL('../../docs/ai-benchmark/images/homestyle-lunch.jpg', import.meta.url))
const password = 'camera-playwright-fixture-only'
const shutter = (page: Page) => page.getByRole('button', { name: '按下快门' })
const known = (path: string, method: string, request: { url(): string; method(): string }) =>
  new URL(request.url()).pathname === '/api/v1' + path && request.method() === method
const screen = (page: Page, name: string) => page.screenshot({ path: join(evidence, name + '.png'), scale: 'css' })

async function login(page: Page) {
  const username = 'camera' + crypto.randomUUID().slice(0, 8)
  await page.goto('/login')
  const browser = { Origin: new URL(page.url()).origin, 'X-FoodDiary-Intent': 'browser' }
  const result = await page.request.post('/api/v1/auth/register', {
    headers: browser,
    data: { username, nickname: '相机测试', password },
  })
  expect(result.status()).toBe(201)
  const session = await page.request.post('/api/v1/auth/login', { headers: browser, data: { username, password } })
  expect(session.ok()).toBeTruthy()
  await page.evaluate(() => sessionStorage.removeItem('fooddiary.api.identity-paused'))
  await page.goto('/')
  await expect(page.getByRole('heading', { name: '美食手账' })).toBeVisible()
  const { access_token: token, user: { public_id: id } } = await session.json()
  return { id, headers: { Authorization: 'Bearer ' + token } }
}

async function open(page: Page) {
  await page.getByRole('link', { name: '拍照', exact: true }).click()
  await expect(page.getByRole('dialog', { name: '拍下这一餐' })).toBeVisible()
}

async function monitor(page: Page) {
  await page.addInitScript(() => {
    const records: { requested: MediaStreamConstraints | undefined; tracks: MediaStreamTrack[] }[] = []
    Object.defineProperty(window, 'cameraRecords', { value: records })
    const get = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices)
    navigator.mediaDevices.getUserMedia = async requested => {
      const stream = await get(requested)
      records.push({ requested, tracks: stream.getTracks() })
      return stream
    }
  })
}

const trackStates = (page: Page) => page.evaluate(() => {
  const records = (window as unknown as { cameraRecords: { requested: MediaStreamConstraints; tracks: MediaStreamTrack[] }[] }).cameraRecords
  return records.map(({ requested, tracks }) => ({
    audio: requested.audio, facing: (requested.video as MediaTrackConstraints).facingMode,
    tracks: tracks.map(track => track.readyState),
  }))
})

test('A 实时预览、照片上传和 CPU ONNX 真轮廓', async ({ page }) => {
  await monitor(page)
  await login(page)
  let uploads = 0
  let jobs = 0
  page.on('request', request => {
    if (known('/media/upload', 'POST', request)) uploads++
    if (known('/stickers/jobs', 'POST', request)) jobs++
  })
  const start = Date.now()
  await open(page)
  await expect(shutter(page)).toBeEnabled()
  const previewMs = Date.now() - start
  await expect(page.locator('video')).toBeVisible()
  expect(await page.locator('video').evaluate((video: HTMLVideoElement) => ({ width: video.videoWidth, playing: !video.paused })))
    .toEqual({ width: 640, playing: true })
  expect(await trackStates(page)).toEqual([{ audio: false, facing: { ideal: 'environment' }, tracks: ['live'] }])
  expect(uploads).toBe(0)
  await screen(page, '01-preview')
  const uploaded = page.waitForResponse(response => known('/media/upload', 'POST', response.request()))
  const sticker = page.waitForResponse(response => /\/sticker$/.test(new URL(response.url()).pathname))
  const captureTime = Date.now()
  await shutter(page).tap()
  const frozen = page.getByRole('img', { name: '刚刚拍下的照片' })
  await expect(frozen).toBeVisible()
  const capturedBlob = await frozen.evaluate(async node => {
    const blob = await (await fetch((node as HTMLImageElement).src)).blob()
    return { bytes: blob.size, type: blob.type }
  })
  expect(capturedBlob.type).toBe('image/jpeg')
  expect(capturedBlob.bytes).toBeGreaterThan(1000)
  await screen(page, '02-captured')
  const response = await uploaded
  expect(response.status()).toBe(201)
  const { id, width, height, content_type: contentType } = await response.json()
  expect({ width, height, contentType }).toEqual({ width: 640, height: 480, contentType: 'image/webp' })
  const { bytes } = capturedBlob
  const uploadMs = Date.now() - captureTime
  await expect.poll(() => trackStates(page)).toEqual([{ audio: false, facing: { ideal: 'environment' }, tracks: ['ended'] }])
  await expect(page.getByText('AI 识别暂不可用，你仍可以手动记录。')).toBeVisible()
  if (await page.getByText('正在把美食剪下来…').isVisible()) await screen(page, '03-extracting')
  const stickerResponse = await sticker
  expect(stickerResponse.ok()).toBeTruthy()
  expect(new URL(stickerResponse.url()).pathname).toContain(id)
  const workerEnd = Date.now()
  const outline = page.locator('.cutout-outline img')
  await expect(outline).toHaveAttribute('src', /^blob:/)
  await page.waitForFunction(() => {
    const layer = document.querySelector('.cutout-outline')
    return layer && Number(getComputedStyle(layer).opacity) > .5
  }, undefined, { timeout: 3000 })
  expect(await outline.evaluate(async node => {
    const image = node as HTMLImageElement
    const canvas = document.createElement('canvas')
    canvas.width = image.naturalWidth; canvas.height = image.naturalHeight
    const context = canvas.getContext('2d')!
    context.drawImage(image, 0, 0)
    const data = context.getImageData(0, 0, canvas.width, canvas.height).data
    return data.some((value, index) => index % 4 === 3 && value === 0)
      && data.some((value, index) => index % 4 === 3 && value === 255)
  })).toBe(true)
  await screen(page, '04-real-outline')
  await expect(page.locator('.capture-stage')).toHaveAttribute('data-stage', 'ready')
  await screen(page, '05-final-sticker')
  expect({ uploads, jobs }).toEqual({ uploads: 1, jobs: 1 })
  console.log(JSON.stringify({ previewMs, captureToUploadMs: uploadMs, captureToStickerMs: workerEnd - captureTime, bytes }))
})

test('B 保存失败保持草稿，恢复后只创建一餐并播放入账', async ({ page }) => {
  await login(page)
  await open(page)
  await expect(shutter(page)).toBeEnabled()
  await shutter(page).tap()
  await expect(page.locator('.capture-stage')).toHaveAttribute('data-stage', 'ready')
  await page.getByRole('textbox', { name: '食物名称' }).first().fill('家常三菜')
  let attempts = 0
  await page.route('**/api/v1/meals', route => {
    if (route.request().method() !== 'POST') return route.continue()
    attempts++
    if (attempts === 1) return route.abort('internetdisconnected')
    return route.continue()
  })
  const save = page.getByRole('button', { name: '贴进手账' })
  await save.click()
  await expect(page.getByRole('alert')).toBeVisible()
  await expect(page.locator('.landing-sticker')).toHaveCount(0)
  await expect(page.getByRole('img', { name: '美食贴纸预览' })).toBeVisible()
  await save.evaluate(element => { (element as HTMLButtonElement).click(); (element as HTMLButtonElement).click() })
  await expect(page.locator('.landing-sticker')).toBeVisible()
  await screen(page, '06-sticker-landing')
  await expect(page.locator('.landing-sticker')).toHaveCount(0)
  const entry = page.getByRole('button', { name: '查看记录 家常三菜' })
  await expect(entry).toHaveCount(1)
  await expect(entry.locator('[data-sticker]')).toBeVisible()
  await page.reload()
  await expect(entry.locator('[data-sticker]')).toBeVisible()
  expect(attempts).toBe(2)
})

test('C 权限拒绝后相册可用，减少动态效果并持久化原图', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.addInitScript(() => {
    navigator.mediaDevices.getUserMedia = async () => { throw new DOMException('denied', 'NotAllowedError') }
  })
  await login(page)
  await open(page)
  await expect(page.getByText('相机权限未开启', { exact: false })).toBeVisible()
  await expect(page.getByRole('button', { name: '使用系统相机' })).toBeVisible()
  await screen(page, '07-permission-denied')
  await page.locator('input[aria-label="从相册选择"]').setInputFiles(photo)
  await expect(page.locator('.capture-stage')).toHaveAttribute('data-stage', 'ready')
  await expect(page.locator('.cutout-outline')).toHaveCount(0)
  await page.getByRole('button', { name: '使用原图' }).click()
  await expect(page.locator('.capture-stage')).toHaveAttribute('data-stage', 'original')
  await page.getByRole('textbox', { name: '食物名称' }).first().fill('只有原图')
  await page.getByRole('button', { name: '贴进手账' }).click()
  const entry = page.getByRole('button', { name: '查看记录 只有原图' })
  await expect(entry).toBeVisible()
  await page.reload()
  await expect(entry.locator('img')).toBeVisible()
  await expect(entry.locator('[data-sticker]')).toHaveCount(0)
})

test('切换、后台暂停、重新拍摄和退出时释放相机并隔离照片', async ({ page }) => {
  await monitor(page)
  await login(page)
  await open(page)
  await expect(shutter(page)).toBeEnabled()
  await page.getByRole('button', { name: '切换摄像头' }).click()
  await expect(shutter(page)).toBeEnabled()
  await expect.poll(() => trackStates(page)).toEqual([
    { audio: false, facing: { ideal: 'environment' }, tracks: ['ended'] },
    { audio: false, facing: { ideal: 'user' }, tracks: ['live'] },
  ])
  await page.evaluate(() => {
    Object.defineProperty(document, 'hidden', { configurable: true, get: () => true })
    document.dispatchEvent(new Event('visibilitychange'))
  })
  await expect(page.getByText('相机已暂停。')).toBeVisible()
  expect((await trackStates(page)).at(-1)?.tracks).toEqual(['ended'])
  await page.evaluate(() => Reflect.deleteProperty(document, 'hidden'))
  await page.getByRole('button', { name: '继续取景' }).click()
  await expect(shutter(page)).toBeEnabled()
  await shutter(page).tap()
  await expect(page.locator('.capture-stage')).toBeVisible()
  await page.getByRole('button', { name: '重新拍摄' }).click()
  await expect(shutter(page)).toBeEnabled()
  await expect(page.locator('.capture-stage')).toHaveCount(0)
  await page.evaluate(() => {
    const channel = new BroadcastChannel('fooddiary-api-identity')
    channel.postMessage({ type: 'login' }); channel.close()
  })
  await expect(page.getByRole('button', { name: '登录', exact: true })).toBeVisible()
  expect((await trackStates(page)).every(value => value.tracks.every(state => state === 'ended'))).toBe(true)
  await login(page)
  await expect(page.locator('.capture-stage')).toHaveCount(0)
})

test('无摄像头时可关闭相机并进入独立手动记录', async ({ page }) => {
  await page.addInitScript(() => {
    navigator.mediaDevices.getUserMedia = async () => { throw new DOMException('missing', 'NotFoundError') }
  })
  await login(page)
  await open(page)
  await expect(page.getByText('没有找到可用的摄像头。')).toBeVisible()
  await page.getByRole('button', { name: '关闭相机' }).click()
  await expect(page.getByRole('heading', { name: '美食手账' })).toBeVisible()
  await open(page)
  await page.getByRole('button', { name: '手动记录' }).click()
  await expect(page.getByRole('textbox', { name: '食物名称' }).first()).toBeFocused()
})

test('上传中断后恢复、跳过特效，并在贴纸处理中保存', async ({ page }) => {
  await login(page)
  let uploads = 0
  let jobs = 0
  await page.route('**/api/v1/media/upload', route => {
    uploads++
    return uploads === 1 ? route.abort('internetdisconnected') : route.continue()
  })
  page.on('request', request => { if (known('/stickers/jobs', 'POST', request)) jobs++ })
  await open(page)
  await expect(shutter(page)).toBeEnabled()
  await shutter(page).tap()
  await expect(page.getByRole('button', { name: '重试上传' })).toBeVisible()
  await page.evaluate(() => window.dispatchEvent(new Event('online')))
  await expect(page.getByText('正在把美食剪下来…')).toBeVisible()
  await page.getByRole('button', { name: '跳过特效' }).click()
  await expect(page.locator('.scan-light')).toHaveCount(0)
  await page.getByRole('textbox', { name: '食物名称' }).first().fill('处理中保存')
  await page.getByRole('button', { name: '贴进手账' }).click()
  const entry = page.getByRole('button', { name: '查看记录 处理中保存' })
  await expect(entry).toBeVisible()
  await expect(entry.locator('[data-sticker]')).toBeVisible()
  expect({ uploads, jobs }).toEqual({ uploads: 2, jobs: 1 })
})

test('另一浏览器只看到已保存且获授权的真实贴纸，撤销后旧地址失效', async ({ page, browser, baseURL }) => {
  const author = await login(page)
  const separate = await browser.newContext({ baseURL, locale: 'zh-CN', timezoneId: 'Asia/Shanghai', viewport: { width: 390, height: 844 } })
  try {
    const friendPage = await separate.newPage()
    const reader = await login(friendPage)
    const friends = '/api/v1/friends/'
    const sent = await page.request.post(friends + 'requests', { headers: author.headers, data: { public_id: reader.id } })
    expect(sent.status()).toBe(202)
    expect((await friendPage.request.post(friends + 'requests/' + (await sent.json()).id + '/accept', { headers: reader.headers })).ok()).toBe(true)
    const sharing = friends + reader.id + '/sharing'
    const grant = async (permissions: Record<string, boolean>) => {
      const { relationship_id, outgoing: { version } } = await (await page.request.get(sharing, { headers: author.headers })).json()
      expect((await page.request.put(sharing, { headers: author.headers, data: { relationship_id, version, permissions } })).ok()).toBe(true)
    }
    await grant({ records: true, names: true, stickers: true })
    await open(page)
    await expect(shutter(page)).toBeEnabled()
    await shutter(page).tap()
    await expect(page.locator('.capture-stage')).toHaveAttribute('data-stage', 'ready')
    const day = await page.locator('input[type=date]').inputValue()
    const shared = '/friends/' + author.id + '/diary?date=' + day
    await friendPage.goto(shared)
    await expect(friendPage.getByText('这一天还没有饮食记录。')).toBeVisible()
    await page.getByRole('textbox', { name: '食物名称' }).first().fill('分享的家常菜')
    const saved = page.waitForResponse(response => known('/meals', 'POST', response.request()))
    await page.getByRole('button', { name: '贴进手账' }).click()
    const response = await saved
    expect(response.status()).toBe(201)
    const { id, media } = await response.json()
    await friendPage.getByRole('button', { name: '刷新共享内容' }).click()
    const image = friendPage.getByRole('img', { name: '共享美食贴纸' })
    await expect(image).toBeVisible()
    await screen(friendPage, '08-friend-real-sticker')
    const sharedAsset = friends + author.id + '/media/' + media[0].id + '/sticker?meal_id=' + id
    expect((await friendPage.request.get(sharedAsset, { headers: reader.headers })).status()).toBe(200)
    await grant({})
    expect((await friendPage.request.get(sharedAsset, { headers: reader.headers })).status()).toBe(404)
    await friendPage.reload()
    await expect(image).toHaveCount(0)
  } finally { await separate.close() }
})
