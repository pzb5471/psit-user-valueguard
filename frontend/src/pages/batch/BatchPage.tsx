import styles from '../page.module.css'

/** 批次页壳（规格 13.2：批次摘要、分析进度、案例队列、筛选和开始分析）。由 M4-04/M4-05 实现。 */
export function BatchPage() {
  return (
    <section className={styles.page} aria-labelledby="batch-title">
      <h1 id="batch-title" className={styles.pageTitle}>
        批次
      </h1>
      <div className={styles.card}>
        <h2 className={styles.sectionTitle}>批次摘要与案例队列</h2>
        <p className={styles.body}>
          批次创建后，这里将显示当前状态、分析进度、错误数量和按业务优先级排列的案例队列。
        </p>
      </div>
    </section>
  )
}
