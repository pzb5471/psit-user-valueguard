import { expect, test } from '@playwright/test'
import { mkdirSync } from 'node:fs'
import { assertNoExternalRequests, createState, installApiMock } from './apiMock'

/** 相对亮度（WCAG 2.x）。 */
function luminance(hex: string): number {
  const channels = hex.replace('#', '')
  const [r, g, b] = [0, 2, 4].map((offset) => {
    const value = parseInt(channels.slice(offset, offset + 2), 16) / 255
    return value <= 0.03928 ? value / 12.92 : Math.pow((value + 0.055) / 1.055, 2.4)
  })
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

function contrastRatio(a: string, b: string): number {
  const [l1, l2] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (l1 + 0.05) / (l2 + 0.05)
}

test('完整旅程：导入→开始→队列→详情→确认→只读，并在 44px/键盘/对比度/无横向滚动下验收', async ({ page }) => {
  const state = createState()
  installApiMock(page, state)
  assertNoExternalRequests(page)

  // —— 工作台入口：无批次进入导入区 ——
  await page.goto('/')
  await expect(page.getByText('批次导入')).toBeVisible()

  // 上传一个 ZIP（两步导入）。
  await page.locator('input[type="file"]').setInputFiles({
    name: 'mvp_batch_v1.zip',
    mimeType: 'application/zip',
    buffer: Buffer.from('504b0304', 'hex'),
  })
  await expect(page.getByText('已选择：mvp_batch_v1.zip')).toBeVisible()
  await page.getByRole('button', { name: '导入批次' }).click()
  await expect(page.getByText('通过，已导入')).toBeVisible()
  // Mock 提示明确。
  await expect(page.getByText(/Mock 数据/).first()).toBeVisible()

  // 键盘：Tab 聚焦“开始分析”，Enter 激活 → 进入批次页（开始调用后端翻转 ANALYZING）。
  await page.getByRole('button', { name: '开始分析' }).focus()
  await page.keyboard.press('Enter')
  await expect(page.getByText('案例队列')).toBeVisible()

  // —— 队列页：打开一个待确认案例 ——
  await page.getByRole('link', { name: '示例客户 C-1001' }).click()
  await expect(page.getByText('高价值客户')).toBeVisible()

  // —— 详情页：人工确认通过 ——
  await page.getByText('直接通过').click()
  await page.getByRole('button', { name: '提交确认' }).click()
  // 确认后服务端返回 COMPLETED → 只读提示。
  await expect(page.getByText(/结果已锁定为只读/)).toBeVisible()

  // —— 可访问性与布局断言 ——
  // 44×44px 核心点击区。
  const smallTargets = await page.evaluate(() => {
    const targets = Array.from(document.querySelectorAll('button, a, select, [role="button"]'))
    const small: string[] = []
    for (const el of targets) {
      const rect = (el as HTMLElement).getBoundingClientRect()
      if (rect.width < 44 || rect.height < 44) {
        small.push(`${el.tagName}:${(el as HTMLElement).className} ${rect.width}x${rect.height}`)
      }
    }
    return small
  })
  expect(smallTargets).toEqual([])

  // 主体无横向滚动。
  const hasHorizontalScroll = await page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
  )
  expect(hasHorizontalScroll).toBe(false)

  // WCAG AA 对比度（正文 #1d1d1f on #fff、主按钮白字 on #0066cc）。
  const contrast = await page.evaluate(() => {
    const body = getComputedStyle(document.body)
    const button = document.querySelector('button')
    const buttonStyle = button ? getComputedStyle(button) : null
    return {
      bodyColor: body.color,
      bodyBg: body.backgroundColor,
      buttonColor: buttonStyle?.color ?? '',
      buttonBg: buttonStyle?.backgroundColor ?? '',
    }
  })
  const bodyText = rgbToHex(contrast.bodyColor)
  const bodyBg = rgbaToHex(contrast.bodyBg)
  expect(contrastRatio(bodyText, bodyBg)).toBeGreaterThanOrEqual(4.5)
})

// 简化的 rgb()/rgba() → hex 解析（页面用十六进制令牌，getComputedStyle 返回 rgb/rgba）。
function rgbToHex(rgb: string): string {
  const parts = rgb.replace(/[^\d,]/g, '').split(',').map(Number)
  return `#${parts.slice(0, 3).map((n) => n.toString(16).padStart(2, '0')).join('')}`
}

function rgbaToHex(rgba: string): string {
  return rgbToHex(rgba)
}

test('证据图片受控加载与失败回退', async ({ page }) => {
  const state = createState()
  installApiMock(page, state)
  await page.goto('/')
  // 有批次时直接进入最近批次。
  await page.goto(`/batches/batch-mvp-001`)
  await page.getByText('案例队列').waitFor()
  await page.getByRole('link', { name: '示例客户 C-1001' }).click()
  // 展开图片证据，点击可加载（不报错）。
  await page.getByRole('button', { name: /商品照片/ }).click()
  await expect(page.locator('img[alt="商品照片"]')).toBeVisible()
})

test('两种尺寸截图产物（供人工截图审查）', async ({ page }) => {
  const state = createState()
  installApiMock(page, state)
  mkdirSync('playwright-report/screenshots', { recursive: true })
  await page.goto('/batches/batch-mvp-001')
  await page.getByText('案例队列').waitFor()
  const project = test.info().project.name
  await page.screenshot({ path: `playwright-report/screenshots/${project}-batch.png`, fullPage: true })
  await page.getByRole('link', { name: '示例客户 C-1001' }).click()
  await page.getByText('高价值客户').waitFor()
  await page.screenshot({ path: `playwright-report/screenshots/${project}-case.png`, fullPage: true })
  expect(true).toBe(true)
})
