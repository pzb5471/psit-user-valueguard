import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './tests/e2e-msw',
  // 三种桌面尺寸：1366×768 为主验收，1024×768 为最低可用（规格 13.3）。
  projects: [
    { name: 'desktop-1366', use: { ...devices['Desktop Chrome'], viewport: { width: 1366, height: 768 } } },
    { name: 'desktop-1024', use: { ...devices['Desktop Chrome'], viewport: { width: 1024, height: 768 } } },
  ],
  use: {
    baseURL: 'http://127.0.0.1:5199',
  },
  // 由 test:e2e 先完成构建，webServer 同源提供已构建产物（本地资源，无 CDN）。
  // 显式 --host 127.0.0.1：vite 默认绑定 ::1，与健康检查的 127.0.0.1 族不一致会导致超时。
  webServer: {
    command: 'pnpm exec vite preview --port 5199 --strictPort --host 127.0.0.1',
    url: 'http://127.0.0.1:5199',
    timeout: 60_000,
  },
  reporter: [['list'], ['html', { outputFolder: 'playwright-report', open: 'never' }]],
})
