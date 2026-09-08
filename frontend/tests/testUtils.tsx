import { render } from '@testing-library/react'
import { QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { AppLayout } from '../src/app/AppLayout'
import { AppRoutes } from '../src/routes'
import { createQueryClient } from '../src/queries/queryClient'

/** 按指定地址渲染应用骨架（Provider + 布局 + 三固定路由），与 main.tsx 的装配保持一致。 */
export function renderAppAt(route: string): void {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={[route]}>
        <AppLayout>
          <AppRoutes />
        </AppLayout>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}
