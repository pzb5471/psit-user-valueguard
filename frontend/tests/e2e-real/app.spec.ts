import { expect, test } from '@playwright/test'

const BATCH_ID = 'batch-mvp-0001'

test('真实 API：导入→开始→队列→详情→图片→确认→刷新读回', async ({ page, request }) => {
  const externalRequests: string[] = []
  page.on('request', (outgoing) => {
    const url = new URL(outgoing.url())
    if (url.hostname !== '127.0.0.1' && url.hostname !== 'localhost') {
      externalRequests.push(outgoing.url())
    }
  })

  const archiveResponse = await request.get('/e2e/mvp.zip')
  expect(archiveResponse.ok()).toBe(true)
  const archive = await archiveResponse.body()

  await page.goto('/')
  await expect(page.getByText('批次导入')).toBeVisible()
  await page.locator('input[type="file"]').setInputFiles({
    name: 'mvp_batch_v1.zip',
    mimeType: 'application/zip',
    buffer: archive,
  })
  await page.getByRole('button', { name: '导入批次' }).click()
  await expect(page.getByText('通过，已导入')).toBeVisible()

  await page.getByRole('button', { name: '开始分析' }).click()
  await expect(page).toHaveURL(new RegExp(`/batches/${BATCH_ID}$`))
  await page.getByRole('button', { name: '开始分析' }).click()

  await expect(page.getByRole('link', { name: 'cust-0001' })).toBeVisible()
  await expect(page.getByRole('table').getByText('待确认')).toBeVisible({ timeout: 15_000 })
  await page.getByRole('link', { name: 'cust-0001' }).click()

  await expect(page.getByText('高价值客户').first()).toBeVisible()
  await expect(page.getByText('商品安全问题未解决，存在流失风险。')).toBeVisible()
  await page.getByRole('button', { name: /售后图片/ }).click()
  await expect(page.locator('img[alt="售后图片"]')).toBeVisible()

  await page.getByRole('button', { name: '提交确认' }).click()
  await expect(page.getByText(/结果已锁定为只读/)).toBeVisible()
  await page.reload()
  await expect(page.getByText(/结果已锁定为只读/)).toBeVisible()
  expect(externalRequests).toEqual([])
})
