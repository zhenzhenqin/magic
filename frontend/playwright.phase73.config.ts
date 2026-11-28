import { defineConfig, devices } from '@playwright/test'
import { join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const evidence = process.env.FOODDIARY_73_EVIDENCE
const fixture = process.env.FOODDIARY_CAMERA_FIXTURE
if (!evidence || !fixture) throw new Error('Supply the Phase 7.3 evidence and camera fixture paths on D:')
const backend = fileURLToPath(new URL('../backend/', import.meta.url))
const python = resolve(backend, '.venv', 'Scripts', 'python.exe')
const webPort = 15273
const apiPort = 18273
const web = 'http://127.0.0.1:' + webPort

export default defineConfig({
  testDir: './tests', testMatch: '**/*.phase73.spec.ts', workers: 1, timeout: 120_000,
  outputDir: join(evidence, 'runs'), reporter: 'list', expect: { timeout: 24_000 },
  use: {
    ...devices['Pixel 7'], viewport: { width: 390, height: 844 }, channel: 'chrome',
    baseURL: web, locale: 'zh-CN', timezoneId: 'Asia/Shanghai', video: 'on',
    launchOptions: { args: ['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream',
      '--use-file-for-fake-video-capture=' + fixture] },
  },
  webServer: [
    ...(process.env.FOODDIARY_73_EXTERNAL_BACKEND ? [] : [{ command: '"' + python + '" -m tests.browser_server ' + apiPort + ' ' + webPort + ' --phase-73 --onnx-stickers',
      cwd: backend, env: { FOODDIARY_TEST_INBOX: join(evidence, 'mock-inbox') },
      url: 'http://127.0.0.1:' + apiPort + '/api/v1/ready', stdout: 'pipe' as const }]),
    { command: 'pnpm dev --host 127.0.0.1 --port ' + webPort + ' --strictPort',
      env: { VITE_APP_MODE: 'api', FOODDIARY_BACKEND_PORT: String(apiPort) }, url: web },
  ],
})
