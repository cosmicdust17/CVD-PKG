import { defineConfig } from '@playwright/test'

const pagesUrl = process.env.HF_PAGES_URL

export default defineConfig({
  testDir: './tests/browser',
  timeout: 60_000,
  use: {
    baseURL: pagesUrl || 'http://127.0.0.1:4187',
    channel: process.env.PLAYWRIGHT_CHANNEL || 'msedge',
    viewport: { width: 1440, height: 900 },
  },
  webServer: pagesUrl ? undefined : {
    command: 'pnpm dev --mode test --port 4187',
    url: 'http://127.0.0.1:4187',
    timeout: 60_000,
  },
})
