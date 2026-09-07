import { HttpResponse, http } from 'msw'
import {
  batchListView,
  batchView,
  caseDetail,
  healthView,
  queueView,
  reviewResult,
} from './fixtures'

/**
 * MSW（Node 端）匹配要求完整 URL：path 模式在当前 msw/interceptors 组合下会穿透到真实网络。
 * 浏览器端 MSW（M4-08）装配时按其运行时 origin 另行组装，本模块不承担该职责。
 */
export const MOCK_ORIGIN = 'http://psit-mock.local'

/** 为 handler 组装完整 URL。 */
export function mockUrl(path: string): string {
  return `${MOCK_ORIGIN}${path}`
}

/** 1×1 透明 PNG，作为受控证据图片响应体。 */
const PNG_PIXEL = new Uint8Array([
  0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0x00, 0x00, 0x00, 0x0d, 0x49, 0x48, 0x44, 0x52,
  0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01, 0x08, 0x06, 0x00, 0x00, 0x00, 0x1f, 0x15, 0xc4,
  0x89, 0x00, 0x00, 0x00, 0x0d, 0x49, 0x44, 0x41, 0x54, 0x78, 0x9c, 0x63, 0x00, 0x01, 0x00, 0x00,
  0x05, 0x00, 0x01, 0x0d, 0x0a, 0x2d, 0xb4, 0x00, 0x00, 0x00, 0x00, 0x49, 0x45, 0x4e, 0x44, 0xae,
  0x42, 0x60, 0x82,
])

/** 十个固定接口的默认（正常路径）handlers（规格 12.1）。 */
export const defaultHandlers = [
  http.post(mockUrl('/api/v1/batches'), () =>
    HttpResponse.json(batchView('PENDING_ANALYSIS'), { status: 201 }),
  ),
  http.get(mockUrl('/api/v1/batches'), () => HttpResponse.json(batchListView())),
  http.get(mockUrl('/api/v1/batches/:batchId'), () => HttpResponse.json(batchView('COMPLETED'))),
  http.post(mockUrl('/api/v1/batches/:batchId/runs'), () =>
    HttpResponse.json(batchView('ANALYZING'), { status: 202 }),
  ),
  http.get(mockUrl('/api/v1/batches/:batchId/cases'), () => HttpResponse.json(queueView())),
  http.get(mockUrl('/api/v1/batches/:batchId/cases/:caseId'), () =>
    HttpResponse.json(caseDetail('PENDING_REVIEW')),
  ),
  http.post(mockUrl('/api/v1/batches/:batchId/cases/:caseId/reruns'), () =>
    HttpResponse.json(caseDetail('ANALYZING'), { status: 202 }),
  ),
  http.post(mockUrl('/api/v1/batches/:batchId/cases/:caseId/reviews'), () =>
    HttpResponse.json(reviewResult({ outcome: 'APPROVED' }), { status: 201 }),
  ),
  http.get(
    mockUrl('/api/v1/batches/:batchId/cases/:caseId/evidence/:evidenceId/content'),
    () =>
      HttpResponse.arrayBuffer(PNG_PIXEL.buffer as ArrayBuffer, {
        status: 200,
        headers: { 'Content-Type': 'image/png' },
      }),
  ),
  http.get(mockUrl('/api/v1/health'), () => HttpResponse.json(healthView(true))),
]
