import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClientProvider } from '@tanstack/react-query'
import { delay, http, HttpResponse } from 'msw'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, expect, test } from 'vitest'
import { BatchPage } from '../../src/pages/batch/BatchPage'
import { createQueryClient } from '../../src/queries/queryClient'
import { batchView, queueView } from '../../src/mocks/fixtures'
import { mockUrl } from '../../src/mocks/handlers'
import { scenarios } from '../../src/mocks/scenarios'
import { startMsw } from '../contracts/mswServer'

const server = startMsw()

const calls = { runs: 0 }
beforeEach(() => {
  calls.runs = 0
})

/** 与 main.tsx 装配一致：Provider + /batches/:batchId 路由参数。 */
function renderBatch(batchId = 'batch-demo-001') {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={[`/batches/${batchId}`]}>
        <Routes>
          <Route path="/batches/:batchId" element={<BatchPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

/** 队列五状态样例（fixtures.queueView）：处理异常/待确认/已完成/分析中/待分析各一。 */
function useDefaultQueue() {
  server.use(http.get(mockUrl('/api/v1/batches/:batchId/cases'), () => HttpResponse.json(queueView())))
}

test('批次状态一：待分析显示开始按钮', async () => {
  server.use(
    http.get(mockUrl('/api/v1/batches/:batchId'), () =>
      HttpResponse.json(batchView('PENDING_ANALYSIS')),
    ),
  )
  useDefaultQueue()
  renderBatch()
  const button = await screen.findByRole('button', { name: '开始分析' })
  expect(button).toBeEnabled()
  const pendingBadges = await screen.findAllByText('待分析')
  expect(pendingBadges.length).toBeGreaterThanOrEqual(1)
})

test('批次状态二：分析中不显示开始按钮', async () => {
  server.use(
    http.get(mockUrl('/api/v1/batches/:batchId'), () => HttpResponse.json(batchView('ANALYZING'))),
  )
  useDefaultQueue()
  renderBatch()
  expect(await screen.findByText('分析进行中；每个案例完成后将进入待确认。')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '开始分析' })).not.toBeInTheDocument()
})

test('批次状态三：已完成显示零错误摘要', async () => {
  server.use(
    http.get(mockUrl('/api/v1/batches/:batchId'), () => HttpResponse.json(batchView('COMPLETED'))),
  )
  useDefaultQueue()
  renderBatch()
  expect((await screen.findAllByText('已完成')).length).toBeGreaterThanOrEqual(1)
  expect(screen.queryByRole('button', { name: '开始分析' })).not.toBeInTheDocument()
})

test('批次状态四：完成（含错误）显示错误计数', async () => {
  server.use(
    http.get(mockUrl('/api/v1/batches/:batchId'), () =>
      HttpResponse.json(batchView('COMPLETED_WITH_ERRORS')),
    ),
  )
  useDefaultQueue()
  renderBatch()
  expect(await screen.findByText('已完成（含错误）')).toBeInTheDocument()
  expect(screen.getAllByText('处理异常').length).toBeGreaterThanOrEqual(2)
})

test('无密钥：开始按钮禁用并显示业务说明', async () => {
  server.use(
    http.get(mockUrl('/api/v1/batches/:batchId'), () =>
      HttpResponse.json(
        batchView('PENDING_ANALYSIS', {
          can_start_analysis: false,
          analysis_unavailable_message: '缺少模型密钥，暂时不能开始分析。',
        }),
      ),
    ),
  )
  useDefaultQueue()
  renderBatch()
  expect(await screen.findByText('缺少模型密钥，暂时不能开始分析。')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '开始分析' })).not.toBeInTheDocument()
})

test('开始分析：202 后精确失效，批次进入分析中', async () => {
  let runsStarted = false
  server.use(
    http.get(mockUrl('/api/v1/batches/:batchId'), () =>
      HttpResponse.json(runsStarted ? batchView('ANALYZING') : batchView('PENDING_ANALYSIS')),
    ),
    http.post(mockUrl('/api/v1/batches/:batchId/runs'), () => {
      calls.runs += 1
      runsStarted = true
      return HttpResponse.json(batchView('ANALYZING'), { status: 202 })
    }),
  )
  useDefaultQueue()
  renderBatch()
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: '开始分析' }))
  await waitFor(() =>
    expect(screen.getByText('分析进行中；每个案例完成后将进入待确认。')).toBeInTheDocument(),
  )
  expect(calls.runs).toBe(1)
})

test('重复点击保护：请求进行中按钮禁用，仅发出一次', async () => {
  let runsStarted = false
  server.use(
    http.get(mockUrl('/api/v1/batches/:batchId'), () =>
      HttpResponse.json(runsStarted ? batchView('ANALYZING') : batchView('PENDING_ANALYSIS')),
    ),
    http.post(
      mockUrl('/api/v1/batches/:batchId/runs'),
      async () => {
        calls.runs += 1
        runsStarted = true
        await delay(800)
        return HttpResponse.json(batchView('ANALYZING'), { status: 202 })
      },
    ),
  )
  useDefaultQueue()
  renderBatch()
  const user = userEvent.setup()
  const button = await screen.findByRole('button', { name: '开始分析' })
  await user.click(button)
  const startingButton = screen.getByRole('button', { name: '正在开始…' })
  expect(startingButton).toBeDisabled()
  await user.click(startingButton)
  await waitFor(() =>
    expect(screen.getByText('分析进行中；每个案例完成后将进入待确认。')).toBeInTheDocument(),
  )
  expect(calls.runs).toBe(1)
})

test.each([
  ['run.activeBatchExists', '该批次已有分析正在运行。'],
  ['run.analysisUnavailable', '缺少模型密钥，暂时不能开始分析。'],
])('开始失败（%s）显示原因与建议', async (scenario, message) => {
  server.use(
    http.get(mockUrl('/api/v1/batches/:batchId'), () =>
      HttpResponse.json(batchView('PENDING_ANALYSIS')),
    ),
    ...scenarios[scenario],
  )
  useDefaultQueue()
  renderBatch()
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: '开始分析' }))
  const alert = await screen.findByRole('alert')
  expect(alert).toHaveTextContent('操作未能完成')
  expect(alert).toHaveTextContent(message)
})

test('队列呈现五种案例状态', async () => {
  server.use(
    http.get(mockUrl('/api/v1/batches/:batchId'), () =>
      HttpResponse.json(batchView('ANALYZING')),
    ),
  )
  useDefaultQueue()
  const { container } = renderBatch()
  await screen.findByText('案例队列')
  await waitFor(() => expect(container.querySelector('tbody')).not.toBeNull())
  const tableText = container.querySelector('tbody')?.textContent ?? ''
  // 五种案例状态（服务端固定排序）：处理异常/待确认/已完成/分析中/待分析。
  expect(tableText).toContain('处理异常')
  expect(tableText).toContain('待确认')
  expect(tableText).toContain('已完成')
  expect(tableText).toContain('分析中')
  expect(tableText).toContain('待分析')
})

test('状态三重表达：徽章含文字、图标与颜色类', async () => {
  server.use(
    http.get(mockUrl('/api/v1/batches/:batchId'), () => HttpResponse.json(batchView('ANALYZING'))),
  )
  useDefaultQueue()
  const { container } = renderBatch()
  await screen.findByText('案例队列')
  // 队列表格内的"处理异常"状态徽章：颜色类（dangerCell）+ 图标（svg）+ 文字。
  const badge = container.querySelector('tbody [class*="dangerCell"]')
  expect(badge).not.toBeNull()
  expect(badge?.textContent).toContain('处理异常')
  expect(badge?.querySelector('svg')).not.toBeNull()
})

test('介入等级与异常标记呈现', async () => {
  server.use(
    http.get(mockUrl('/api/v1/batches/:batchId'), () =>
      HttpResponse.json(batchView('PENDING_ANALYSIS')),
    ),
  )
  useDefaultQueue()
  const { container } = renderBatch()
  await screen.findByText('案例队列')
  await waitFor(() => expect(container.querySelector('tbody')).not.toBeNull())
  const tableText = container.querySelector('tbody')?.textContent ?? ''
  expect(tableText).toContain('必须介入')
  expect(tableText).toContain('建议介入')
  expect(tableText).toContain('证据读取失败，需要人工跟进。')
  expect(tableText).toContain('处理异常')
})

test('队列空态', async () => {
  server.use(
    http.get(mockUrl('/api/v1/batches/:batchId'), () =>
      HttpResponse.json(batchView('PENDING_ANALYSIS', { case_count: 0 })),
    ),
    http.get(mockUrl('/api/v1/batches/:batchId/cases'), () =>
      HttpResponse.json({ items: [], total: 0 }),
    ),
  )
  renderBatch()
  expect(await screen.findByText('暂无符合条件的案例。')).toBeInTheDocument()
})

test('批次不存在显示错误态', async () => {
  server.use(...scenarios['read.resourceNotFound'])
  renderBatch('batch-missing')
  const alert = await screen.findByRole('alert')
  expect(alert).toHaveTextContent('批次不存在。')
})

test('队列加载失败显示错误与重试', async () => {
  server.use(
    http.get(mockUrl('/api/v1/batches/:batchId'), () =>
      HttpResponse.json(batchView('PENDING_ANALYSIS')),
    ),
    http.get(mockUrl('/api/v1/batches/:batchId/cases'), () =>
      HttpResponse.json(
        { code: 'INTERNAL_ERROR', message: '服务内部错误，请稍后重试。' },
        { status: 500 },
      ),
    ),
  )
  const { container } = renderBatch()
  const user = userEvent.setup()
  expect(await screen.findByRole('alert')).toHaveTextContent('服务内部错误')
  server.use(
    http.get(mockUrl('/api/v1/batches/:batchId/cases'), () => HttpResponse.json(queueView())),
  )
  await user.click(screen.getByRole('button', { name: '重新加载' }))
  await waitFor(() => expect(container.querySelector('tbody')).not.toBeNull())
  expect(container.querySelector('tbody')?.textContent).toContain('待确认')
})

test('页面不出现技术字段与内部概念', async () => {
  server.use(
    http.get(mockUrl('/api/v1/batches/:batchId'), () => HttpResponse.json(batchView('ANALYZING'))),
  )
  useDefaultQueue()
  const { container } = renderBatch()
  await screen.findByText('案例队列')
  const text = container.textContent ?? ''
  for (const banned of ['Agent', 'RFM', 'Prompt', 'Token', 'Schema', 'run_id', 'batch_run', 'case_run']) {
    expect(text).not.toContain(banned)
  }
})
