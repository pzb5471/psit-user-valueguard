import { useCallback, useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { useParams } from 'react-router-dom'
import { ExclamationCircleFilled } from '@ant-design/icons'
import { api } from '../../api/client'
import { toResult } from '../../api/errors'
import type { RequestFailure, RequestResult } from '../../api/errors'
import type { components } from '../../api/schema.gen'
import { StatusBadge, presentBatchStatus } from './statusPresentation'
import styles from './batchPage.module.css'
import { CaseQueueTable } from './CaseQueueTable'

type BatchWorkspaceView = components['schemas']['BatchWorkspaceView']
type CaseQueueView = components['schemas']['CaseQueueView']

function ErrorPanel({ failure }: { failure: RequestFailure }) {
  const suggestion =
    failure.kind === 'business' && failure.error.next_action
      ? `建议：${failure.error.next_action}`
      : null
  const detail =
    failure.kind === 'business'
      ? failure.error.message
      : failure.kind === 'network'
        ? '请确认应用已启动，然后重试。'
        : '服务返回了无法识别的响应，请重试；若持续出现请联系团队。'
  return (
    <div role="alert" className={styles.errorPanel}>
      <p className={styles.errorHeadline}>
        <ExclamationCircleFilled aria-hidden />
        {failure.kind === 'business'
          ? '操作未能完成'
          : failure.kind === 'network'
            ? '无法连接服务'
            : '服务响应无法识别'}
      </p>
      <p className={styles.errorText}>{detail}</p>
      {suggestion && <p className={styles.errorText}>{suggestion}</p>}
    </div>
  )
}

function StatItem({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className={styles.statItem}>
      <span className={styles.statValue}>{value}</span>
      <span className={styles.statLabel}>{label}</span>
    </div>
  )
}

/** 批次页（规格 13.2：批次摘要、分析进度、案例队列、筛选和开始分析）。 */
export function BatchPage() {
  const { batchId = '' } = useParams()
  const [batch, setBatch] = useState<BatchWorkspaceView | null>(null)
  const [batchFailure, setBatchFailure] = useState<RequestFailure | null>(null)
  const [queue, setQueue] = useState<CaseQueueView | null>(null)
  const [queueFailure, setQueueFailure] = useState<RequestFailure | null>(null)
  const [starting, setStarting] = useState(false)
  const [startFailure, setStartFailure] = useState<RequestFailure | null>(null)

  const applyBatchResult = useCallback(
    (result: RequestResult<BatchWorkspaceView>) => {
      if (result.ok) {
        setBatch(result.data)
        setBatchFailure(null)
      } else {
        setBatchFailure(result.failure)
      }
    },
    [],
  )

  const applyQueueResult = useCallback((result: RequestResult<CaseQueueView>) => {
    if (result.ok) {
      setQueue(result.data)
      setQueueFailure(null)
    } else {
      setQueueFailure(result.failure)
    }
  }, [])

  const fetchBatch = useCallback(async () => {
    return toResult(api.GET('/api/v1/batches/{batch_id}', { params: { path: { batch_id: batchId } } }))
  }, [batchId])

  const fetchQueue = useCallback(async () => {
    return toResult(
      api.GET('/api/v1/batches/{batch_id}/cases', {
        params: { path: { batch_id: batchId }, query: { limit: 50, offset: 0 } },
      }),
    )
  }, [batchId])

  useEffect(() => {
    let active = true
    void fetchBatch().then((result) => {
      if (active) applyBatchResult(result)
    })
    void fetchQueue().then((result) => {
      if (active) applyQueueResult(result)
    })
    return () => {
      active = false
    }
  }, [fetchBatch, fetchQueue, applyBatchResult, applyQueueResult])

  const onStartAnalysis = () => {
    if (starting || !batch?.can_start_analysis) return
    setStarting(true)
    setStartFailure(null)
    void toResult(
      api.POST('/api/v1/batches/{batch_id}/runs', { params: { path: { batch_id: batchId } } }),
    ).then((result) => {
      setStarting(false)
      if (result.ok) {
        // 202 返回开始后的批次视图（ANALYZING），以服务端结果为准更新。
        setBatch(result.data)
      } else {
        setStartFailure(result.failure)
      }
    })
  }

  const retryQueue = () => {
    setQueueFailure(null)
    void fetchQueue().then(applyQueueResult)
  }

  if (batchFailure) {
    return (
      <section className={styles.page} aria-labelledby="batch-title">
        <h1 id="batch-title" className={styles.pageTitle}>
          批次
        </h1>
        <div className={styles.card}>
          <ErrorPanel failure={batchFailure} />
          <button type="button" className={styles.secondaryButton} onClick={() => {
            setBatchFailure(null)
            void fetchBatch().then(applyBatchResult)
          }}>
            重新加载
          </button>
        </div>
      </section>
    )
  }

  if (!batch) {
    return (
      <section className={styles.page} aria-labelledby="batch-title" aria-busy="true">
        <h1 id="batch-title" className={styles.pageTitle}>
          批次
        </h1>
        <div className={styles.card}>
          <p className={styles.body} aria-live="polite">
            正在加载批次信息…
          </p>
        </div>
      </section>
    )
  }

  const status = presentBatchStatus(batch.status)
  const analyzing = batch.status === 'ANALYZING'
  const canStart = batch.can_start_analysis && !starting

  return (
    <section className={styles.page} aria-labelledby="batch-title">
      <h1 id="batch-title" className={styles.pageTitle}>
        批次
      </h1>

      <div className={styles.card}>
        <div className={styles.summaryBand}>
          <div className={styles.summaryMain}>
            <div className={styles.titleRow}>
              <h2 className={styles.sectionTitle}>{batch.source_filename}</h2>
              <StatusBadge presentation={status} />
              {batch.is_mock && <span className={styles.mockTag}>Mock 数据</span>}
            </div>
            <div className={styles.statBand}>
              <StatItem label="案例数" value={batch.case_count} />
              <StatItem label="已出结果" value={batch.analysis_succeeded_count} />
              <StatItem label="处理异常" value={batch.error_count} />
              <StatItem label="证据数" value={batch.evidence_count} />
            </div>
            {analyzing && (
              <p className={styles.body}>分析进行中；每个案例完成后将进入待确认。</p>
            )}
            {!analyzing && !batch.can_start_analysis && batch.analysis_unavailable_message && (
              <p className={styles.unavailableText}>{batch.analysis_unavailable_message}</p>
            )}
          </div>
          {batch.can_start_analysis && (
            <button
              type="button"
              className={styles.primaryButton}
              disabled={!canStart}
              onClick={onStartAnalysis}
            >
              {starting ? '正在开始…' : '开始分析'}
            </button>
          )}
        </div>
        {startFailure && <ErrorPanel failure={startFailure} />}
      </div>

      <div className={styles.card}>
        <h2 className={styles.sectionTitle}>案例队列</h2>
        {queueFailure && (
          <div>
            <ErrorPanel failure={queueFailure} />
            <button type="button" className={styles.secondaryButton} onClick={retryQueue}>
              重新加载
            </button>
          </div>
        )}
        {!queueFailure && !queue && (
          <p className={styles.body} aria-live="polite" aria-busy="true">
            正在加载案例队列…
          </p>
        )}
        {!queueFailure && queue && queue.items.length === 0 && (
          <p className={styles.body}>暂无案例。</p>
        )}
        {!queueFailure && queue && queue.items.length > 0 && (
          <CaseQueueTable batchId={batchId} items={queue.items} />
        )}
      </div>
    </section>
  )
}
