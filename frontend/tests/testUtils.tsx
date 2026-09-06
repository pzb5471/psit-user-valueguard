import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { AppLayout } from '../src/app/AppLayout'
import { AppRoutes } from '../src/routes'

/** 按指定地址渲染应用骨架（布局 + 三固定路由），与 main.tsx 的装配保持一致。 */
export function renderAppAt(route: string): void {
  render(
    <MemoryRouter initialEntries={[route]}>
      <AppLayout>
        <AppRoutes />
      </AppLayout>
    </MemoryRouter>,
  )
}
