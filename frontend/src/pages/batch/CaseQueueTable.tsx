import { Link } from 'react-router-dom'
import { CheckCircleFilled } from '@ant-design/icons'
import type { components } from '../../api/schema.gen'
import { StatusBadge, presentCaseStatus, presentInterventionLevel } from './statusPresentation'
import styles from './caseQueueTable.module.css'

type CaseQueueItemView = components['schemas']['CaseQueueItemView']

/** 队列行的异常标记（规格 12.2：三个标记由当前有效结果或当前运行错误确定）。 */
const MARKERS = [
  { key: 'has_evidence_conflict', label: '证据冲突' },
  { key: 'has_insufficient_evidence', label: '证据不足' },
  { key: 'has_modality_failure', label: '处理异常' },
] as const

/**
 * 案例队列表格（规格 13.6）：白色表面、分隔线与行距形成层级；
 * 顺序为服务端固定排序，前端不重排、不提供排序控件（规格 12.1）。
 */
export function CaseQueueTable({ batchId, items }: { batchId: string; items: CaseQueueItemView[] }) {
  return (
    <div className={styles.tableWrap}>
      <table className={styles.table}>
        <thead>
          <tr>
            <th scope="col">客户</th>
            <th scope="col">案例状态</th>
            <th scope="col">介入等级</th>
            <th scope="col">说明</th>
            <th scope="col">标记</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => {
            const note = item.priority_reason ?? item.risk_summary
            const markers = MARKERS.filter((marker) => item[marker.key])
            return (
              <tr key={item.case_id}>
                <td className={styles.customerCell}>
                  <Link className={styles.caseLink} to={`/batches/${batchId}/cases/${item.case_id}`}>
                    {item.customer_display_id}
                  </Link>
                  {item.is_high_value && (
                    <span className={styles.highValueTag}>
                      <CheckCircleFilled aria-hidden />
                      高价值
                    </span>
                  )}
                </td>
                <td>
                  <StatusBadge presentation={presentCaseStatus(item.status)} tone="table" />
                </td>
                <td>
                  {item.intervention_level ? (
                    <StatusBadge
                      presentation={presentInterventionLevel(item.intervention_level)}
                      tone="table"
                    />
                  ) : (
                    <span className={styles.emptyCell}>—</span>
                  )}
                </td>
                <td className={styles.noteCell}>{note ?? '—'}</td>
                <td>
                  {markers.length > 0 ? (
                    <span className={styles.markerList}>
                      {markers.map((marker) => (
                        <span key={marker.key} className={styles.markerTag}>
                          {marker.label}
                        </span>
                      ))}
                    </span>
                  ) : (
                    <span className={styles.emptyCell}>—</span>
                  )}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
