/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./tests/setup.ts'],
    environmentOptions: {
      jsdom: {
        // 组件测试的请求基址与 MSW MOCK_ORIGIN 同源（Node 端 MSW 要求完整 URL 匹配）。
        url: 'http://psit-mock.local/',
      },
    },
  },
})
