import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useSearchParams, useParams } from 'react-router-dom'
import { ExclamationCircleFilled, LeftOutlined, RightOutlined } from '@ant-design/icons'
import { api } from '../../api/client'
import { toResult } from '../../api/errors'
import type { RequestFailure } from '../../api/errors'
import {
  INTERVENTION_LEVEL_VALUES,
  CASE_STATUS_VALUES,
  parseCaseQueueParams,
  writeCaseQueueParams,
} from '../../routing/caseQueueParams'
import { ACTIVE_POLL_MS, useBatchDetailQuery, useCaseQueueQuery } from '../../queries/batchQueries'
import { queryKeys } from '../../queries/queryKeys'
import {
  presentCaseStatus,
  presentInterventionLevel,
  presentBatchStatus,
} from './statusPresentation'
import { StatusBadge } from './StatusBadge'
import { CaseQueueTable } from './CaseQueueTable'
import styles from './batchPage.module.css'

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

/** 批次页（规格 13.2）：批次摘要、案例队列、筛选与分页写入 URL，活动批次按唯一节奏轮询。 */
export function BatchPage() {
  const { batchId = '' } = useParams()
  const queryClient = useQueryClient()
  const [searchParams, setSearchParams] = useSearchParams()
  const [startFailure, setStartFailure] = useState<RequestFailure | null>(null)

  const queueParams = parseCaseQueueParams(searchParams)
  const batchQuery = useBatchDetailQuery(batchId)
  // 分析中按唯一节奏轮询；终态与待分析不轮询（后台暂停由 TanStack 默认行为保证）。
  const pollMs = batchQuery.data?.ok && batchQuery.data.data.status === 'ANALYZING' ? ACTIVE_POLL_MS : false
  const queueQuery = useCaseQueueQuery(batchId, queueParams, pollMs)

  const batchResult = batchQuery.data
  const queueResult = queueQuery.data
  const batch = batchResult?.ok ? batchResult.data : null
  const batchFailure = batchResult && !batchResult.ok ? batchResult.failure : null
  const queue = queueResult?.ok ? queueResult.data : null
  const queueFailure = queueResult && !queueResult.ok ? queueResult.failure : null

  const updateParams = (patch: Parameters<typeof writeCaseQueueParams>[1]) => {
    setSearchParams(writeCaseQueueParams(searchParams, patch), { preventScrollReset: true })
  }

  const startMutation = useMutation({
    mutationFn: () =>
      toResult(api.POST('/api/v1/batches/{batch_id}/runs', { params: { path: { batch_id: batchId } } })),
    onSuccess: async (result) => {
      if (result.ok) {
        // 精确失效：只失效该批次的详情与队列（全部筛选变体）。
        await queryClient.invalidateQueries({ queryKey: queryKeys.batchDetail(batchId) })
        await queryClient.invalidateQueries({ queryKey: queryKeys.caseQueueRoot(batchId) })
      } else {
        setStartFailure(result.failure)
      }
    },
  })

  const starting = startMutation.isPending
  const retryBatch = () => {
    void batchQuery.refetch()
  }
  const retryQueue = () => {
    void queueQuery.refetch()
  }

  if (batchFailure) {
    return (
      <section className={styles.page} aria-labelledby="batch-title">
        <h1 id="batch-title" className={styles.pageTitle}>
          批次
        </h1>
        <div className={styles.card}>
          <ErrorPanel failure={batchFailure} />
          <button type="button" className={styles.secondaryButton} onClick={retryBatch}>
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

  const total = queue?.total ?? 0
  const rangeEnd = Math.min(queueParams.offset + queueParams.limit, total)
  const prevDisabled = queueParams.offset === 0
  const nextDisabled = queueParams.offset + queueParams.limit >= total

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
              {[
                { label: '案例数', value: batch.case_count },
                { label: '已出结果', value: batch.analysis_succeeded_count },
                { label: '处理异常', value: batch.error_count },
                { label: '证据数', value: batch.evidence_count },
              ].map((stat) => (
                <div key={stat.label} className={styles.statItem}>
                  <span className={styles.statValue}>{stat.value}</span>
                  <span className={styles.statLabel}>{stat.label}</span>
                </div>
              ))}
            </div>
            {analyzing && <p className={styles.body}>分析进行中；每个案例完成后将进入待确认。</p>}
            {!analyzing && !batch.can_start_analysis && batch.analysis_unavailable_message && (
              <p className={styles.unavailableText}>{batch.analysis_unavailable_message}</p>
            )}
          </div>
          {batch.can_start_analysis && (
            <button
              type="button"
              className={styles.primaryButton}
              disabled={starting}
              onClick={() => startMutation.mutate()}
            >
              {starting ? '正在开始…' : '开始分析'}
            </button>
          )}
        </div>
        {startFailure && <ErrorPanel failure={startFailure} />}
      </div>

      <div className={styles.card}>
        <h2 className={styles.sectionTitle}>案例队列</h2>

        <div className={styles.filterRow}>
          <label className={styles.filterField}>
            <span className={styles.filterLabel}>案例状态</span>
            <select
              className={styles.filterSelect}
              value={queueParams.status ?? ''}
              onChange={(event) => updateParams({ status: event.target.value || null, offset: 0 })}
            >
              <option value="">全部</option>
              {CASE_STATUS_VALUES.map((value) => (
                <option key={value} value={value}>
                  {presentCaseStatus(value).label}
                </option>
              ))}
            </select>
          </label>
          <label className={styles.filterField}>
            <span className={styles.filterLabel}>介入等级</span>
            <select
              className={styles.filterSelect}
              value={queueParams.interventionLevel ?? ''}
              onChange={(event) =>
                updateParams({ intervention_level: event.target.value || null, offset: 0 })
              }
            >
              <option value="">全部</option>
              {INTERVENTION_LEVEL_VALUES.map((value) => (
                <option key={value} value={value}>
                  {presentInterventionLevel(value).label}
                </option>
              ))}
            </select>
          </label>
          {total > 0 && (
            <div className={styles.paginationRow}>
              <button
                type="button"
                className={styles.pageButton}
                disabled={prevDisabled}
                aria-label="上一页"
                onClick={() => updateParams({ offset: Math.max(0, queueParams.offset - queueParams.limit) })}
              >
                <LeftOutlined aria-hidden />
              </button>
              <span className={styles.pageText}>
                第 {queueParams.offset + 1}–{rangeEnd} 个，共 {total} 个
              </span>
              <button
                type="button"
                className={styles.pageButton}
                disabled={nextDisabled}
                aria-label="下一页"
                onClick={() => updateParams({ offset: queueParams.offset + queueParams.limit })}
              >
                <RightOutlined aria-hidden />
              </button>
            </div>
          )}
        </div>

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
          <p className={styles.body}>暂无符合条件的案例。</p>
        )}
        {!queueFailure && queue && queue.items.length > 0 && (
          <CaseQueueTable batchId={batchId} items={queue.items} />
        )}
      </div>
    </section>
  )
}
