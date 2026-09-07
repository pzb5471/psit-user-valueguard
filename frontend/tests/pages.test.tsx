import { screen } from '@testing-library/react'
import { renderAppAt } from './testUtils'

test('工作台入口页壳在 / 渲染', () => {
  renderAppAt('/')
  expect(screen.getByRole('heading', { level: 1, name: '工作台' })).toBeInTheDocument()
  expect(screen.getByRole('banner')).toHaveTextContent('PSIT 工作台')
  expect(screen.getByRole('navigation', { name: '当前页面' })).toHaveTextContent('工作台')
})

test('批次页壳在 /batches/:batchId 渲染', () => {
  renderAppAt('/batches/batch-001')
  expect(screen.getByRole('heading', { level: 1, name: '批次' })).toBeInTheDocument()
  expect(screen.getByRole('navigation', { name: '当前页面' })).toHaveTextContent('批次')
})

test('案例详情页壳在 /batches/:batchId/cases/:caseId 渲染', () => {
  renderAppAt('/batches/batch-001/cases/case-042')
  expect(screen.getByRole('heading', { level: 1, name: '案例详情' })).toBeInTheDocument()
  expect(screen.getByRole('navigation', { name: '当前页面' })).toHaveTextContent('案例详情')
})

test('未知地址回到工作台', () => {
  renderAppAt('/some/unknown/path')
  expect(screen.getByRole('heading', { level: 1, name: '工作台' })).toBeInTheDocument()
})
