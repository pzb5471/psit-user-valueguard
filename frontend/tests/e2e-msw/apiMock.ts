import type { Page } from '@playwright/test'
import type { components } from '../../src/api/schema.gen'
import {
  batchView,
  caseDetail,
  healthView,
  queueItem,
  reviewResult,
} from '../../src/mocks/fixtures'

/**
 * 确定性前端旅程的 API Mock（M4-08）。
 * 用 Playwright 路由拦截（route）把 /api/v1/** 指向 MSW 合同夹具，驱动真实浏览器跑完整旅程。
 * 服务端状态可变，使导入→开始→队列→详情→确认→只读的每一步都确定性可复现。
 */
type CaseStatus = components['schemas']['CaseStatus']

export type MockState = {
  batchStatus: ReturnType<typeof batchView>['status']
  caseStatus: CaseStatus
  reviewPerformed: boolean
}

export function createState(): MockState {
  return { batchStatus: 'PENDING_ANALYSIS', caseStatus: 'PENDING_REVIEW', reviewPerformed: false }
}

const BATCH_ID = 'batch-demo-001'
const CASE_ID = 'case-demo-001'

/** 1×1 透明 PNG，作为受控证据图片响应体。 */
const PNG_PIXEL = Buffer.from(
  '89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c63000100000500010d0a2db40000000049454e44ae426082',
  'hex',
)

/** 为页面安装 /api/v1/** 路由，全部来自 MSW 夹具；返回可变状态供测试推进。 */
export function installApiMock(page: Page, state: MockState) {
  page.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url())
    const { pathname } = url

    const json = (body: unknown, status = 200) =>
      route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })

    if (pathname === '/api/v1/health') {
      return json(healthView(true))
    }

    if (pathname === '/api/v1/batches' && route.request().method() === 'GET') {
      // 初始无批次 → 工作台进入导入区；导入后才产生批次（完整旅程起点）。
      return json({ items: [], total: 0 })
    }
    if (pathname === '/api/v1/batches' && route.request().method() === 'POST') {
      return json(batchView('PENDING_ANALYSIS'), 201)
    }

    if (pathname === `/api/v1/batches/${BATCH_ID}`) {
      return json(batchView(state.batchStatus))
    }

    if (pathname === `/api/v1/batches/${BATCH_ID}/runs` && route.request().method() === 'POST') {
      state.batchStatus = 'ANALYZING'
      return json(batchView('ANALYZING'), 202)
    }

    if (pathname === `/api/v1/batches/${BATCH_ID}/cases` && route.request().method() === 'GET') {
      // 确定性：队列只含目标案例单行，保证可唯一点击。
      return json({ items: [queueItem('PENDING_REVIEW')], total: 1 })
    }

    const caseDetailPattern = new RegExp(`^/api/v1/batches/${BATCH_ID}/cases/${CASE_ID}$`)
    if (caseDetailPattern.test(pathname) && route.request().method() === 'GET') {
      if (state.reviewPerformed) {
        return json(
          caseDetail('COMPLETED', { review_result: reviewResult({ outcome: 'APPROVED' }) }),
        )
      }
      return json(caseDetail(state.caseStatus))
    }

    const rerunPattern = new RegExp(`^/api/v1/batches/${BATCH_ID}/cases/${CASE_ID}/reruns$`)
    if (rerunPattern.test(pathname) && route.request().method() === 'POST') {
      state.caseStatus = 'PENDING_REVIEW'
      return json(caseDetail('PENDING_REVIEW'), 202)
    }

    const reviewPattern = new RegExp(`^/api/v1/batches/${BATCH_ID}/cases/${CASE_ID}/reviews$`)
    if (reviewPattern.test(pathname) && route.request().method() === 'POST') {
      state.reviewPerformed = true
      return json(reviewResult({ outcome: 'APPROVED' }), 201)
    }

    const evidencePattern = new RegExp(
      `^/api/v1/batches/${BATCH_ID}/cases/${CASE_ID}/evidence/[^/]+/content$`,
    )
    if (evidencePattern.test(pathname)) {
      return route.fulfill({
        status: 200,
        contentType: 'image/png',
        body: PNG_PIXEL,
      })
    }

    // 未匹配的 API 视为 404，避免测试误命中生产网络。
    return json({ code: 'RESOURCE_NOT_FOUND', message: 'Mock 未覆盖此接口。' }, 404)
  })
}

/** 断言页面加载过程中未向任何外部主机发起请求（本地打包资源，断网可用）。 */
export function assertNoExternalRequests(page: Page) {
  page.on('request', (request) => {
    const host = new URL(request.url()).host
    if (!host.endsWith('localhost') && !host.startsWith('127.0.0.1')) {
      throw new Error(`页面发起了外部请求：${request.url()}`)
    }
  })
}
