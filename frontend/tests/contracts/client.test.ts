// @vitest-environment node
import { expect, test, vi } from 'vitest'
import { createApiClient, evidenceContentUrl } from '../../src/api/client'
import { toResult } from '../../src/api/errors'
import { startMsw } from './mswServer'

startMsw()

/** 测试用绝对地址：Node fetch 无法解析相对 URL，MSW 按路径匹配处理器。 */
const api = createApiClient('http://psit-mock.local')

const BATCH_ID = 'batch-demo-001'
const CASE_ID = 'case-demo-001'

/** 合同路径模板（规格 12.1），用于断言证据 URL 组装不越界。 */
test('evidenceContentUrl 使用公开业务字段组装受控证据地址', () => {
  expect(evidenceContentUrl('b/1', 'c/2', 'e/3')).toBe(
    '/api/v1/batches/b%2F1/cases/c%2F2/evidence/e%2F3/content',
  )
})

test('接口一：POST /api/v1/batches 上传 ZIP 返回 201', async () => {
  const form = new FormData()
  form.append('file', new Blob([new Uint8Array([0x50, 0x4b])], { type: 'application/zip' }), 'demo_batch_v1.zip')
  const result = await toResult(api.POST('/api/v1/batches', { body: form as never }))
  expect(result.ok).toBe(true)
  if (result.ok) {
    expect(result.status).toBe(201)
    expect(result.data.status).toBe('PENDING_ANALYSIS')
    expect(result.data.can_start_analysis).toBe(true)
  }
})

test('接口二：GET /api/v1/batches 返回批次列表', async () => {
  const result = await toResult(api.GET('/api/v1/batches', { params: { query: { limit: 20, offset: 0 } } }))
  expect(result.ok).toBe(true)
  if (result.ok) {
    expect(result.data.total).toBe(2)
    expect(result.data.items).toHaveLength(2)
  }
})

test('接口三：GET /api/v1/batches/{batch_id} 返回批次视图', async () => {
  const result = await toResult(api.GET('/api/v1/batches/{batch_id}', { params: { path: { batch_id: BATCH_ID } } }))
  expect(result.ok).toBe(true)
  if (result.ok) {
    expect(result.data.batch_id).toBeTypeOf('string')
    expect(result.data.is_mock).toBe(true)
  }
})

test('接口四：POST /api/v1/batches/{batch_id}/runs 返回 202', async () => {
  const result = await toResult(
    api.POST('/api/v1/batches/{batch_id}/runs', { params: { path: { batch_id: BATCH_ID } } }),
  )
  expect(result.ok).toBe(true)
  if (result.ok) {
    expect(result.status).toBe(202)
    expect(result.data.status).toBe('ANALYZING')
  }
})

test('接口五：GET /api/v1/batches/{batch_id}/cases 返回案例队列', async () => {
  const result = await toResult(
    api.GET('/api/v1/batches/{batch_id}/cases', { params: { path: { batch_id: BATCH_ID } } }),
  )
  expect(result.ok).toBe(true)
  if (result.ok) {
    expect(result.data.total).toBe(5)
    expect(result.data.items[0]?.has_modality_failure).toBe(true)
  }
})

test('接口六：GET 案例详情携带 review_token 与 review_options', async () => {
  const result = await toResult(
    api.GET('/api/v1/batches/{batch_id}/cases/{case_id}', {
      params: { path: { batch_id: BATCH_ID, case_id: CASE_ID } },
    }),
  )
  expect(result.ok).toBe(true)
  if (result.ok) {
    expect(result.data.can_review).toBe(true)
    expect(result.data.review_token).toBeTypeOf('string')
    expect(result.data.review_options?.intervention_levels).toHaveLength(3)
    expect(result.data.review_options?.cause_categories).toHaveLength(6)
    expect(result.data.review_options?.action_types).toHaveLength(6)
  }
})

test('接口七：POST 重跑返回 202', async () => {
  const result = await toResult(
    api.POST('/api/v1/batches/{batch_id}/cases/{case_id}/reruns', {
      params: { path: { batch_id: BATCH_ID, case_id: CASE_ID } },
    }),
  )
  expect(result.ok).toBe(true)
  if (result.ok) expect(result.status).toBe(202)
})

test('接口八：POST 人工确认返回 201 ReviewResultView', async () => {
  const result = await toResult(
    api.POST('/api/v1/batches/{batch_id}/cases/{case_id}/reviews', {
      params: { path: { batch_id: BATCH_ID, case_id: CASE_ID } },
      body: {
        submission_id: '11111111-1111-4111-8111-111111111111',
        review_token: 'demo-review-token-001',
        outcome: 'APPROVED',
      },
    }),
  )
  expect(result.ok).toBe(true)
  if (result.ok) {
    expect(result.status).toBe(201)
    expect(result.data.outcome).toBe('APPROVED')
    expect(result.data.created_at).toBeTypeOf('string')
  }
})

test('接口九：GET 证据内容返回图片流', async () => {
  // 证据图片是二进制流：openapi-fetch 对响应做 JSON 解析，
  // 页面（M4-06）用 evidenceContentUrl 直接以 <img>/fetch 加载，与生产用法一致。
  const response = await globalThis.fetch(
    `http://psit-mock.local${evidenceContentUrl(BATCH_ID, CASE_ID, 'evd-img-001')}`,
  )
  expect(response.ok).toBe(true)
  expect(response.headers.get('content-type')).toBe('image/png')
  const body = await response.arrayBuffer()
  expect(body.byteLength).toBeGreaterThan(0)
})

test('接口十：GET /api/v1/health 返回 HealthView', async () => {
  const result = await toResult(api.GET('/api/v1/health'))
  expect(result.ok).toBe(true)
  if (result.ok) {
    expect(result.data.app_status).toBe('READY')
    expect(result.data.analysis_status).toBe('AVAILABLE')
  }
})

test('集中错误层：请求未到达后端时归入 network', async () => {
  const fetchFailure = vi
    .spyOn(globalThis, 'fetch')
    .mockRejectedValueOnce(new TypeError('simulated network failure'))
  try {
    const result = await toResult(api.GET('/api/v1/health'))
    expect(result.ok).toBe(false)
    if (!result.ok) {
      expect(result.failure.kind).toBe('network')
      expect(result.status).toBe(0)
    }
  } finally {
    fetchFailure.mockRestore()
  }
})
