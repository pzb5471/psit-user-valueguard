import { HttpResponse, http } from 'msw'
import type { HttpHandler } from 'msw'
import {
  batchView,
  businessError,
  caseDetail,
  healthView,
  queueView,
  reviewResult,
} from './fixtures'
import { mockUrl } from './handlers'

/**
 * 命名 MSW 场景（M4-02 自动验收：各业务状态与错误合同）。
 * 每个场景只覆盖它要模拟的行为，测试中通过 server.use 叠加在默认 handlers 之上。
 * URL 一律使用 mockUrl() 完整地址（Node 端 path 模式会穿透，见 handlers.ts 说明）。
 */
export const scenarios: Record<string, HttpHandler[]> = {
  /* ---- 批次四种业务状态 ---- */
  'batch.pendingAnalysis': [
    http.get(mockUrl('/api/v1/batches/:batchId'), () =>
      HttpResponse.json(batchView('PENDING_ANALYSIS')),
    ),
  ],
  'batch.analyzing': [
    http.get(mockUrl('/api/v1/batches/:batchId'), () => HttpResponse.json(batchView('ANALYZING'))),
  ],
  'batch.completed': [
    http.get(mockUrl('/api/v1/batches/:batchId'), () => HttpResponse.json(batchView('COMPLETED'))),
  ],
  'batch.completedWithErrors': [
    http.get(mockUrl('/api/v1/batches/:batchId'), () =>
      HttpResponse.json(batchView('COMPLETED_WITH_ERRORS')),
    ),
  ],

  /* ---- 案例五种业务状态 ---- */
  'case.pendingAnalysis': [
    http.get(mockUrl('/api/v1/batches/:batchId/cases/:caseId'), () =>
      HttpResponse.json(caseDetail('PENDING_ANALYSIS')),
    ),
  ],
  'case.analyzing': [
    http.get(mockUrl('/api/v1/batches/:batchId/cases/:caseId'), () =>
      HttpResponse.json(caseDetail('ANALYZING')),
    ),
  ],
  'case.pendingReview': [
    http.get(mockUrl('/api/v1/batches/:batchId/cases/:caseId'), () =>
      HttpResponse.json(caseDetail('PENDING_REVIEW')),
    ),
  ],
  'case.completed': [
    http.get(mockUrl('/api/v1/batches/:batchId/cases/:caseId'), () =>
      HttpResponse.json(caseDetail('COMPLETED')),
    ),
  ],
  'case.processingError': [
    http.get(mockUrl('/api/v1/batches/:batchId/cases/:caseId'), () =>
      HttpResponse.json(caseDetail('PROCESSING_ERROR')),
    ),
  ],

  /* ---- 导入与上传错误 ---- */
  'import.invalidZip': [
    http.post(mockUrl('/api/v1/batches'), () =>
      HttpResponse.json(
        businessError({
          code: 'INVALID_ZIP',
          message: '运行包结构不合格，无法导入。',
          object_type: '运行包',
        }),
        { status: 400 },
      ),
    ),
  ],
  'import.batchIdConflict': [
    http.post(mockUrl('/api/v1/batches'), () =>
      HttpResponse.json(
        businessError({
          code: 'BATCH_ID_CONFLICT',
          message: '相同批次编号对应不同的包内容。',
          object_type: '批次',
          object_id: 'batch-mvp-001',
        }),
        { status: 409 },
      ),
    ),
  ],
  'import.activeBatchExists': [
    http.post(mockUrl('/api/v1/batches'), () =>
      HttpResponse.json(
        businessError({
          code: 'ACTIVE_BATCH_EXISTS',
          message: '已有批量分析正在运行，不能导入新批次。',
          object_type: '批次',
        }),
        { status: 409 },
      ),
    ),
  ],
  'import.uploadTooLarge': [
    http.post(mockUrl('/api/v1/batches'), () =>
      HttpResponse.json(
        businessError({
          code: 'UPLOAD_TOO_LARGE',
          message: 'ZIP 超过允许的上传大小。',
          object_type: '运行包',
        }),
        { status: 413 },
      ),
    ),
  ],
  'import.unsupportedMedia': [
    http.post(mockUrl('/api/v1/batches'), () =>
      HttpResponse.json(
        businessError({
          code: 'UNSUPPORTED_MEDIA_TYPE',
          message: '仅支持 ZIP 格式的运行包。',
          object_type: '运行包',
        }),
        { status: 415 },
      ),
    ),
  ],
  'import.validationFailed': [
    http.post(mockUrl('/api/v1/batches'), () =>
      HttpResponse.json(
        businessError({
          code: 'REQUEST_VALIDATION_FAILED',
          message: '上传内容不符合接口要求。',
          object_type: '运行包',
        }),
        { status: 422 },
      ),
    ),
  ],

  /* ---- 开始分析 ---- */
  'run.analysisUnavailable': [
    http.post(mockUrl('/api/v1/batches/:batchId/runs'), () =>
      HttpResponse.json(
        businessError({
          code: 'ANALYSIS_UNAVAILABLE',
          message: '缺少模型密钥，暂时不能开始分析。',
          object_type: '批次',
          stage: 'AI_ANALYSIS',
          next_action: '配置密钥后再试。',
        }),
        { status: 503 },
      ),
    ),
  ],
  'run.activeBatchExists': [
    http.post(mockUrl('/api/v1/batches/:batchId/runs'), () =>
      HttpResponse.json(
        businessError({
          code: 'ACTIVE_BATCH_EXISTS',
          message: '该批次已有分析正在运行。',
          object_type: '批次',
          object_id: 'batch-mvp-001',
          stage: 'AI_ANALYSIS',
        }),
        { status: 409 },
      ),
    ),
  ],

  /* ---- 队列与详情读取 ---- */
  'read.resourceNotFound': [
    http.get(mockUrl('/api/v1/batches/:batchId'), () =>
      HttpResponse.json(
        businessError({
          code: 'RESOURCE_NOT_FOUND',
          message: '批次不存在。',
          object_type: '批次',
          object_id: 'batch-missing',
        }),
        { status: 404 },
      ),
    ),
  ],
  'read.validationFailed': [
    http.get(mockUrl('/api/v1/batches/:batchId/cases'), () =>
      HttpResponse.json(
        businessError({
          code: 'REQUEST_VALIDATION_FAILED',
          message: '筛选参数不合格。',
          object_type: '案例',
        }),
        { status: 422 },
      ),
    ),
  ],
  'read.serverError': [
    http.get(mockUrl('/api/v1/batches/:batchId'), () =>
      HttpResponse.json(
        businessError({
          code: 'INTERNAL_ERROR',
          message: '服务内部错误，请稍后重试。',
          object_type: '批次',
          stage: 'APP_RECOVERY',
          next_action: '稍后重试或联系团队。',
        }),
        { status: 500 },
      ),
    ),
  ],
  'read.nonJsonError': [
    http.get(mockUrl('/api/v1/batches/:batchId'), () =>
      HttpResponse.html('<html><body>Bad Gateway</body></html>', { status: 502 }),
    ),
  ],

  /* ---- 重跑 ---- */
  'rerun.accepted': [
    http.post(mockUrl('/api/v1/batches/:batchId/cases/:caseId/reruns'), () =>
      HttpResponse.json(caseDetail('ANALYZING', { can_rerun: false }), { status: 202 }),
    ),
  ],
  'rerun.caseAlreadyCompleted': [
    http.post(mockUrl('/api/v1/batches/:batchId/cases/:caseId/reruns'), () =>
      HttpResponse.json(
        businessError({
          code: 'CASE_ALREADY_COMPLETED',
          message: '该案例已完成，不能重跑。',
          object_type: '案例',
          object_id: 'case-mvp-001',
          stage: 'AI_ANALYSIS',
        }),
        { status: 409 },
      ),
    ),
  ],
  'rerun.analysisUnavailable': [
    http.post(mockUrl('/api/v1/batches/:batchId/cases/:caseId/reruns'), () =>
      HttpResponse.json(
        businessError({
          code: 'ANALYSIS_UNAVAILABLE',
          message: '缺少模型密钥，暂时不能重跑。',
          object_type: '案例',
          stage: 'AI_ANALYSIS',
          next_action: '配置密钥后再试。',
        }),
        { status: 503 },
      ),
    ),
  ],

  /* ---- 人工确认 ---- */
  'review.created': [
    http.post(mockUrl('/api/v1/batches/:batchId/cases/:caseId/reviews'), () =>
      HttpResponse.json(reviewResult({ outcome: 'APPROVED' }), { status: 201 }),
    ),
  ],
  'review.idempotentHit': [
    http.post(mockUrl('/api/v1/batches/:batchId/cases/:caseId/reviews'), () =>
      HttpResponse.json(reviewResult({ outcome: 'APPROVED' }), { status: 200 }),
    ),
  ],
  'review.modifiedApproved': [
    http.post(mockUrl('/api/v1/batches/:batchId/cases/:caseId/reviews'), () =>
      HttpResponse.json(
        reviewResult({
          outcome: 'MODIFIED_AND_APPROVED',
          final_intervention_level: 'SHOULD_INTERVENE',
          final_actions: [
            {
              action_type: 'CUSTOMER_CONTACT',
              description: '示例：先电话确认补发时间。',
              reason: '人工判断优先。',
              evidence_ids: [],
              precondition: null,
            },
          ],
          review_reason: '人工下调介入等级。',
        }),
        { status: 201 },
      ),
    ),
  ],
  'review.rejectedWithJudgment': [
    http.post(mockUrl('/api/v1/batches/:batchId/cases/:caseId/reviews'), () =>
      HttpResponse.json(
        reviewResult({
          outcome: 'REJECTED_WITH_JUDGMENT',
          final_intervention_level: 'NO_IMMEDIATE_INTERVENTION',
          final_actions: [
            {
              action_type: 'NO_ACTION_MONITOR',
              description: '示例：维持现状并持续观察。',
              reason: '证据不支持原判断。',
              evidence_ids: [],
              precondition: null,
            },
          ],
          review_reason: '证据不足以支持必须介入。',
        }),
        { status: 201 },
      ),
    ),
  ],
  'review.insufficientEvidence': [
    http.post(mockUrl('/api/v1/batches/:batchId/cases/:caseId/reviews'), () =>
      HttpResponse.json(
        reviewResult({
          outcome: 'INSUFFICIENT_EVIDENCE',
          review_reason: '缺少退换货记录，无法判断。',
        }),
        { status: 201 },
      ),
    ),
  ],
  'review.staleToken': [
    http.post(mockUrl('/api/v1/batches/:batchId/cases/:caseId/reviews'), () =>
      HttpResponse.json(
        businessError({
          code: 'STALE_CASE_RESULT',
          message: '结果已被重跑替换，请刷新后重新确认。',
          object_type: '案例',
          object_id: 'case-mvp-001',
          stage: 'RESULT_PERSISTENCE',
          next_action: '刷新案例详情后重新审核。',
        }),
        { status: 409 },
      ),
    ),
  ],
  'review.caseAlreadyCompleted': [
    http.post(mockUrl('/api/v1/batches/:batchId/cases/:caseId/reviews'), () =>
      HttpResponse.json(
        businessError({
          code: 'CASE_ALREADY_COMPLETED',
          message: '该案例已完成确认。',
          object_type: '案例',
          object_id: 'case-mvp-001',
          stage: 'RESULT_PERSISTENCE',
        }),
        { status: 409 },
      ),
    ),
  ],
  'review.validationFailed': [
    http.post(mockUrl('/api/v1/batches/:batchId/cases/:caseId/reviews'), () =>
      HttpResponse.json(
        businessError({
          code: 'REQUEST_VALIDATION_FAILED',
          message: '确认请求字段不合格。',
          object_type: '确认请求',
        }),
        { status: 422 },
      ),
    ),
  ],

  /* ---- 证据图片 ---- */
  'evidence.notFound': [
    http.get(mockUrl('/api/v1/batches/:batchId/cases/:caseId/evidence/:evidenceId/content'), () =>
      HttpResponse.json(
        businessError({
          code: 'RESOURCE_NOT_FOUND',
          message: '证据不存在。',
          object_type: '证据',
          object_id: 'evd-missing',
        }),
        { status: 404 },
      ),
    ),
  ],
  'evidence.unsupportedMedia': [
    http.get(mockUrl('/api/v1/batches/:batchId/cases/:caseId/evidence/:evidenceId/content'), () =>
      HttpResponse.json(
        businessError({
          code: 'UNSUPPORTED_MEDIA_TYPE',
          message: '证据媒体类型不受支持。',
          object_type: '证据',
        }),
        { status: 415 },
      ),
    ),
  ],

  /* ---- 健康 ---- */
  'health.unavailable': [http.get(mockUrl('/api/v1/health'), () => HttpResponse.json(healthView(false)))],

  /* ---- 队列全状态（供列表场景使用） ---- */
  'queue.allStatuses': [
    http.get(mockUrl('/api/v1/batches/:batchId/cases'), () => HttpResponse.json(queueView())),
  ],
}
