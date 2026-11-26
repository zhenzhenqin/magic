import { defineConfig } from '@playwright/test'
import { fileURLToPath } from 'node:url'
import { resolve } from 'node:path'

const frontendPort = Number(process.env.FOODDIARY_PORT ?? 15173)
const backendPort = Number(process.env.FOODDIARY_BACKEND_PORT ?? 18020)
const backend = fileURLToPath(new URL('../backend/', import.meta.url))
const python = resolve(backend, '.venv', 'Scripts', 'python.exe')
const web = 'http://127.0.0.1:' + frontendPort
const api = 'http://127.0.0.1:' + backendPort

export default defineConfig({
  testDir: './tests',
  testMatch: '**/*.api.spec.ts',
  outputDir: './test-results/phase-2-api',
  workers: 1,
  timeout: 60_000,
  reporter: [['list'], ['html', { outputFolder: 'playwright-report/phase-2-api', open: 'never' }]],
  use: {
    baseURL: web,
    channel: 'chrome',
    locale: 'zh-CN',
    timezoneId: 'Asia/Shanghai',
    actionTimeout: 8_000,
    trace: 'off',
    screenshot: 'off',
  },
  webServer: [
    {
      command: '"' + python + '" -m tests.browser_server ' + backendPort + ' ' + frontendPort,
      cwd: backend,
      url: api + '/api/v1/ready',
      reuseExistingServer: false,
      stdout: 'pipe',
    },
    {
      command: 'pnpm dev --host 127.0.0.1 --port ' + frontendPort + ' --strictPort',
      env: { VITE_APP_MODE: 'api', FOODDIARY_BACKEND_PORT: String(backendPort) },
      url: web,
      reuseExistingServer: false,
    },
  ],
})
