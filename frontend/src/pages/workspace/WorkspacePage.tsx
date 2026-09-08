import { useCallback, useEffect, useState } from 'react'
import type { ChangeEvent, FormEvent } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { CheckCircleFilled, ExclamationCircleFilled, WarningFilled } from '@ant-design/icons'
import { api } from '../../api/client'
import { toResult } from '../../api/errors'
import type { RequestFailure, RequestResult } from '../../api/errors'
import type { components } from '../../api/schema.gen'
import shell from '../page.module.css'
import styles from './workspacePage.module.css'

type BatchWorkspaceView = components['schemas']['BatchWorkspaceView']
type BatchListView = components['schemas']['BatchListView']

/** 批次列表读取阶段：决定根页面进入导入区还是最近批次。 */
type ListPhase = { kind: 'loading' } | { kind: 'error'; failure: RequestFailure } | { kind: 'ready' }

/** 导入动作阶段：两步导入（选择 → 确认）与导入后的静止摘要。 */
type UploadPhase =
  | { kind: 'idle' }
  | { kind: 'selected'; file: File }
  | { kind: 'uploading'; file: File }
  | { kind: 'imported'; batch: BatchWorkspaceView; duplicate: boolean }
  | { kind: 'failed'; file: File; failure: RequestFailure }

/** 错误面板的三种文案来源与集中错误层一一对应。 */
function failureHeadline(failure: RequestFailure): string {
  if (failure.kind === 'business') return '操作未能完成'
  if (failure.kind === 'network') return '无法连接服务'
  return '服务响应无法识别'
}

function failureDetail(failure: RequestFailure): string | null {
  if (failure.kind === 'business') return failure.error.message
  if (failure.kind === 'network') return '请确认应用已启动，然后重试。'
  return '服务返回了无法识别的响应，请重试；若持续出现请联系团队。'
}

function ErrorPanel({ failure }: { failure: RequestFailure }) {
  const suggestion =
    failure.kind === 'business' && failure.error.next_action
      ? `建议：${failure.error.next_action}`
      : null
  return (
    <div role="alert" className={styles.errorPanel}>
      <p className={styles.errorHeadline}>
        <ExclamationCircleFilled aria-hidden />
        {failureHeadline(failure)}
      </p>
      <p className={styles.errorText}>{failureDetail(failure)}</p>
      {suggestion && <p className={styles.errorText}>{suggestion}</p>}
    </div>
  )
}

/** 根页面（规格 13.2）：没有批次时导入 ZIP；有批次时进入最近批次。 */
export function WorkspacePage() {
  const navigate = useNavigate()
  const [listPhase, setListPhase] = useState<ListPhase>({ kind: 'loading' })
  const [redirectBatchId, setRedirectBatchId] = useState<string | null>(null)
  const [upload, setUpload] = useState<UploadPhase>({ kind: 'idle' })
  const [localRejection, setLocalRejection] = useState<string | null>(null)
  const [history, setHistory] = useState<BatchWorkspaceView[]>([])

  /** 按列表结果更新去向；只在请求回调中调用（规格 13.2：有批次进入最近批次）。 */
  const applyListResult = useCallback((result: RequestResult<BatchListView>) => {
    if (!result.ok) {
      setListPhase({ kind: 'error', failure: result.failure })
      return
    }
    // 服务端按 imported_at 倒序排列，首项即最近批次（规格 12.1）。
    const mostRecent = result.data.items[0]
    if (mostRecent) {
      setRedirectBatchId(mostRecent.batch_id)
    } else {
      setListPhase({ kind: 'ready' })
    }
  }, [])

  const fetchBatches = useCallback(async () => {
    return toResult(api.GET('/api/v1/batches', { params: { query: { limit: 20, offset: 0 } } }))
  }, [])

  useEffect(() => {
    let active = true
    void fetchBatches().then((result) => {
      if (active) applyListResult(result)
    })
    return () => {
      active = false
    }
  }, [fetchBatches, applyListResult])

  const onFileChosen = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return
    // 本地只做"明显不合格"预检（扩展名、空文件）；校验结论以服务端为准，不靠浏览器判定合格。
    if (!file.name.toLowerCase().endsWith('.zip')) {
      setLocalRejection('请选择 .zip 格式的运行包。')
      setUpload({ kind: 'idle' })
      return
    }
    if (file.size === 0) {
      setLocalRejection('文件内容为空，请重新选择有效的运行包。')
      setUpload({ kind: 'idle' })
      return
    }
    setLocalRejection(null)
    setUpload({ kind: 'selected', file })
  }

  const onImportSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (upload.kind !== 'selected') return
    const { file } = upload
    setUpload({ kind: 'uploading', file })
    const form = new FormData()
    form.append('file', file, file.name)
    const result = await toResult(api.POST('/api/v1/batches', { body: form as never }))
    if (result.ok) {
      setUpload({ kind: 'imported', batch: result.data, duplicate: result.status === 200 })
      void refreshHistory(result.data.batch_id)
    } else {
      setUpload({ kind: 'failed', file, failure: result.failure })
    }
  }

  /** 导入成功后刷新历史批次入口；这是辅助信息，失败不阻塞摘要展示。 */
  const refreshHistory = useCallback(async (currentBatchId: string) => {
    const result = await toResult(
      api.GET('/api/v1/batches', { params: { query: { limit: 20, offset: 0 } } }),
    )
    if (result.ok) {
      setHistory(result.data.items.filter((batch) => batch.batch_id !== currentBatchId))
    }
  }, [])

  if (redirectBatchId) {
    return <Navigate to={`/batches/${redirectBatchId}`} replace />
  }

  const selectedFile =
    upload.kind === 'selected' || upload.kind === 'uploading' || upload.kind === 'failed'
      ? upload.file
      : null
  const importing = upload.kind === 'uploading'

  return (
    <section className={shell.page} aria-labelledby="workspace-title">
      <h1 id="workspace-title" className={shell.pageTitle}>
        工作台
      </h1>

      {listPhase.kind === 'loading' && (
        <div className={shell.card} aria-busy="true">
          <p className={shell.body} aria-live="polite">
            正在加载批次信息…
          </p>
        </div>
      )}

      {listPhase.kind === 'error' && (
        <div className={shell.card}>
          <ErrorPanel failure={listPhase.failure} />
          <button
            type="button"
            className={styles.secondaryButton}
            onClick={() => {
              setListPhase({ kind: 'loading' })
              void fetchBatches().then(applyListResult)
            }}
          >
            重新加载
          </button>
        </div>
      )}

      {listPhase.kind === 'ready' && (
        <div className={shell.card}>
          <h2 className={shell.sectionTitle}>批次导入</h2>
          <p className={shell.body}>
            选择一个标准案例 ZIP 运行包导入；导入后先核对摘要，再进入批次明确开始分析。
          </p>

          {upload.kind === 'imported' ? (
            <div className={styles.summary}>
              {upload.duplicate && (
                <p className={styles.staticNote}>该运行包此前已导入，已返回原有批次。</p>
              )}
              <dl className={styles.summaryList}>
                <div className={styles.summaryRow}>
                  <dt>文件名</dt>
                  <dd>{upload.batch.source_filename}</dd>
                </div>
                <div className={styles.summaryRow}>
                  <dt>案例数</dt>
                  <dd>{upload.batch.case_count}</dd>
                </div>
                <div className={styles.summaryRow}>
                  <dt>证据数</dt>
                  <dd>{upload.batch.evidence_count}</dd>
                </div>
                <div className={styles.summaryRow}>
                  <dt>校验结论</dt>
                  <dd className={styles.passText}>
                    <CheckCircleFilled aria-hidden />
                    {upload.duplicate ? '通过（幂等命中）' : '通过，已导入'}
                  </dd>
                </div>
              </dl>
              {upload.batch.is_mock && (
                <p className={styles.mockNote}>
                  <WarningFilled aria-hidden />
                  Mock 数据：当前案例包为演示数据，不代表真实客户关系。
                </p>
              )}
              {upload.batch.can_start_analysis ? (
                <button
                  type="button"
                  className={styles.primaryButton}
                  onClick={() => navigate(`/batches/${upload.batch.batch_id}`)}
                >
                  开始分析
                </button>
              ) : (
                <p className={styles.errorText}>{upload.batch.analysis_unavailable_message}</p>
              )}
              <p className={styles.staticNote}>导入不会自动开始分析；开始分析需要在批次页明确点击。</p>
              {history.length > 0 && (
                <div className={styles.history}>
                  <h3 className={styles.historyTitle}>历史批次</h3>
                  <ul className={styles.historyList}>
                    {history.map((batch) => (
                      <li key={batch.batch_id}>
                        <Link className={styles.historyLink} to={`/batches/${batch.batch_id}`}>
                          {batch.source_filename}
                        </Link>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          ) : (
            <form onSubmit={(event) => void onImportSubmit(event)}>
              <label className={styles.fileButton}>
                选择 ZIP 文件
                <input
                  type="file"
                  accept=".zip"
                  className={styles.fileInput}
                  onChange={onFileChosen}
                  disabled={importing}
                />
              </label>
              {selectedFile && <p className={styles.selectedFile}>已选择：{selectedFile.name}</p>}
              {localRejection && (
                <p role="alert" className={styles.errorText}>
                  {localRejection}
                </p>
              )}
              {upload.kind === 'failed' && <ErrorPanel failure={upload.failure} />}
              <button
                type="submit"
                className={styles.primaryButton}
                disabled={!selectedFile || importing}
              >
                {importing ? '正在导入…' : '导入批次'}
              </button>
            </form>
          )}
        </div>
      )}
    </section>
  )
}
