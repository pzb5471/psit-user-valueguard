import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import {
  colorTokens,
  motionTokens,
  radiusTokens,
  spacingTokens,
  typographyTokens,
  zIndexTokens,
} from '../src/theme/tokens'

const here = dirname(fileURLToPath(import.meta.url))
const themeCssPath = resolve(here, '../src/theme/theme.css')
const themeCss = readFileSync(themeCssPath, 'utf-8')

test('主题令牌包含规格 13.5 要求的六组', () => {
  expect(colorTokens).toBeDefined()
  expect(typographyTokens).toBeDefined()
  expect(spacingTokens).toBeDefined()
  expect(radiusTokens).toBeDefined()
  expect(motionTokens).toBeDefined()
  expect(zIndexTokens).toBeDefined()
})

test('CSS 变量与 TS 令牌逐值一致', () => {
  const tokenGroups = [
    colorTokens,
    typographyTokens,
    spacingTokens,
    radiusTokens,
    motionTokens,
    zIndexTokens,
  ]
  for (const group of tokenGroups) {
    for (const value of Object.values(group)) {
      expect(themeCss).toContain(value)
    }
  }
})

test('AntD ConfigProvider 主题映射主色与状态色', async () => {
  const { antdTheme } = await import('../src/theme/antdTheme')
  const token = antdTheme.token ?? {}
  expect(token.colorPrimary).toBe(colorTokens.primaryAction)
  expect(token.colorSuccess).toBe(colorTokens.success)
  expect(token.colorWarning).toBe(colorTokens.warning)
  expect(token.colorError).toBe(colorTokens.danger)
  expect(token.colorText).toBe(colorTokens.textPrimary)
  expect(token.fontFamily).toBe(typographyTokens.fontFamily)
})

test('Inter 字体本地打包且 font-display 为 swap', () => {
  expect(themeCss).toContain('@font-face')
  expect(themeCss).toContain('font-display: swap')
  expect(themeCss).toContain('../assets/fonts/InterVariable.woff2')

  const fontPath = resolve(here, '../src/assets/fonts/InterVariable.woff2')
  const licensePath = resolve(here, '../src/assets/fonts/LICENSE-OFL.txt')
  expect(readFileSync(fontPath).byteLength).toBeGreaterThan(100_000)
  expect(readFileSync(licensePath, 'utf-8')).toContain('SIL OPEN FONT LICENSE')
})
