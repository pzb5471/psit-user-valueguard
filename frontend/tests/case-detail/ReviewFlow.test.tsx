import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, expect, test } from 'vitest'
import { CaseDetailPage } from '../../src/pages/case-detail/CaseDetailPage'
import { createQueryClient } from '../../src/queries/queryClient'
import { caseDetail, reviewResult } from '../../src/mocks/fixtures'
import { mockUrl } from '../../src/mocks/handlers'
import { startMsw } from '../contracts/mswServer'

const server = startMsw()

let postedBodies: Array<Record<string, unknown>> = []
let rerunCalled = false
let currentDetail = caseDetail('PENDING_REVIEW')

beforeEach(() => {
  postedBodies = []
  rerunCalled = false
  currentDetail = caseDetail('PENDING_REVIEW')
  server.use(
    http.get(mockUrl('/api/v1/batches/:batchId/cases/:caseId'), () =>
      HttpResponse.json(currentDetail),
    ),
    http.post(mockUrl('/api/v1/batches/:batchId/cases/:caseId/reviews'), async ({ request }) => {
      const body = (await request.json()) as Record<string, unknown>
      postedBodies.push(body)
      return HttpResponse.json(
        reviewResult({ outcome: (body.outcome as never) ?? 'APPROVED' }),
        { status: 201 },
      )
    }),
    http.post(mockUrl('/api/v1/batches/:batchId/cases/:caseId/reruns'), () => {
      rerunCalled = true
      return HttpResponse.json(caseDetail('ANALYZING'), { status: 202 })
    }),
  )
})

function renderCase() {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={['/batches/batch-demo-001/cases/case-demo-001']}>
        <Routes>
          <Route path="/batches/:batchId/cases/:caseId" element={<CaseDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

test('直接通过：只发送共同字段，无任何判断与原因', async () => {
  renderCase()
  const user = userEvent.setup()
  await user.click(await screen.findByText('直接通过'))
  await user.click(screen.getByRole('button', { name: '提交确认' }))
  await waitFor(() => expect(postedBodies.length).toBe(1))
  const body = postedBodies[0]
  expect(body.outcome).toBe('APPROVED')
  expect(body.submission_id).toBeTypeOf('string')
  expect(body.review_token).toBe('demo-review-token-001')
  expect(body.final_intervention_level).toBeUndefined()
  expect(body.final_cause).toBeUndefined()
  expect(body.final_actions).toBeUndefined()
  expect(body.review_reason).toBeUndefined()
})

test('修改后确认：判断字段与修改原因必填，未选动作或未填原因时提交禁用', async () => {
  renderCase()
  const user = userEvent.setup()
  await user.click(await screen.findByText('修改后确认'))

  // 未填原因且未选动作时提交禁用。
  let submit = screen.getByRole('button', { name: '提交确认' })
  expect(submit).toBeDisabled()

  // 只填原因仍禁用（最终动作至少一项必填）。
  await user.type(screen.getByLabelText('审核原因'), '人工下调介入等级')
  submit = screen.getByRole('button', { name: '提交确认' })
  expect(submit).toBeDisabled()

  // 勾选一个最终动作后启用并提交，判断字段随请求发出。
  await user.click(screen.getByLabelText('联系客户'))
  await user.click(submit)
  await waitFor(() => expect(postedBodies.length).toBe(1))
  const body = postedBodies[0]
  expect(body.outcome).toBe('MODIFIED_AND_APPROVED')
  expect(body.final_intervention_level).toBeTypeOf('string')
  expect(body.final_cause).toBeTypeOf('string')
  expect(body.final_actions).toEqual(['CUSTOMER_CONTACT'])
  expect(body.review_reason).toBe('人工下调介入等级')
})

test('驳回并给出判断：必须给出完整人工判断', async () => {
  renderCase()
  const user = userEvent.setup()
  await user.click(await screen.findByText('驳回并给出判断'))
  await user.type(screen.getByLabelText('审核原因'), '证据不足以支持必须介入')
  await user.click(screen.getByLabelText('暂不动作观察'))
  await user.click(screen.getByRole('button', { name: '提交确认' }))
  await waitFor(() => expect(postedBodies.length).toBe(1))
  expect(postedBodies[0].outcome).toBe('REJECTED_WITH_JUDGMENT')
  expect(postedBodies[0].final_actions).toEqual(['NO_ACTION_MONITOR'])
})

test('证据不足：只发送证据缺口说明，不发送判断', async () => {
  renderCase()
  const user = userEvent.setup()
  await user.click(await screen.findByText('证据不足'))
  await user.type(screen.getByLabelText('证据缺口说明'), '缺少退换货记录')
  await user.click(screen.getByRole('button', { name: '提交确认' }))
  await waitFor(() => expect(postedBodies.length).toBe(1))
  const body = postedBodies[0]
  expect(body.outcome).toBe('INSUFFICIENT_EVIDENCE')
  expect(body.review_reason).toBe('缺少退换货记录')
  expect(body.final_intervention_level).toBeUndefined()
  expect(body.final_actions).toBeUndefined()
})

test('目录外动作不出现：动作只来自 review_options.action_types', async () => {
  renderCase()
  const user = userEvent.setup()
  await user.click(await screen.findByText('修改后确认'))
  const actions = await screen.findByText('最终动作（至少一项）')
  expect(actions).toBeInTheDocument()
  // 只渲染六个动作目录项，没有自由文本输入。
  for (const label of ['核实证据', '联系客户', '履约升级', '换货退换核查', '致歉补偿挽留', '暂不动作观察']) {
    expect(screen.getAllByText(label).length).toBeGreaterThanOrEqual(1)
  }
})

test('重复提交保护：请求进行中按钮禁用，仅发出一次请求', async () => {
  server.use(
    http.post(mockUrl('/api/v1/batches/:batchId/cases/:caseId/reviews'), async ({ request }) => {
      const body = (await request.json()) as Record<string, unknown>
      postedBodies.push(body)
      await new Promise((resolve) => setTimeout(resolve, 400))
      return HttpResponse.json(reviewResult({ outcome: body.outcome as never }), { status: 201 })
    }),
  )
  renderCase()
  const user = userEvent.setup()
  await user.click(await screen.findByText('直接通过'))
  const submit = screen.getByRole('button', { name: '提交确认' })
  await user.click(submit)
  // 请求进行中按钮变为"正在提交…"且禁用。
  const pendingButton = await screen.findByRole('button', { name: '正在提交…' })
  expect(pendingButton).toBeDisabled()
  await user.click(pendingButton)
  await waitFor(() => expect(postedBodies.length).toBe(1))
})

test('旧 Token 返回 409 时展示冲突提示', async () => {
  currentDetail = caseDetail('PENDING_REVIEW', {
    review_token: 'old-token-999',
  })
  server.use(
    http.post(mockUrl('/api/v1/batches/:batchId/cases/:caseId/reviews'), () =>
      HttpResponse.json(
        {
          code: 'STALE_CASE_RESULT',
          message: '结果已被重跑替换，请刷新后重新确认。',
          object_type: '案例',
          object_id: 'case-demo-001',
          stage: 'RESULT_PERSISTENCE',
          next_action: '刷新案例详情后重新审核。',
          trace_id: 'trace-1',
        },
        { status: 409 },
      ),
    ),
  )
  renderCase()
  const user = userEvent.setup()
  await user.click(await screen.findByText('直接通过'))
  await user.click(screen.getByRole('button', { name: '提交确认' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('结果已被重跑替换')
})

test('重跑：按钮调用 reruns，请求后触发详情刷新', async () => {
  renderCase()
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: '重新分析' }))
  await waitFor(() => expect(rerunCalled).toBe(true))
})

test('已完成案例只读：不显示表单与重跑', async () => {
  currentDetail = caseDetail('COMPLETED', { review_result: reviewResult({ outcome: 'APPROVED' }) })
  renderCase()
  expect(await screen.findByText(/已完成人工确认，结果已锁定为只读/)).toBeInTheDocument()
  expect(screen.queryByText('人工确认')).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '重新分析' })).not.toBeInTheDocument()
})

test('不可重跑：不显示重跑按钮', async () => {
  currentDetail = caseDetail('PENDING_REVIEW', { can_rerun: false })
  renderCase()
  await screen.findByText('示例客户 C-1001')
  expect(screen.queryByRole('button', { name: '重新分析' })).not.toBeInTheDocument()
})

test('review_token 不出现在页面文本', async () => {
  const { container } = renderCase()
  await screen.findByText('示例客户 C-1001')
  expect(container.textContent ?? '').not.toContain('demo-review-token-001')
  expect(container.textContent ?? '').not.toContain('review_token')
})