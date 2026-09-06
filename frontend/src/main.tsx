import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { BrowserRouter } from 'react-router-dom'
import { AppLayout } from './app/AppLayout'
import { ErrorBoundary } from './app/ErrorBoundary'
import { AppRoutes } from './routes'
import { antdTheme } from './theme/antdTheme'
import './theme/theme.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ConfigProvider locale={zhCN} theme={antdTheme}>
      <ErrorBoundary>
        <BrowserRouter>
          <AppLayout>
            <AppRoutes />
          </AppLayout>
        </BrowserRouter>
      </ErrorBoundary>
    </ConfigProvider>
  </StrictMode>,
)
