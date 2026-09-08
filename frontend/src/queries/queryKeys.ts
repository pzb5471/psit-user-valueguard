import type { CaseQueueParams } from '../routing/caseQueueParams'

/**
 * TanStack Query 键工厂（规格 13.2：只保存可失效缓存）。
 * caseQueueRoot 作为前缀用于精确失效某批次全部筛选变体。
 */
export const queryKeys = {
  batchDetail: (batchId: string) => ['batches', 'detail', batchId] as const,
  caseQueue: (batchId: string, params: CaseQueueParams) =>
    [
      'batches',
      batchId,
      'cases',
      {
        status: params.status ?? null,
        interventionLevel: params.interventionLevel ?? null,
        offset: params.offset,
        limit: params.limit,
      },
    ] as const,
  caseQueueRoot: (batchId: string) => ['batches', batchId, 'cases'] as const,
}
