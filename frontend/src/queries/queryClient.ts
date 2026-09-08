import { QueryClient } from '@tanstack/react-query'

/**
 * 统一 QueryClient（规格 13.2：TanStack Query 只保存可失效缓存）。
 * retry 关闭：失败由页面显式重试与轮询节奏接管，保持验收确定性。
 */
export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 15_000,
        retry: false,
        refetchOnWindowFocus: true,
      },
    },
  })
}
