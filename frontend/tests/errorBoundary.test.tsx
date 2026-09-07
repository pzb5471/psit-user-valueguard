import { render, screen } from '@testing-library/react'
import { vi } from 'vitest'
import { ErrorBoundary } from '../src/app/ErrorBoundary'

function Boom(): never {
  throw new Error('boom')
}

test('子组件渲染失败时显示诚实回退界面', () => {
  const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
  try {
    render(
      <ErrorBoundary>
        <Boom />
      </ErrorBoundary>,
    )
    expect(screen.getByRole('alert')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '页面出现异常' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '重新加载' })).toBeInTheDocument()
  } finally {
    consoleError.mockRestore()
  }
})

test('正常子组件不受错误边界影响', () => {
  render(
    <ErrorBoundary>
      <p>正常内容</p>
    </ErrorBoundary>,
  )
  expect(screen.getByText('正常内容')).toBeInTheDocument()
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})
