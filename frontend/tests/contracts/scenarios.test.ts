// @vitest-environment node
import { expect, test } from 'vitest'
import { createApiClient } from '../../src/api/client'
import { toResult } from '../../src/api/errors'
import { scenarios } from '../../src/mocks/scenarios'
import { startMsw } from './mswServer'

const server = startMsw()

/** 测试用绝对地址：Node fetch 无法解析相对 URL，MSW 按路径匹配处理器。 */
const api = createApiClient('http://psit-mock.local')

const BATCH = { params: { path: { batch_id: 'batch-demo-001' } } } as const
const CASE = {
  params: { path: { batch_id: 'batch-demo-001', case_id: 'case-demo-001' } },
} as const

/** 每个命名场景的探针：发起对应请求并断言状态与业务判别字段。 */
const probes: Record<string, () => Promise<void>> = {
  'batch.pendingAnalysis': async () => {
    const r = await toResult(api.GET('/api/v1/batches/{batch_id}', BATCH))
    if (!r.ok) throw new Error(String(r.failure))
    expect(r.data.status).toBe('PENDING_ANALYSIS')
    expect(r.data.can_start_analysis).toBe(true)
  },
  'batch.analyzing': async () => {
    const r = await toResult(api.GET('/api/v1/batches/{batch_id}', BATCH))
    if (!r.ok) throw new Error(String(r.failure))
    expect(r.data.status).toBe('ANALYZING')
    expect(r.data.can_start_analysis).toBe(false)
  },
  'batch.completed': async () => {
    const r = await toResult(api.GET('/api/v1/batches/{batch_id}', BATCH))
    if (!r.ok) throw new Error(String(r.failure))
    expect(r.data.status).toBe('COMPLETED')
    expect(r.data.analysis_succeeded_count).toBe(7)
  },
  'batch.completedWithErrors': async () => {
    const r = await toResult(api.GET('/api/v1/batches/{batch_id}', BATCH))
    if (!r.ok) throw new Error(String(r.failure))
    expect(r.data.status).toBe('COMPLETED_WITH_ERRORS')
    expect(r.data.error_count).toBe(1)
  },

  'case.pendingAnalysis': async () => {
    const r = await toResult(api.GET('/api/v1/batches/{batch_id}/cases/{case_id}', CASE))
    if (!r.ok) throw new Error(String(r.failure))
    expect(r.data.status).toBe('PENDING_ANALYSIS')
    expect(r.data.can_review).toBe(false)
  },
  'case.analyzing': async () => {
    const r = await toResult(api.GET('/api/v1/batches/{batch_id}/cases/{case_id}', CASE))
    if (!r.ok) throw new Error(String(r.failure))
    expect(r.data.status).toBe('ANALYZING')
  },
  'case.pendingReview': async () => {
    const r = await toResult(api.GET('/api/v1/batches/{batch_id}/cases/{case_id}', CASE))
    if (!r.ok) throw new Error(String(r.failure))
    expect(r.data.status).toBe('PENDING_REVIEW')
    expect(r.data.review_options).not.toBeNull()
  },
  'case.completed': async () => {
    const r = await toResult(api.GET('/api/v1/batches/{batch_id}/cases/{case_id}', CASE))
    if (!r.ok) throw new Error(String(r.failure))
    expect(r.data.status).toBe('COMPLETED')
    expect(r.data.can_review).toBe(false)
    expect(r.data.intervention_level).toBe('MUST_INTERVENE')
  },
  'case.processingError': async () => {
    const r = await toResult(api.GET('/api/v1/batches/{batch_id}/cases/{case_id}', CASE))
    if (!r.ok) throw new Error(String(r.failure))
    expect(r.data.status).toBe('PROCESSING_ERROR')
    expect(r.data.processing_error?.code).toBe('EVIDENCE_READ_FAILED')
    expect(r.data.processing_error?.stage).toBe('EVIDENCE_PROCESSING')
  },

  'queue.allStatuses': async () => {
    const r = await toResult(api.GET('/api/v1/batches/{batch_id}/cases', BATCH))
    if (!r.ok) throw new Error(String(r.failure))
    const statuses = r.data.items.map((item) => item.status)
    expect(new Set(statuses)).toEqual(
      new Set(['PENDING_ANALYSIS', 'ANALYZING', 'PENDING_REVIEW', 'COMPLETED', 'PROCESSING_ERROR']),
    )
  },

  'import.invalidZip': async () => {
    const r = await toResult(api.POST('/api/v1/batches', { body: undefined as never }))
    expect(r.ok).toBe(false)
    if (!r.ok && r.failure.kind === 'business') {
      expect(r.status).toBe(400)
      expect(r.failure.error.code).toBe('INVALID_ZIP')
    } else {
      throw new Error('应为 business 失败')
    }
  },
  'import.batchIdConflict': async () => {
    const r = await toResult(api.POST('/api/v1/batches', { body: undefined as never }))
    if (!r.ok && r.failure.kind === 'business') {
      expect(r.status).toBe(409)
      expect(r.failure.error.code).toBe('BATCH_ID_CONFLICT')
    } else {
      throw new Error('应为 business 失败')
    }
  },
  'import.activeBatchExists': async () => {
    const r = await toResult(api.POST('/api/v1/batches', { body: undefined as never }))
    if (!r.ok && r.failure.kind === 'business') {
      expect(r.status).toBe(409)
      expect(r.failure.error.code).toBe('ACTIVE_BATCH_EXISTS')
    } else {
      throw new Error('应为 business 失败')
    }
  },
  'import.uploadTooLarge': async () => {
    const r = await toResult(api.POST('/api/v1/batches', { body: undefined as never }))
    if (!r.ok && r.failure.kind === 'business') {
      expect(r.status).toBe(413)
      expect(r.failure.error.code).toBe('UPLOAD_TOO_LARGE')
    } else {
      throw new Error('应为 business 失败')
    }
  },
  'import.unsupportedMedia': async () => {
    const r = await toResult(api.POST('/api/v1/batches', { body: undefined as never }))
    if (!r.ok && r.failure.kind === 'business') {
      expect(r.status).toBe(415)
      expect(r.failure.error.code).toBe('UNSUPPORTED_MEDIA_TYPE')
    } else {
      throw new Error('应为 business 失败')
    }
  },
  'import.validationFailed': async () => {
    const r = await toResult(api.POST('/api/v1/batches', { body: undefined as never }))
    if (!r.ok && r.failure.kind === 'business') {
      expect(r.status).toBe(422)
      expect(r.failure.error.code).toBe('REQUEST_VALIDATION_FAILED')
    } else {
      throw new Error('应为 business 失败')
    }
  },

  'run.analysisUnavailable': async () => {
    const r = await toResult(api.POST('/api/v1/batches/{batch_id}/runs', BATCH))
    if (!r.ok && r.failure.kind === 'business') {
      expect(r.status).toBe(503)
      expect(r.failure.error.code).toBe('ANALYSIS_UNAVAILABLE')
    } else {
      throw new Error('应为 business 失败')
    }
  },
  'run.activeBatchExists': async () => {
    const r = await toResult(api.POST('/api/v1/batches/{batch_id}/runs', BATCH))
    if (!r.ok && r.failure.kind === 'business') {
      expect(r.status).toBe(409)
      expect(r.failure.error.code).toBe('ACTIVE_BATCH_EXISTS')
    } else {
      throw new Error('应为 business 失败')
    }
  },

  'read.resourceNotFound': async () => {
    const r = await toResult(api.GET('/api/v1/batches/{batch_id}', BATCH))
    if (!r.ok && r.failure.kind === 'business') {
      expect(r.status).toBe(404)
      expect(r.failure.error.code).toBe('RESOURCE_NOT_FOUND')
    } else {
      throw new Error('应为 business 失败')
    }
  },
  'read.validationFailed': async () => {
    const r = await toResult(api.GET('/api/v1/batches/{batch_id}/cases', BATCH))
    if (!r.ok && r.failure.kind === 'business') {
      expect(r.status).toBe(422)
      expect(r.failure.error.code).toBe('REQUEST_VALIDATION_FAILED')
    } else {
      throw new Error('应为 business 失败')
    }
  },
  'read.serverError': async () => {
    const r = await toResult(api.GET('/api/v1/batches/{batch_id}', BATCH))
    if (!r.ok && r.failure.kind === 'business') {
      expect(r.status).toBe(500)
      expect(r.failure.error.code).toBe('INTERNAL_ERROR')
    } else {
      throw new Error('应为 business 失败')
    }
  },
  'read.nonJsonError': async () => {
    const r = await toResult(api.GET('/api/v1/batches/{batch_id}', BATCH))
    expect(r.ok).toBe(false)
    if (!r.ok && r.failure.kind === 'unparseable') {
      expect(r.status).toBe(502)
      expect(r.failure.bodyText).toContain('Bad Gateway')
    } else {
      throw new Error('应为 unparseable 失败')
    }
  },

  'rerun.accepted': async () => {
    const r = await toResult(
      api.POST('/api/v1/batches/{batch_id}/cases/{case_id}/reruns', CASE),
    )
    if (!r.ok) throw new Error(String(r.failure))
    expect(r.status).toBe(202)
    expect(r.data.can_rerun).toBe(false)
  },
  'rerun.caseAlreadyCompleted': async () => {
    const r = await toResult(
      api.POST('/api/v1/batches/{batch_id}/cases/{case_id}/reruns', CASE),
    )
    if (!r.ok && r.failure.kind === 'business') {
      expect(r.status).toBe(409)
      expect(r.failure.error.code).toBe('CASE_ALREADY_COMPLETED')
    } else {
      throw new Error('应为 business 失败')
    }
  },
  'rerun.analysisUnavailable': async () => {
    const r = await toResult(
      api.POST('/api/v1/batches/{batch_id}/cases/{case_id}/reruns', CASE),
    )
    if (!r.ok && r.failure.kind === 'business') {
      expect(r.status).toBe(503)
      expect(r.failure.error.code).toBe('ANALYSIS_UNAVAILABLE')
    } else {
      throw new Error('应为 business 失败')
    }
  },

  'review.created': async () => {
    const r = await reviewProbe()
    expect(r.status).toBe(201)
    if (r.kind === 'ok') expect(r.data.outcome).toBe('APPROVED')
  },
  'review.idempotentHit': async () => {
    const r = await reviewProbe()
    expect(r.status).toBe(200)
  },
  'review.modifiedApproved': async () => {
    const r = await reviewProbe()
    expect(r.status).toBe(201)
    if (r.kind === 'ok') expect(r.data.outcome).toBe('MODIFIED_AND_APPROVED')
  },
  'review.rejectedWithJudgment': async () => {
    const r = await reviewProbe()
    expect(r.status).toBe(201)
    if (r.kind === 'ok') expect(r.data.outcome).toBe('REJECTED_WITH_JUDGMENT')
  },
  'review.insufficientEvidence': async () => {
    const r = await reviewProbe()
    expect(r.status).toBe(201)
    if (r.kind === 'ok') expect(r.data.outcome).toBe('INSUFFICIENT_EVIDENCE')
  },
  'review.staleToken': async () => {
    const r = await reviewProbe()
    if (r.kind === 'business') {
      expect(r.status).toBe(409)
      expect(r.error.code).toBe('STALE_CASE_RESULT')
    } else {
      throw new Error('应为 business 失败')
    }
  },
  'review.caseAlreadyCompleted': async () => {
    const r = await reviewProbe()
    if (r.kind === 'business') {
      expect(r.status).toBe(409)
      expect(r.error.code).toBe('CASE_ALREADY_COMPLETED')
    } else {
      throw new Error('应为 business 失败')
    }
  },
  'review.validationFailed': async () => {
    const r = await reviewProbe()
    if (r.kind === 'business') {
      expect(r.status).toBe(422)
      expect(r.error.code).toBe('REQUEST_VALIDATION_FAILED')
    } else {
      throw new Error('应为 business 失败')
    }
  },

  'evidence.notFound': async () => {
    const r = await toResult(
      api.GET('/api/v1/batches/{batch_id}/cases/{case_id}/evidence/{evidence_id}/content', {
        params: { path: { batch_id: 'batch-demo-001', case_id: 'case-demo-001', evidence_id: 'evd-missing' } },
      }),
    )
    if (!r.ok && r.failure.kind === 'business') {
      expect(r.status).toBe(404)
      expect(r.failure.error.code).toBe('RESOURCE_NOT_FOUND')
    } else {
      throw new Error('应为 business 失败')
    }
  },
  'evidence.unsupportedMedia': async () => {
    const r = await toResult(
      api.GET('/api/v1/batches/{batch_id}/cases/{case_id}/evidence/{evidence_id}/content', {
        params: { path: { batch_id: 'batch-demo-001', case_id: 'case-demo-001', evidence_id: 'evd-bad' } },
      }),
    )
    if (!r.ok && r.failure.kind === 'business') {
      expect(r.status).toBe(415)
      expect(r.failure.error.code).toBe('UNSUPPORTED_MEDIA_TYPE')
    } else {
      throw new Error('应为 business 失败')
    }
  },

  'health.unavailable': async () => {
    const r = await toResult(api.GET('/api/v1/health'))
    if (!r.ok) throw new Error(String(r.failure))
    expect(r.data.analysis_status).toBe('UNAVAILABLE')
    expect(r.data.message).toContain('密钥')
  },
}

type ReviewProbe =
  | { kind: 'ok'; status: number; data: { outcome: string } }
  | { kind: 'business'; status: number; error: { code: string } }
  | { kind: 'other'; status: number; failure: unknown }

async function reviewProbe(): Promise<ReviewProbe> {
  const r = await toResult(
    api.POST('/api/v1/batches/{batch_id}/cases/{case_id}/reviews', {
      ...CASE,
      body: {
        submission_id: '22222222-2222-4222-8222-222222222222',
        review_token: 'demo-review-token-001',
        outcome: 'APPROVED',
      },
    }),
  )
  if (r.ok) return { kind: 'ok', status: r.status, data: { outcome: r.data.outcome } }
  if (r.failure.kind === 'business') {
    return { kind: 'business', status: r.status, error: { code: r.failure.error.code } }
  }
  return { kind: 'other', status: r.status, failure: r.failure }
}

test('MSW 场景覆盖全部业务状态与错误合同', async () => {
  const names = Object.keys(scenarios)
  expect(names.length).toBeGreaterThanOrEqual(30)
  for (const name of names) {
    server.use(...scenarios[name])
    await expect(probes[name](), `场景 ${name}`).resolves.toBeUndefined()
  }
})
