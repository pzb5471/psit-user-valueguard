import type { components } from '../api/schema.gen'

type CaseStatus = components['schemas']['CaseStatus']
type InterventionLevel = components['schemas']['InterventionLevel']

/**
 * 筛选值白名单：由生成类型的联合类型做编译期穷尽性守卫——
 * 后端枚举变化导致生成类型更新时，这里会编译失败提醒同步，不手抄第二套枚举。
 */
const CASE_STATUS_FLAGS: Record<CaseStatus, true> = {
  PENDING_ANALYSIS: true,
  ANALYZING: true,
  PENDING_REVIEW: true,
  COMPLETED: true,
  PROCESSING_ERROR: true,
}
const INTERVENTION_FLAGS: Record<InterventionLevel, true> = {
  MUST_INTERVENE: true,
  SHOULD_INTERVENE: true,
  NO_IMMEDIATE_INTERVENTION: true,
}

export const CASE_STATUS_VALUES = Object.keys(CASE_STATUS_FLAGS) as CaseStatus[]
export const INTERVENTION_LEVEL_VALUES = Object.keys(INTERVENTION_FLAGS) as InterventionLevel[]

/** 规格第 12.1 节：案例列表 limit 默认 50，允许 1—100；offset 默认 0。 */
export const DEFAULT_CASE_LIMIT = 50
export const MIN_CASE_LIMIT = 1
export const MAX_CASE_LIMIT = 100

/** 从 URL 解析出的案例队列位置；非法值一律回落默认，不让服务端收到越界参数。 */
export type CaseQueueParams = {
  status?: CaseStatus
  interventionLevel?: InterventionLevel
  offset: number
  limit: number
}

function parseBoundedInt(raw: string | null, fallback: number, min: number, max: number): number {
  const value = Number(raw)
  if (raw === null || raw === '' || !Number.isInteger(value) || value < min || value > max) {
    return fallback
  }
  return value
}

/** 解析 URL 查询参数；每个筛选只允许一个值（规格 12.1），未知筛选值丢弃。 */
export function parseCaseQueueParams(searchParams: URLSearchParams): CaseQueueParams {
  const rawStatus = searchParams.get('status')
  const rawLevel = searchParams.get('intervention_level')
  return {
    status: CASE_STATUS_VALUES.includes(rawStatus as CaseStatus)
      ? (rawStatus as CaseStatus)
      : undefined,
    interventionLevel: INTERVENTION_LEVEL_VALUES.includes(rawLevel as InterventionLevel)
      ? (rawLevel as InterventionLevel)
      : undefined,
    offset: parseBoundedInt(searchParams.get('offset'), 0, 0, Number.MAX_SAFE_INTEGER),
    limit: parseBoundedInt(
      searchParams.get('limit'),
      DEFAULT_CASE_LIMIT,
      MIN_CASE_LIMIT,
      MAX_CASE_LIMIT,
    ),
  }
}

/** 合并参数补丁并序列化；默认值与空筛选不写入 URL，保持地址简洁。 */
export function writeCaseQueueParams(
  searchParams: URLSearchParams,
  patch: {
    status?: string | null
    intervention_level?: string | null
    offset?: number
    limit?: number
  },
): URLSearchParams {
  const current = parseCaseQueueParams(searchParams)
  const merged = {
    status: patch.status !== undefined ? patch.status : (current.status ?? null),
    intervention_level:
      patch.intervention_level !== undefined
        ? patch.intervention_level
        : (current.interventionLevel ?? null),
    offset: patch.offset ?? current.offset,
    limit: patch.limit ?? current.limit,
  }
  const next = new URLSearchParams()
  if (merged.status) next.set('status', merged.status)
  if (merged.intervention_level) next.set('intervention_level', merged.intervention_level)
  if (merged.offset > 0) next.set('offset', String(merged.offset))
  if (merged.limit !== DEFAULT_CASE_LIMIT) next.set('limit', String(merged.limit))
  return next
}
