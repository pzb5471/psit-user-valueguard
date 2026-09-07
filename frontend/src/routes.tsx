import { Navigate, Route, Routes } from 'react-router-dom'
import { WorkspacePage } from './pages/workspace/WorkspacePage'
import { BatchPage } from './pages/batch/BatchPage'
import { CaseDetailPage } from './pages/case-detail/CaseDetailPage'

/** 三个固定业务地址（规格 13.2）；未知地址一律回到工作台。 */
export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<WorkspacePage />} />
      <Route path="/batches/:batchId" element={<BatchPage />} />
      <Route path="/batches/:batchId/cases/:caseId" element={<CaseDetailPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
