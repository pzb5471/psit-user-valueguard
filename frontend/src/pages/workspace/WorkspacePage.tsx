import styles from '../page.module.css'

/** 工作台入口页壳（规格 13.2：无批次时导入 ZIP，有批次时进入最近批次）。导入区由 M4-03 实现。 */
export function WorkspacePage() {
  return (
    <section className={styles.page} aria-labelledby="workspace-title">
      <h1 id="workspace-title" className={styles.pageTitle}>
        工作台
      </h1>
      <div className={styles.card}>
        <h2 className={styles.sectionTitle}>批次导入</h2>
        <p className={styles.body}>
          尚未导入任何批次。导入标准案例 ZIP 后，这里将显示导入摘要和最近批次入口，分析只在明确点击开始后进行。
        </p>
      </div>
    </section>
  )
}
