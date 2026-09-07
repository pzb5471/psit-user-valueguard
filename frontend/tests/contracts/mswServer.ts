import { setupServer } from 'msw/node'
import { afterAll, afterEach, beforeAll } from 'vitest'
import { defaultHandlers } from '../../src/mocks/handlers'

/** 启动 MSW（默认正常路径 handlers，未匹配请求按错误处理），并挂接生命周期。 */
export function startMsw() {
  const server = setupServer(...defaultHandlers)
  beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
  afterEach(() => server.resetHandlers())
  afterAll(() => server.close())
  return server
}
