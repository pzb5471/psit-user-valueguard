import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import { toResult } from '../api/errors'
import type { RequestResult } from '../api/errors'
import type { components } from '../api/schema.gen'
import type { CaseQueueParams } from '../routing/caseQueueParams'
import { queryKeys } from './queryKeys'

type BatchWorkspaceView = components['schemas']['BatchWorkspaceView']

/** 活动批次的唯一轮询节奏（规格 13.2：2 秒；仅分析中轮询，终态停止，后台暂停）。 */
export const ACTIVE_POLL_MS = 2000

/** 批次工作台视图；分析中按 ACTIVE_POLL_MS 轮询，终态不再请求。 */
export function useBatchDetailQuery(batchId: string) {
  return useQuery({
    queryKey: queryKeys.batchDetail(batchId),
    queryFn: async (): Promise<RequestResult<BatchWorkspaceView>> =>
      toResult(api.GET('/api/v1/batches/{batch_id}', { params: { path: { batch_id: batchId } } })),
    staleTime: 15_000,
    refetchInterval: (query) =>
      query.state.data?.ok && query.state.data.data.status === 'ANALYZING'
        ? ACTIVE_POLL_MS
        : false,
  })
}

/** 案例队列；分析中由页面传入与批次一致的唯一节奏，切页筛选期间保留上一页数据。 */
export function useCaseQueueQuery(
  batchId: string,
  params: CaseQueueParams,
  pollMs: number | false,
) {
  return useQuery({
    queryKey: queryKeys.caseQueue(batchId, params),
    queryFn: async () =>
      toResult(
        api.GET('/api/v1/batches/{batch_id}/cases', {
          params: {
            path: { batch_id: batchId },
            query: {
              status: params.status,
              intervention_level: params.interventionLevel,
              limit: params.limit,
              offset: params.offset,
            },
          },
        }),
      ),
    placeholderData: keepPreviousData,
    staleTime: 15_000,
    refetchInterval: pollMs === false ? false : pollMs,
  })
}
