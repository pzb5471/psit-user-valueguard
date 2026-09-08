import createClient from 'openapi-fetch'
import type { paths } from './schema.gen'

/** 创建唯一形态的 HTTP 客户端（规格 12：生成类型 + openapi-fetch，禁止手写第二套 DTO）。 */
export function createApiClient(baseUrl?: string) {
  return createClient<paths>({
    baseUrl,
    // createClient 的默认参数会在创建时缓存全局 fetch；改为调用时解析，
    // msw/node 在 listen 时替换的全局 fetch 才能生效。
    // 运行时 openapi-fetch 以 (request, requestInit) 两参调用，第二参可选以匹配其类型声明。
    fetch: (input: Request, init?: RequestInit) => globalThis.fetch(input, init),
  })
}

/** 默认基址：浏览器与组件测试取同源绝对地址（FastAPI 单机同源提供 /api/v1）；纯 Node 环境无 window，由调用方显式传入。 */
function defaultBaseUrl(): string {
  return typeof window === 'undefined' ? '' : window.location.origin
}

/**
 * 应用客户端：生产由 FastAPI 同源提供 /api/v1；
 * 测试通过 createApiClient 注入绝对地址。
 */
export const api = createApiClient(defaultBaseUrl())

/** 组装受控证据图片地址（规格 12.1；只使用公开业务字段，不新增 content_url 字段）。 */
export function evidenceContentUrl(batchId: string, caseId: string, evidenceId: string): string {
  return (
    `/api/v1/batches/${encodeURIComponent(batchId)}` +
    `/cases/${encodeURIComponent(caseId)}` +
    `/evidence/${encodeURIComponent(evidenceId)}/content`
  )
}
