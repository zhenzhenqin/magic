import { defineConfig, devices } from '@playwright/test'
import { join } from 'node:path'

const artifacts = process.env.FOODDIARY_CAMERA_EVIDENCE
const fixture = process.env.FOODDIARY_CAMERA_FIXTURE
if (!artifacts || !fixture) throw new Error('Set FOODDIARY_CAMERA_EVIDENCE and FOODDIARY_CAMERA_FIXTURE to D: paths.')

export default defineConfig({
  testDir: './tests', testMatch: '**/*.camera.spec.ts', workers: 1, timeout: 60_000,
  outputDir: join(artifacts, 'runs'), reporter: 'list', expect: { timeout: 24_000 },
  use: {
    ...devices['Pixel 7'], viewport: { width: 390, height: 844 }, channel: 'chrome',
    baseURL: process.env.FOODDIARY_CAMERA_URL ?? 'http://127.0.0.1:15197', locale: 'zh-CN', timezoneId: 'Asia/Shanghai',
    video: 'on', launchOptions: { args: ['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream',
      '--use-file-for-fake-video-capture=' + fixture] },
  },
})
