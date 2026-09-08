import type { AnyPresentation } from './statusPresentation'
import tableStyles from './caseQueueTable.module.css'
import styles from './batchPage.module.css'

/** 状态徽章：图标 + 文字 + 颜色类三重表达（供批次摘要带与队列表格共用）。 */
export function StatusBadge({
  presentation,
  tone = 'batch',
}: {
  presentation: AnyPresentation
  tone?: 'batch' | 'table'
}) {
  const { Icon, label, className } = presentation
  const toneClass =
    tone === 'batch'
      ? styles[`${className}Badge` as keyof typeof styles]
      : tableStyles[`${className}Cell` as keyof typeof tableStyles]
  return (
    <span className={`${tone === 'batch' ? styles.statusBadge : tableStyles.statusCell} ${toneClass ?? ''}`}>
      <Icon aria-hidden />
      {label}
    </span>
  )
}
