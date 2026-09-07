import { Component } from 'react'
import type { ReactNode } from 'react'
import styles from './ErrorBoundary.module.css'

type ErrorBoundaryProps = {
  children: ReactNode
}

type ErrorBoundaryState = {
  hasError: boolean
}

/** 全局错误边界：渲染失败时给出诚实回退界面，不显示任何伪造数据（规格 13.7）。 */
export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { hasError: false }

  static getDerivedStateFromError(): ErrorBoundaryState {
    return { hasError: true }
  }

  private handleReload = () => {
    window.location.reload()
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className={styles.panel} role="alert">
          <h1 className={styles.title}>页面出现异常</h1>
          <p className={styles.description}>
            界面渲染失败，数据不受影响。请重新加载页面；若问题持续存在，请联系团队处理。
          </p>
          <button type="button" className={styles.reloadButton} onClick={this.handleReload}>
            重新加载
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
