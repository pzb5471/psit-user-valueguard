import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './tests/e2e-real',
  fullyParallel: false,
  workers: 1,
  projects: [
    {
      name: 'real-api-desktop-1366',
      use: { ...devices['Desktop Chrome'], viewport: { width: 1366, height: 768 } },
    },
  ],
  use: {
    baseURL: 'http://127.0.0.1:8000',
  },
  webServer: {
    command: 'uv run python -m app.modules.application.e2e_launcher',
    cwd: '..',
    env: { PYTHONPATH: 'backend' },
    url: 'http://127.0.0.1:8000/api/v1/health',
    timeout: 60_000,
    reuseExistingServer: false,
  },
  reporter: [['list'], ['html', { outputFolder: 'playwright-report', open: 'never' }]],
})
