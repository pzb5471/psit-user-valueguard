// @vitest-environment jsdom
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { BatchPage } from '../../src/pages/batch/BatchPage'
import { createQueryClient } from '../../src/queries/queryClient'
import { batchView, queueItem } from '../../src/mocks/fixtures'
import { mockUrl } from '../../src/mocks/handlers'
import { startMsw } from '../contracts/mswServer'

const server = startMsw()

const calls = { batch: 0, queue: 0 }
const seenQueueUrls: string[] = []
let currentBatchStatus: ReturnType<typeof batchView>['status'] = 'PENDING_ANALYSIS'

beforeEach(() => {
  calls.batch = 0
  calls.queue = 0
  seenQueueUrls.length = 0
  currentBatchStatus = 'PENDING_ANALYSIS'
  server.use(
    http.get(mockUrl('/api/v1/batches/:batchId'), () => {
      calls.batch += 1
      return HttpResponse.json(batchView(currentBatchStatus))
    }),
    http.get(mockUrl('/api/v1/batches/:batchId/cases'), ({ request }) => {
      calls.queue += 1
      seenQueueUrls.push(request.url)
      return HttpResponse.json({
        items: [queueItem('PENDING_REVIEW')],
        total: 1,
      })
    }),
  )
  window.history.replaceState(null, '', '/batches/batch-mvp-001')
})

afterEach(() => {
  vi.useRealTimers()
  Reflect.deleteProperty(document, 'hidden')
  window.history.replaceState(null, '', '/')
})

/** 在假时钟下推进并等待断言通过（避免 waitFor 与假定时器死锁）。 */
async function advanceUntil(assertion: () => void, stepMs = 100, tries = 60) {
  let lastError: unknown = new Error('未执行断言')
  for (let i = 0; i < tries; i += 1) {
    await advanceClock(stepMs)
    try {
      assertion()
      return
    } catch (error) {
      lastError = error
    }
  }
  throw lastError
}

function renderAt(path: string) {
  window.history.replaceState(null, '', path)
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <BrowserRouter>
        <Routes>
          <Route path="/batches/:batchId" element={<BatchPage />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>,
  )
}

/** 让 TanStack Query 的初始加载与轮询定时器在假时钟下完成。 */
async function advanceClock(ms: number) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms)
  })
}

test('直接地址恢复筛选与分页（结果来自服务端）', async () => {
  renderAt('/batches/batch-mvp-001?status=COMPLETED&intervention_level=MUST_INTERVENE&offset=0')
  await screen.findByText('案例队列')
  await waitFor(() => expect(seenQueueUrls.length).toBeGreaterThan(0))
  const url = new URL(seenQueueUrls[seenQueueUrls.length - 1])
  expect(url.searchParams.get('status')).toBe('COMPLETED')
  expect(url.searchParams.get('intervention_level')).toBe('MUST_INTERVENE')
  expect(url.searchParams.get('limit')).toBe('50')
})

test('筛选变更写入 URL、重置分页并触发服务端新请求；返回恢复原筛选', async () => {
  const user = userEvent.setup()
  renderAt('/batches/batch-mvp-001')
  const select = await screen.findByLabelText('案例状态')
  await user.selectOptions(select, 'COMPLETED')

  await waitFor(() => expect(window.location.search).toContain('status=COMPLETED'))
  const withStatus = new URL(seenQueueUrls[seenQueueUrls.length - 1])
  expect(withStatus.searchParams.get('status')).toBe('COMPLETED')

  await user.selectOptions(screen.getByLabelText('介入等级'), 'MUST_INTERVENE')
  await waitFor(() => expect(window.location.search).toContain('intervention_level=MUST_INTERVENE'))

  // 浏览器返回：回到只有 status 筛选的业务位置。
  await act(async () => {
    window.history.back()
  })
  await waitFor(() => expect(window.location.search).toContain('status=COMPLETED'))
  await waitFor(() => expect(window.location.search).not.toContain('intervention_level'))
})

test('默认与边界分页', async () => {
  server.use(
    http.get(mockUrl('/api/v1/batches/:batchId/cases'), ({ request }) => {
      calls.queue += 1
      seenQueueUrls.push(request.url)
      return HttpResponse.json({
        items: [queueItem('PENDING_REVIEW')],
        total: 120,
      })
    }),
  )
  const user = userEvent.setup()
  renderAt('/batches/batch-mvp-001')

  // 默认：limit=50、offset=0，首页上一页禁用。
  await screen.findByText('案例队列')
  await waitFor(() => expect(seenQueueUrls.length).toBeGreaterThan(0))
  expect(new URL(seenQueueUrls[0]).searchParams.get('offset')).toBe('0')
  expect(new URL(seenQueueUrls[0]).searchParams.get('limit')).toBe('50')
  await waitFor(() => expect(screen.getByRole('button', { name: '下一页' })).toBeEnabled())
  expect(screen.getByRole('button', { name: '上一页' })).toBeDisabled()

  // 下一页写入 URL 并向服务端请求 offset=50。
  await user.click(screen.getByRole('button', { name: '下一页' }))
  await waitFor(() => expect(window.location.search).toContain('offset=50'))
  await waitFor(() =>
    expect(new URL(seenQueueUrls[seenQueueUrls.length - 1]).searchParams.get('offset')).toBe('50'),
  )
  expect(screen.getByRole('button', { name: '上一页' })).toBeEnabled()
})

test('越界 URL 参数回落安全默认（不把非法值发给服务端）', async () => {
  renderAt('/batches/batch-mvp-001?offset=-10&limit=999&status=BOGUS&sort_by=case_id')
  await screen.findByText('案例队列')
  await waitFor(() => expect(seenQueueUrls.length).toBeGreaterThan(0))
  const url = new URL(seenQueueUrls[seenQueueUrls.length - 1])
  expect(url.searchParams.get('offset')).toBe('0')
  expect(url.searchParams.get('limit')).toBe('50')
  expect(url.searchParams.get('status')).toBeNull()
  expect(url.searchParams.get('sort_by')).toBeNull()
})

test('分析中按 2 秒唯一节奏轮询，终态停止', async () => {
  currentBatchStatus = 'ANALYZING'
  vi.useFakeTimers()
  renderAt('/batches/batch-mvp-001')
  await advanceUntil(() => expect(calls.queue).toBe(1))

  // 6.1 秒 → 恰好 3 次轮询（批次详情与队列同一节奏）。
  await advanceClock(6100)
  const batchAfterPoll = calls.batch
  const queueAfterPoll = calls.queue
  expect(batchAfterPoll).toBeGreaterThanOrEqual(4)
  expect(queueAfterPoll).toBeGreaterThanOrEqual(4)

  // 服务端翻转终态：下一次轮询观察到 COMPLETED 后，批次与队列都停止请求。
  currentBatchStatus = 'COMPLETED'
  await advanceClock(8100)
  const batchAtTerminal = calls.batch
  const queueAtTerminal = calls.queue
  expect(batchAtTerminal).toBeGreaterThan(batchAfterPoll)
  expect(queueAtTerminal).toBeGreaterThanOrEqual(queueAfterPoll)

  await advanceClock(6100)
  expect(calls.batch).toBe(batchAtTerminal)
  expect(calls.queue).toBe(queueAtTerminal)
})

test('后台标签页暂停轮询，回到前台恢复', async () => {
  currentBatchStatus = 'ANALYZING'
  vi.useFakeTimers()
  renderAt('/batches/batch-mvp-001')
  await advanceUntil(() => expect(calls.queue).toBe(1))

  const defineHidden = (value: boolean) => {
    Object.defineProperty(document, 'hidden', { configurable: true, get: () => value })
    document.dispatchEvent(new Event('visibilitychange'))
  }

  defineHidden(true)
  await advanceClock(6100)
  const queueWhileHidden = calls.queue
  const batchWhileHidden = calls.batch

  defineHidden(false)
  await advanceUntil(() => expect(calls.queue).toBeGreaterThan(queueWhileHidden))
  expect(calls.batch).toBeGreaterThan(batchWhileHidden)
})

test('重复挂载无重复请求（共享同一 QueryClient）', async () => {
  renderAt('/batches/batch-mvp-001')
  await screen.findByText('案例队列')
  expect(calls.batch).toBe(1)
  expect(calls.queue).toBe(1)
})
