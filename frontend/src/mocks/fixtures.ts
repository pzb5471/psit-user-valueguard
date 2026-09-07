import type { components } from '../api/schema.gen'

/**
 * MSW 状态样例（M4-02）。全部使用生成类型标注：枚举值与必填字段由合同类型校验，
 * 不存在第二套 DTO 或手写枚举声明。数据均为虚构 Mock 内容。
 */
type BatchWorkspaceView = components['schemas']['BatchWorkspaceView']
type BatchStatus = components['schemas']['BatchStatus']
type BatchListView = components['schemas']['BatchListView']
type CaseQueueView = components['schemas']['CaseQueueView']
type CaseQueueItemView = components['schemas']['CaseQueueItemView']
type CaseStatus = components['schemas']['CaseStatus']
type CaseDetailView = components['schemas']['CaseDetailView']
type HealthView = components['schemas']['HealthView']
type ReviewResultView = components['schemas']['ReviewResultView']
type ReviewOptionsView = components['schemas']['ReviewOptionsView']
type BusinessError = components['schemas']['BusinessError']
type CauseView = components['schemas']['CauseView']
type ActionView = components['schemas']['ActionView']
type CitedEvidenceView = components['schemas']['CitedEvidenceView']

const MOCK_TRACE_ID = 'trace-demo-0001'
const IMPORTED_AT = '2026-09-06T09:30:00+08:00'

export function businessError(overrides: Partial<BusinessError> & { code: string; message: string }): BusinessError {
  return {
    object_type: '批次',
    stage: 'INPUT_PREPARATION',
    next_action: '请检查运行包后重新导入。',
    object_id: null,
    trace_id: MOCK_TRACE_ID,
    ...overrides,
  }
}

export function batchView(status: BatchStatus, overrides: Partial<BatchWorkspaceView> = {}): BatchWorkspaceView {
  const analysisRunning = status === 'ANALYZING'
  return {
    batch_id: 'batch-demo-001',
    source_filename: 'demo_batch_v1.zip',
    is_mock: true,
    status,
    case_count: 8,
    evidence_count: 21,
    analysis_succeeded_count: status === 'PENDING_ANALYSIS' || analysisRunning ? 0 : 7,
    error_count: status === 'COMPLETED_WITH_ERRORS' ? 1 : 0,
    imported_at: IMPORTED_AT,
    can_start_analysis: status === 'PENDING_ANALYSIS',
    analysis_unavailable_message: null,
    ...overrides,
  }
}

export function batchListView(): BatchListView {
  return {
    items: [batchView('ANALYZING'), batchView('COMPLETED', { batch_id: 'batch-demo-000' })],
    total: 2,
  }
}

export function queueItem(status: CaseStatus, overrides: Partial<CaseQueueItemView> = {}): CaseQueueItemView {
  return {
    case_id: 'case-demo-001',
    customer_display_id: '示例客户 C-1001',
    is_high_value: true,
    risk_summary: status === 'PENDING_ANALYSIS' || status === 'ANALYZING' ? null : '物流履约多次延误引发不满。',
    intervention_level:
      status === 'PENDING_REVIEW'
        ? 'MUST_INTERVENE'
        : status === 'COMPLETED'
          ? 'SHOULD_INTERVENE'
          : null,
    priority_reason: status === 'PROCESSING_ERROR' ? '证据读取失败，需要人工跟进。' : null,
    status,
    has_evidence_conflict: false,
    has_insufficient_evidence: false,
    has_modality_failure: status === 'PROCESSING_ERROR',
    ...overrides,
  }
}

export function queueView(): CaseQueueView {
  return {
    items: [
      queueItem('PROCESSING_ERROR', { case_id: 'case-demo-101' }),
      queueItem('PENDING_REVIEW', { case_id: 'case-demo-001' }),
      queueItem('COMPLETED', { case_id: 'case-demo-002', customer_display_id: '示例客户 C-1002' }),
      queueItem('ANALYZING', { case_id: 'case-demo-003' }),
      queueItem('PENDING_ANALYSIS', { case_id: 'case-demo-004' }),
    ],
    total: 5,
  }
}

export function primaryCause(overrides: Partial<CauseView> = {}): CauseView {
  return {
    category: 'LOGISTICS_FULFILLMENT',
    explanation: '示例：连续两单配送超时且客服承诺未兑现（Mock 数据）。',
    evidence_ids: ['evd-text-001', 'evd-img-001'],
    counter_evidence_ids: null,
    uncertainty: null,
    ...overrides,
  }
}

export function sampleAction(overrides: Partial<ActionView> = {}): ActionView {
  return {
    action_type: 'CUSTOMER_CONTACT',
    description: '示例：48 小时内由专属客服主动致歉并同步处理进度。',
    reason: '主要原因为物流履约沟通缺口。',
    evidence_ids: ['evd-text-001'],
    precondition: null,
    ...overrides,
  }
}

export function citedEvidence(
  overrides: Partial<CitedEvidenceView> & { evidence_id: string; modality: CitedEvidenceView['modality'] },
): CitedEvidenceView {
  return {
    label: '示例证据',
    text: null,
    summary: null,
    ...overrides,
  }
}

export function caseDetail(
  status: CaseStatus,
  overrides: Partial<CaseDetailView> = {},
): CaseDetailView {
  const canReview = status === 'PENDING_REVIEW'
  const erroring = status === 'PROCESSING_ERROR'
  const analyzed = status === 'PENDING_REVIEW' || status === 'COMPLETED'
  return {
    batch_id: 'batch-demo-001',
    case_id: 'case-demo-001',
    customer_display_id: '示例客户 C-1001',
    is_high_value: true,
    customer_value_summary: '示例：近 12 个月累计消费 8420 元，共 23 笔订单（Mock 数据）。',
    status,
    intervention_level: analyzed ? 'MUST_INTERVENE' : null,
    risk_summary: analyzed ? '物流履约多次延误引发不满，存在流失风险。' : null,
    primary_cause: analyzed ? primaryCause() : null,
    actions: analyzed ? [sampleAction()] : null,
    communication_points: analyzed ? ['先确认补发进度', '说明赔偿方案'] : null,
    uncertainty: analyzed ? ['客户是否接受补偿方案尚不确定'] : null,
    missing_evidence: null,
    cited_evidence: analyzed
      ? [
          citedEvidence({ evidence_id: 'evd-text-001', modality: 'TEXT', label: '客服对话', text: '示例：客户质问为何又延迟。' }),
          citedEvidence({ evidence_id: 'evd-img-001', modality: 'IMAGE', label: '商品照片', summary: '示例：外包装破损照片。' }),
        ]
      : null,
    is_mock: true,
    review_result: null,
    processing_error: erroring
      ? {
          code: 'EVIDENCE_READ_FAILED',
          message: '证据文件读取失败，无法完成分析。',
          stage: 'EVIDENCE_PROCESSING',
          next_action: '可对该案例发起重跑；若仍失败请联系团队。',
          trace_id: MOCK_TRACE_ID,
        }
      : null,
    can_rerun: status === 'PENDING_REVIEW' || erroring,
    can_review: canReview,
    review_token: canReview ? 'demo-review-token-001' : null,
    review_options: canReview ? reviewOptionsView() : null,
    ...overrides,
  }
}

export function reviewOptionsView(): ReviewOptionsView {
  return {
    intervention_levels: [
      { value: 'MUST_INTERVENE', label: '必须介入' },
      { value: 'SHOULD_INTERVENE', label: '建议介入' },
      { value: 'NO_IMMEDIATE_INTERVENTION', label: '暂无需介入' },
    ],
    cause_categories: [
      { value: 'LOGISTICS_FULFILLMENT', label: '物流履约' },
      { value: 'PRODUCT_ISSUE', label: '商品问题' },
      { value: 'RETURN_REFUND', label: '退换退款' },
      { value: 'SERVICE_COMMUNICATION', label: '服务沟通' },
      { value: 'PRICE_OR_BENEFIT', label: '价格与权益' },
      { value: 'OTHER', label: '其他' },
    ],
    action_catalog_version: 'v1',
    action_types: [
      { value: 'EVIDENCE_CHECK', label: '核实证据' },
      { value: 'CUSTOMER_CONTACT', label: '联系客户' },
      { value: 'FULFILLMENT_ESCALATION', label: '履约升级' },
      { value: 'REPLACEMENT_RETURN_REFUND_CHECK', label: '换货退换核查' },
      { value: 'APOLOGY_COMPENSATION_RETENTION_REQUEST', label: '致歉补偿挽留' },
      { value: 'NO_ACTION_MONITOR', label: '暂不动作观察' },
    ],
  }
}

export function reviewResult(
  overrides: Partial<ReviewResultView> & { outcome: ReviewResultView['outcome'] },
): ReviewResultView {
  return {
    final_intervention_level: null,
    final_cause: null,
    final_actions: null,
    execution_note: null,
    review_reason: null,
    created_at: '2026-09-06T10:12:00+08:00',
    ...overrides,
  }
}

export function healthView(analysisAvailable: boolean, overrides: Partial<HealthView> = {}): HealthView {
  return {
    app_status: 'READY',
    database_status: 'READY',
    analysis_status: analysisAvailable ? 'AVAILABLE' : 'UNAVAILABLE',
    message: analysisAvailable ? '服务就绪。' : '缺少模型密钥，分析暂不可用；历史结果仍可查看。',
    ...overrides,
  }
}
