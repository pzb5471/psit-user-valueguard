import { render, screen } from '@testing-library/react'
import { fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, expect, test } from 'vitest'
import { WorkspacePage } from '../../src/pages/workspace/WorkspacePage'
import { batchView } from '../../src/mocks/fixtures'
import { mockUrl } from '../../src/mocks/handlers'
import { scenarios } from '../../src/mocks/scenarios'
import { startMsw } from '../contracts/mswServer'

const server = startMsw()

/** 请求计数器：叠加在默认 handlers 之上，验证"导入后零开始请求"。 */
const calls = { create: 0, runs: 0 }
beforeEach(() => {
  calls.create = 0
  calls.runs = 0
})
function trackRequests() {
  server.use(
    http.post(mockUrl('/api/v1/batches'), () => {
      calls.create += 1
      return HttpResponse.json(batchView('PENDING_ANALYSIS'), { status: 201 })
    }),
    http.post(mockUrl('/api/v1/batches/:batchId/runs'), () => {
      calls.runs += 1
      return HttpResponse.json(batchView('ANALYZING'), { status: 202 })
    }),
  )
}

function renderWorkspace() {
  return render(
    <MemoryRouter initialEntries={['/']}>
      <Routes>
        <Route path="/" element={<WorkspacePage />} />
        <Route path="/batches/:batchId" element={<p>已进入批次页</p>} />
      </Routes>
    </MemoryRouter>,
  )
}

function zipFile(name = 'mvp_batch_v1.zip'): File {
  return new File([new Uint8Array([0x50, 0x4b, 0x03, 0x04])], name, { type: 'application/zip' })
}

async function chooseAndImport(file: File) {
  const user = userEvent.setup()
  await user.click(screen.getByText('选择 ZIP 文件'))
  const input = document.querySelector('input[type="file"]') as HTMLInputElement
  await user.upload(input, file)
  await user.click(screen.getByRole('button', { name: '导入批次' }))
  return user
}

test('加载中显示加载状态（列表请求悬挂）', async () => {
  server.use(
    http.get(mockUrl('/api/v1/batches'), async () => {
      await new Promise(() => {})
    }),
  )
  renderWorkspace()
  expect(screen.getByText('正在加载批次信息…')).toBeInTheDocument()
})

test('无批次时进入导入区（空态）', async () => {
  server.use(
    http.get(mockUrl('/api/v1/batches'), () =>
      HttpResponse.json({ items: [], total: 0 }),
    ),
  )
  renderWorkspace()
  expect(await screen.findByText('批次导入')).toBeInTheDocument()
  expect(screen.getByText('选择 ZIP 文件')).toBeInTheDocument()
})

test('有批次时自动进入最近批次', async () => {
  renderWorkspace()
  expect(await screen.findByText('已进入批次页')).toBeInTheDocument()
})

test('非法扩展名本地拒绝且不发起任何请求', async () => {
  trackRequests()
  server.use(
    http.get(mockUrl('/api/v1/batches'), () => HttpResponse.json({ items: [], total: 0 })),
  )
  renderWorkspace()
  await screen.findByText('批次导入')
  // user.upload 会按 accept=".zip" 过滤掉 .txt；真实浏览器里 accept 只是选择器提示，
  // 程序设置文件仍会触发 change——这里直接设置 files 验证组件自身的扩展名拒绝逻辑。
  const input = document.querySelector('input[type="file"]') as HTMLInputElement
  Object.defineProperty(input, 'files', { value: [new File(['文本'], 'notes.txt')] })
  fireEvent.change(input)
  expect(screen.getByRole('alert')).toHaveTextContent('请选择 .zip 格式的运行包。')
  expect(calls.create).toBe(0)
})

test('空文件本地拒绝且不发起任何请求', async () => {
  trackRequests()
  server.use(
    http.get(mockUrl('/api/v1/batches'), () => HttpResponse.json({ items: [], total: 0 })),
  )
  renderWorkspace()
  await screen.findByText('批次导入')
  const user = userEvent.setup()
  await user.click(screen.getByText('选择 ZIP 文件'))
  const input = document.querySelector('input[type="file"]') as HTMLInputElement
  await user.upload(input, new File([], 'empty.zip'))
  expect(screen.getByRole('alert')).toHaveTextContent('文件内容为空')
  expect(calls.create).toBe(0)
})

test('新导入成功：摘要、Mock 提示与下一主动作', async () => {
  trackRequests()
  server.use(
    http.get(mockUrl('/api/v1/batches'), () => HttpResponse.json({ items: [], total: 0 })),
  )
  renderWorkspace()
  await screen.findByText('批次导入')
  await chooseAndImport(zipFile())

  expect(await screen.findByText('文件名')).toBeInTheDocument()
  expect(screen.getByText('mvp_batch_v1.zip')).toBeInTheDocument()
  expect(screen.getByText('8')).toBeInTheDocument()
  expect(screen.getByText('21')).toBeInTheDocument()
  expect(screen.getByText('通过，已导入')).toBeInTheDocument()
  expect(
    screen.getByText('Mock 数据：当前案例包为演示数据，不代表真实客户关系。'),
  ).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '开始分析' })).toBeInTheDocument()
  expect(
    screen.getByText('导入不会自动开始分析；开始分析需要在批次页明确点击。'),
  ).toBeInTheDocument()
  expect(calls.create).toBe(1)
  expect(calls.runs).toBe(0)
})

test('导入成功后零开始请求：点击开始分析只导航，不触发分析接口', async () => {
  trackRequests()
  server.use(
    http.get(mockUrl('/api/v1/batches'), () => HttpResponse.json({ items: [], total: 0 })),
  )
  renderWorkspace()
  await screen.findByText('批次导入')
  const user = await chooseAndImport(zipFile())
  await screen.findByText('通过，已导入')
  await user.click(screen.getByRole('button', { name: '开始分析' }))
  expect(await screen.findByText('已进入批次页')).toBeInTheDocument()
  expect(calls.runs).toBe(0)
})

test('重复导入同一包：幂等命中提示', async () => {
  server.use(
    http.get(mockUrl('/api/v1/batches'), () => HttpResponse.json({ items: [], total: 0 })),
    http.post(mockUrl('/api/v1/batches'), () => {
      calls.create += 1
      return HttpResponse.json(batchView('PENDING_ANALYSIS'), { status: 200 })
    }),
  )
  renderWorkspace()
  await screen.findByText('批次导入')
  await chooseAndImport(zipFile())
  expect(await screen.findByText('该运行包此前已导入，已返回原有批次。')).toBeInTheDocument()
  expect(screen.getByText('通过（幂等命中）')).toBeInTheDocument()
  expect(calls.create).toBe(1)
  expect(calls.runs).toBe(0)
})

test.each([
  ['import.uploadTooLarge', 'ZIP 超过允许的上传大小。', '413'],
  ['import.unsupportedMedia', '仅支持 ZIP 格式的运行包。', '415'],
  ['import.validationFailed', '上传内容不符合接口要求。', '422'],
])('服务器错误 %s（%s，HTTP %s）展示原因与建议', async (scenario, message) => {
  server.use(
    http.get(mockUrl('/api/v1/batches'), () => HttpResponse.json({ items: [], total: 0 })),
    ...scenarios[scenario],
  )
  renderWorkspace()
  await screen.findByText('批次导入')
  await chooseAndImport(zipFile())
  const alert = await screen.findByRole('alert')
  expect(alert).toHaveTextContent('操作未能完成')
  expect(alert).toHaveTextContent(message)
  expect(calls.runs).toBe(0)
})

test('列表加载失败显示异常态，重试后恢复导入区', async () => {
  server.use(http.get(mockUrl('/api/v1/batches'), () => HttpResponse.error()))
  renderWorkspace()
  const user = userEvent.setup()
  expect(await screen.findByRole('alert')).toHaveTextContent('无法连接服务')
  server.use(
    http.get(mockUrl('/api/v1/batches'), () => HttpResponse.json({ items: [], total: 0 })),
  )
  await user.click(screen.getByRole('button', { name: '重新加载' }))
  expect(await screen.findByText('批次导入')).toBeInTheDocument()
})

test('导入成功后展示历史批次入口', async () => {
  const older = batchView('COMPLETED', {
    batch_id: 'batch-mvp-000',
    source_filename: 'acceptance_batch_v1.zip',
  })
  server.use(
    http.get(mockUrl('/api/v1/batches'), () => HttpResponse.json({ items: [], total: 0 })),
  )
  renderWorkspace()
  await screen.findByText('批次导入')
  server.use(
    http.get(mockUrl('/api/v1/batches'), () =>
      HttpResponse.json({
        items: [batchView('PENDING_ANALYSIS', { batch_id: 'batch-mvp-001' }), older],
        total: 2,
      }),
    ),
  )
  await chooseAndImport(zipFile())
  expect(await screen.findByText('历史批次')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'acceptance_batch_v1.zip' })).toHaveAttribute(
    'href',
    '/batches/batch-mvp-000',
  )
  expect(screen.queryByRole('link', { name: 'mvp_batch_v1.zip' })).not.toBeInTheDocument()
})
