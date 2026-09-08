import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import { toResult } from '../api/errors'
import type { RequestResult } from '../api/errors'
import type { components } from '../api/schema.gen'
import { queryKeys } from './queryKeys'

type CaseDetailView = components['schemas']['CaseDetailView']

/** 案例详情（规格 12.2：can_review=true 时携带 review_token 与 review_options）。 */
export function useCaseDetailQuery(batchId: string, caseId: string) {
  return useQuery({
    queryKey: queryKeys.caseDetail(batchId, caseId),
    queryFn: async (): Promise<RequestResult<CaseDetailView>> =>
      toResult(
        api.GET('/api/v1/batches/{batch_id}/cases/{case_id}', {
          params: { path: { batch_id: batchId, case_id: caseId } },
        }),
      ),
    staleTime: 15_000,
    retry: false,
  })
}