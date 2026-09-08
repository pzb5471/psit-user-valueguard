import type { ComponentType } from 'react'
import {
  CheckCircleFilled,
  ClockCircleOutlined,
  CloseCircleFilled,
  ExclamationCircleFilled,
  LoadingOutlined,
  WarningFilled,
} from '@ant-design/icons'
import type { components } from '../../api/schema.gen'

type BatchStatus = components['schemas']['BatchStatus']
type CaseStatus = components['schemas']['CaseStatus']
type InterventionLevel = components['schemas']['InterventionLevel']

/** 状态的三重表达（规格 13.3：文字、图标、颜色缺一不可）。 */
export type StatusPresentation<Kind extends string> = {
  kind: Kind
  label: string
  Icon: ComponentType<{ 'aria-hidden'?: boolean | 'true' | 'false'; className?: string }>
  className: string
}

export type AnyPresentation =
  | StatusPresentation<BatchStatus>
  | StatusPresentation<CaseStatus>
  | StatusPresentation<InterventionLevel>

const NEUTRAL = 'neutral'
const INFO = 'info'
const SUCCESS = 'success'
const WARNING = 'warning'
const DANGER = 'danger'

const BATCH_STATUS_MAP: Record<BatchStatus, StatusPresentation<BatchStatus>> = {
  PENDING_ANALYSIS: {
    kind: 'PENDING_ANALYSIS',
    label: '待分析',
    Icon: ClockCircleOutlined,
    className: NEUTRAL,
  },
  ANALYZING: { kind: 'ANALYZING', label: '分析中', Icon: LoadingOutlined, className: INFO },
  COMPLETED: { kind: 'COMPLETED', label: '已完成', Icon: CheckCircleFilled, className: SUCCESS },
  COMPLETED_WITH_ERRORS: {
    kind: 'COMPLETED_WITH_ERRORS',
    label: '已完成（含错误）',
    Icon: WarningFilled,
    className: WARNING,
  },
}

const CASE_STATUS_MAP: Record<CaseStatus, StatusPresentation<CaseStatus>> = {
  PENDING_ANALYSIS: {
    kind: 'PENDING_ANALYSIS',
    label: '待分析',
    Icon: ClockCircleOutlined,
    className: NEUTRAL,
  },
  ANALYZING: { kind: 'ANALYZING', label: '分析中', Icon: LoadingOutlined, className: INFO },
  PENDING_REVIEW: {
    kind: 'PENDING_REVIEW',
    label: '待确认',
    Icon: ExclamationCircleFilled,
    className: WARNING,
  },
  COMPLETED: { kind: 'COMPLETED', label: '已完成', Icon: CheckCircleFilled, className: SUCCESS },
  PROCESSING_ERROR: {
    kind: 'PROCESSING_ERROR',
    label: '处理异常',
    Icon: CloseCircleFilled,
    className: DANGER,
  },
}

const INTERVENTION_MAP: Record<InterventionLevel, StatusPresentation<InterventionLevel>> = {
  MUST_INTERVENE: {
    kind: 'MUST_INTERVENE',
    label: '必须介入',
    Icon: CloseCircleFilled,
    className: DANGER,
  },
  SHOULD_INTERVENE: {
    kind: 'SHOULD_INTERVENE',
    label: '建议介入',
    Icon: WarningFilled,
    className: WARNING,
  },
  NO_IMMEDIATE_INTERVENTION: {
    kind: 'NO_IMMEDIATE_INTERVENTION',
    label: '暂无需介入',
    Icon: CheckCircleFilled,
    className: SUCCESS,
  },
}

export function presentBatchStatus(status: BatchStatus): StatusPresentation<BatchStatus> {
  return BATCH_STATUS_MAP[status]
}

export function presentCaseStatus(status: CaseStatus): StatusPresentation<CaseStatus> {
  return CASE_STATUS_MAP[status]
}

export function presentInterventionLevel(
  level: InterventionLevel,
): StatusPresentation<InterventionLevel> {
  return INTERVENTION_MAP[level]
}
