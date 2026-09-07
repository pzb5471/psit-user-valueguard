import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const pkg = JSON.parse(readFileSync(resolve(here, '../package.json'), 'utf-8')) as {
  dependencies?: Record<string, string>
  devDependencies?: Record<string, string>
}

/**
 * 依赖白名单（技术实施规格 13.1 冻结技术栈 + 构建测试工具链）。
 * 运行依赖只允许冻结栈；@tanstack/react-query、openapi-typescript、openapi-fetch、msw、
 * playwright 由 M4-02 与 M4-08/M4-09 的卡片启用，白名单一次到位，后续卡不改本测试。
 */
const allowedDependencies = new Set([
  '@ant-design/icons',
  'antd',
  'react',
  'react-dom',
  'react-router-dom',
  '@tanstack/react-query',
  'openapi-fetch',
])

const allowedDevDependencies = new Set([
  // 构建
  '@vitejs/plugin-react',
  'typescript',
  'vite',
  // 测试（含冻结栈后续卡）
  '@testing-library/jest-dom',
  '@testing-library/react',
  '@testing-library/user-event',
  'jsdom',
  'msw',
  'playwright',
  '@playwright/test',
  'vitest',
  // Lint
  '@eslint/js',
  'eslint',
  'eslint-plugin-react-hooks',
  'eslint-plugin-react-refresh',
  'globals',
  'typescript-eslint',
  // 类型
  '@types/react',
  '@types/react-dom',
  '@types/node',
  'openapi-typescript',
])

test('运行依赖全部在白名单内', () => {
  const actual = new Set(Object.keys(pkg.dependencies ?? {}))
  for (const dep of actual) {
    expect(allowedDependencies.has(dep)).toBe(true)
  }
})

test('开发依赖全部在白名单内', () => {
  const actual = new Set(Object.keys(pkg.devDependencies ?? {}))
  for (const dep of actual) {
    expect(allowedDevDependencies.has(dep)).toBe(true)
  }
})

test('冻结技术栈的运行时部分已在依赖中', () => {
  for (const required of ['react', 'react-dom', 'react-router-dom', 'antd', '@ant-design/icons']) {
    expect(pkg.dependencies).toHaveProperty(required)
  }
})
