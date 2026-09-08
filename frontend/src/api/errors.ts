import type { components } from './schema.gen'

/** 统一 JSON 错误结构（规格 12.4），字段与后端 BusinessError 完全同源。 */
export type BusinessError = components['schemas']['BusinessError']

/**
 * 请求失败的三种形态：
 * - business：后端返回的 BusinessError（合同原样，不发明新 code）。
 * - unparseable：非 JSON 错误响应（如代理/网关页面），保留状态码与原文供展示层判断。
 * - network：请求未到达后端（断网、连接被拒）。
 */
export type RequestFailure =
  | { kind: 'business'; status: number; error: BusinessError }
  | { kind: 'unparseable'; status: number; bodyText: string }
  | { kind: 'network'; message: string }

/** 集中错误层的统一结果：调用方先看 ok，再分支处理，不直接触碰 Response。 */
export type RequestResult<TData> =
  | { ok: true; data: TData; status: number }
  | { ok: false; failure: RequestFailure; status: number }

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

/** 只按合同字段判断错误体，不使用 any 断言绕过类型。 */
function isBusinessErrorShape(value: unknown): value is BusinessError {
  return isRecord(value) && typeof value.code === 'string' && typeof value.message === 'string'
}

/**
 * 把 openapi-fetch 的 { data, error, response } 调用收敛为 RequestResult。
 * BusinessError 从响应体原样解析；请求体读取失败或网络异常分别归入 unparseable / network。
 */
export async function toResult<TData>(
  call: Promise<{ data?: TData; error?: unknown; response: Response }>,
): Promise<RequestResult<TData>> {
  let settled: { data?: TData; error?: unknown; response: Response }
  try {
    settled = await call
  } catch (cause) {
    return {
      ok: false,
      status: 0,
      failure: { kind: 'network', message: cause instanceof Error ? cause.message : String(cause) },
    }
  }

  const { data, error, response } = settled
  if (response.ok && error === undefined) {
    return { ok: true, data: data as TData, status: response.status }
  }

  if (isBusinessErrorShape(error)) {
    return { ok: false, status: response.status, failure: { kind: 'business', status: response.status, error } }
  }

  let bodyText = ''
  if (isRecord(error)) {
    try {
      bodyText = JSON.stringify(error)
    } catch {
      bodyText = String(error)
    }
  } else {
    bodyText = String(error ?? '')
  }
  return { ok: false, status: response.status, failure: { kind: 'unparseable', status: response.status, bodyText } }
}
