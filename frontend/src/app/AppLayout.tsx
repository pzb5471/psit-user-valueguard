import { useLocation } from 'react-router-dom'
import type { ReactNode } from 'react'
import styles from './AppLayout.module.css'

/** 从路由推导次导航上下文标签；M4-01 阶段不读取任何业务数据。 */
function useSubNavLabel(pathname: string): string {
  if (/^\/batches\/[^/]+\/cases\/[^/]+$/.test(pathname)) {
    return '案例详情'
  }
  if (/^\/batches\/[^/]+$/.test(pathname)) {
    return '批次'
  }
  return '工作台'
}

/** 全局布局骨架：44px 黑色顶部栏 + 52px 浅灰次导航 + 最大 1440px 主内容（规格 13.6）。 */
export function AppLayout({ children }: { children: ReactNode }) {
  const { pathname } = useLocation()
  const label = useSubNavLabel(pathname)

  return (
    <div className={styles.shell}>
      <header className={styles.topBar}>
        <span className={styles.brand}>PSIT 工作台</span>
      </header>
      <nav className={styles.subNav} aria-label="当前页面">
        <span className={styles.subNavLabel}>{label}</span>
      </nav>
      <main className={styles.content}>{children}</main>
    </div>
  )
}
