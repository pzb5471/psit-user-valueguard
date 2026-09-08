import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { expect, test } from 'vitest'
import { CaseDetailPage } from '../../src/pages/case-detail/CaseDetailPage'
import { createQueryClient } from '../../src/queries/queryClient'
import { caseDetail } from '../../src/mocks/fixtures'
import { mockUrl } from '../../src/mocks/handlers'
import { startMsw } from '../contracts/mswServer'

const server = startMsw()

/** 以给定状态与覆盖渲染案例详情（fixtures.caseDetail 已按状态提供风险原因/介入/动作/证据等）。 */
function renderCase(status: Parameters<typeof caseDetail>[0] = 'PENDING_REVIEW', overrides: Parameters<typeof caseDetail>[1] = {}) {
  const detail = caseDetail(status, overrides)
  server.use(
    http.get(mockUrl('/api/v1/batches/:batchId/cases/:caseId'), () =>
      HttpResponse.json(detail),
    ),
  )
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

test('结论优先顺序呈现完整结果', async () => {
  renderCase()
  expect(await screen.findByText('示例客户 C-1001')).toBeInTheDocument()
  // 高价值结论
  expect(screen.getByText('高价值客户')).toBeInTheDocument()
  // 风险原因 + 主因标签
  expect(screen.getByText('物流履约多次延误引发不满，存在流失风险。')).toBeInTheDocument()
  expect(screen.getByText('物流履约')).toBeInTheDocument()
  // 介入等级
  expect(screen.getByText('必须介入')).toBeInTheDocument()
  // 处理建议 + 动作
  expect(screen.getByText('处理建议')).toBeInTheDocument()
  expect(screen.getByText('联系客户')).toBeInTheDocument()
  // 沟通重点
  expect(screen.getByText('沟通重点')).toBeInTheDocument()
  // 不确定性
  expect(screen.getByText('不确定性与证据缺口')).toBeInTheDocument()
  expect(screen.getByText('客户是否接受补偿方案尚不确定')).toBeInTheDocument()
})

test('证据不足：归因兜底标签 + 缺失说明', async () => {
  renderCase('PENDING_REVIEW', {
    primary_cause: {
      category: 'INSUFFICIENT_EVIDENCE',
      explanation: '证据不足，无法可靠判断主要原因。',
      evidence_ids: [],
      counter_evidence_ids: [],
      uncertainty: '缺少关键履约记录',
    },
    missing_evidence: ['缺少退换货记录，无法核实履约承诺'],
  })
  await screen.findByText('示例客户 C-1001')
  expect(screen.getByText('证据不足')).toBeInTheDocument()
  expect(screen.getByText('证据不足，无法可靠判断主要原因。')).toBeInTheDocument()
  expect(screen.getByText(/缺少退换货记录/)).toBeInTheDocument()
})

test('图文冲突：文本证据按需展开', async () => {
  renderCase()
  await screen.findByText('示例客户 C-1001')
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: /客服对话/ }))
  expect(screen.getByText('示例：客户质问为何又延迟。')).toBeInTheDocument()
})

test('图片证据加载失败显示回退提示（不阻断其余）', async () => {
  renderCase()
  await screen.findByText('示例客户 C-1001')
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: /商品照片/ }))
  const img = await screen.findByRole('img', { name: '商品照片' })
  fireEvent.error(img)
  await waitFor(() =>
    expect(screen.getByText('图片暂无法显示，可稍后重试或参考文字摘要。')).toBeInTheDocument(),
  )
})

test('Mock 提示与币种说明', async () => {
  renderCase()
  expect(await screen.findByText('Mock 数据')).toBeInTheDocument()
  expect(
    screen.getByText('Mock 数据金额：源数据未提供币种，请勿据此推断真实客户价值。'),
  ).toBeInTheDocument()
})

test('处理异常展示业务化错误', async () => {
  renderCase('PROCESSING_ERROR')
  await screen.findByText('分析未能完成')
  expect(screen.getByText('证据文件读取失败，无法完成分析。')).toBeInTheDocument()
})

test('页面不出现证据 ID、Token、Prompt、Schema 或本机路径', async () => {
  const { container } = renderCase()
  await screen.findByText('示例客户 C-1001')
  const text = container.textContent ?? ''
  for (const banned of ['evd-text-001', 'Token', 'Prompt', 'Schema', 'C:\\', '/Users/']) {
    expect(text).not.toContain(banned)
  }
})