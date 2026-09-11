/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const apiOrigin = process.env.VITE_API_ORIGIN ?? 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react()],
  // M4 API 装配层：开发环境下将 /api 与证据图片代理到真实后端（config/default.toml port=8000）。
  // 生产演示由 FastAPI 同源提供前端静态文件与 /api（规格 14），无需代理。
  server: {
    proxy: {
      '/api': apiOrigin,
    },
  },
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
    // Playwright 浏览器旅程由 test:e2e 单独运行，排除出 vitest（jsdom 无法执行）。
    exclude: ['tests/e2e-msw/**', 'tests/e2e-real/**', 'node_modules/**', 'dist/**'],
  },
})
