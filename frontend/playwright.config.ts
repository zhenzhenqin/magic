import { defineConfig } from '@playwright/test'

const port = Number(process.env.FOODDIARY_PORT ?? 5173)
const baseURL = 'http://127.0.0.1:' + port

export default defineConfig({
  testDir: './tests',
  testIgnore: '**/*.api.spec.ts',
  outputDir: './test-results',
  fullyParallel: false,
  workers: 1,
  timeout: 60_000,
  reporter: 'list',
  use: {
    baseURL,
    channel: 'chrome',
    actionTimeout: 8_000,
    timezoneId: 'Asia/Shanghai',
    locale: 'zh-CN',
    trace: 'retain-on-failure',
  },
  webServer: {
    command: 'pnpm dev --host 127.0.0.1 --port ' + port + ' --strictPort',
    url: baseURL,
    reuseExistingServer: true,
  },
})
