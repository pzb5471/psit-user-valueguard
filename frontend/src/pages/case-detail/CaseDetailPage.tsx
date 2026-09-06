import styles from '../page.module.css'

/** 案例详情页壳（规格 13.2：高价值结论、风险原因、证据、处理建议和人工确认）。由 M4-06/M4-07 实现。 */
export function CaseDetailPage() {
  return (
    <section className={styles.page} aria-labelledby="case-detail-title">
      <h1 id="case-detail-title" className={styles.pageTitle}>
        案例详情
      </h1>
      <div className={styles.card}>
        <h2 className={styles.sectionTitle}>结论与证据</h2>
        <p className={styles.body}>
          分析完成后，这里将按结论优先的顺序显示高价值结论、风险原因、介入等级、处理建议和证据。
        </p>
      </div>
    </section>
  )
}
