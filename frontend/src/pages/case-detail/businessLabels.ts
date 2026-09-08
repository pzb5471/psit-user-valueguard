import type { ComponentType } from 'react'
import { CheckCircleFilled, CloseCircleFilled } from '@ant-design/icons'
import type { components } from '../../api/schema.gen'

type BusinessCause = components['schemas']['BusinessCause']
type AttributionFallbackCause = components['schemas']['AttributionFallbackCause']
type ActionType = components['schemas']['ActionType']

type LabelItem<Kind extends string> = {
  kind: Kind
  label: string
  Icon: ComponentType<{ 'aria-hidden'?: boolean; className?: string }>
  className: 'success' | 'warning' | 'danger' | 'neutral'
}

const CAUSE_MAP: Record<BusinessCause, LabelItem<BusinessCause>> = {
  LOGISTICS_FULFILLMENT: {
    kind: 'LOGISTICS_FULFILLMENT',
    label: '物流履约',
    Icon: CheckCircleFilled,
    className: 'warning',
  },
  PRODUCT_ISSUE: { kind: 'PRODUCT_ISSUE', label: '商品问题', Icon: CheckCircleFilled, className: 'danger' },
  RETURN_REFUND: { kind: 'RETURN_REFUND', label: '退换退款', Icon: CheckCircleFilled, className: 'warning' },
  SERVICE_COMMUNICATION: {
    kind: 'SERVICE_COMMUNICATION',
    label: '服务沟通',
    Icon: CheckCircleFilled,
    className: 'warning',
  },
  PRICE_OR_BENEFIT: { kind: 'PRICE_OR_BENEFIT', label: '价格与权益', Icon: CheckCircleFilled, className: 'warning' },
  OTHER: { kind: 'OTHER', label: '其他', Icon: CheckCircleFilled, className: 'neutral' },
}

/** 归因无法可靠判断时的兜底原因（AttributionFallbackCause v1 固定为 INSUFFICIENT_EVIDENCE）。 */
const FALLBACK_MAP: Record<AttributionFallbackCause, LabelItem<AttributionFallbackCause>> = {
  INSUFFICIENT_EVIDENCE: {
    kind: 'INSUFFICIENT_EVIDENCE',
    label: '证据不足',
    Icon: CloseCircleFilled,
    className: 'neutral',
  },
}

type CauseKind = BusinessCause | AttributionFallbackCause

const ACTION_MAP: Record<ActionType, LabelItem<ActionType>> = {
  EVIDENCE_CHECK: { kind: 'EVIDENCE_CHECK', label: '核实证据', Icon: CheckCircleFilled, className: 'neutral' },
  CUSTOMER_CONTACT: { kind: 'CUSTOMER_CONTACT', label: '联系客户', Icon: CheckCircleFilled, className: 'neutral' },
  FULFILLMENT_ESCALATION: {
    kind: 'FULFILLMENT_ESCALATION',
    label: '履约升级',
    Icon: CheckCircleFilled,
    className: 'warning',
  },
  REPLACEMENT_RETURN_REFUND_CHECK: {
    kind: 'REPLACEMENT_RETURN_REFUND_CHECK',
    label: '换货退换核查',
    Icon: CheckCircleFilled,
    className: 'warning',
  },
  APOLOGY_COMPENSATION_RETENTION_REQUEST: {
    kind: 'APOLOGY_COMPENSATION_RETENTION_REQUEST',
    label: '致歉补偿挽留',
    Icon: CheckCircleFilled,
    className: 'neutral',
  },
  NO_ACTION_MONITOR: { kind: 'NO_ACTION_MONITOR', label: '暂不动作观察', Icon: CloseCircleFilled, className: 'success' },
}

export function presentCause(cause: CauseKind): LabelItem<CauseKind> {
  if (cause === 'INSUFFICIENT_EVIDENCE') {
    return FALLBACK_MAP[cause]
  }
  return CAUSE_MAP[cause as BusinessCause]
}

export function presentAction(action: ActionType): LabelItem<ActionType> {
  return ACTION_MAP[action]
}