import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClientProvider } from '@tanstack/react-query'
import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { BrowserRouter } from 'react-router-dom'
import { AppLayout } from './app/AppLayout'
import { ErrorBoundary } from './app/ErrorBoundary'
import { AppRoutes } from './routes'
import { antdTheme } from './theme/antdTheme'
import { createQueryClient } from './queries/queryClient'
import './theme/theme.css'

const queryClient = createQueryClient()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ConfigProvider locale={zhCN} theme={antdTheme}>
      <QueryClientProvider client={queryClient}>
        <ErrorBoundary>
          <BrowserRouter>
            <AppLayout>
              <AppRoutes />
            </AppLayout>
          </BrowserRouter>
        </ErrorBoundary>
      </QueryClientProvider>
    </ConfigProvider>
  </StrictMode>,
)
