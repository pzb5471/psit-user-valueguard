import { useId, useState } from 'react'
import type { components } from '../../api/schema.gen'
import { api } from '../../api/client'
import { toResult } from '../../api/errors'
import type { RequestFailure } from '../../api/errors'
import styles from './reviewPanel.module.css'

type CaseDetailView = components['schemas']['CaseDetailView']
type ActionType = components['schemas']['ActionType']
type BusinessCause = components['schemas']['BusinessCause']
type InterventionLevel = components['schemas']['InterventionLevel']
type ReviewResultView = components['schemas']['ReviewResultView']

type ReviewOutcome = 'APPROVED' | 'MODIFIED_AND_APPROVED' | 'REJECTED_WITH_JUDGMENT' | 'INSUFFICIENT_EVIDENCE'

/** 四种人工确认操作面板（规格 12.3）：字段随 outcome 严格切换，review_token 永不渲染。 */
export function ReviewPanel({
  detail,
  onCompleted,
}: {
  detail: CaseDetailView
  onCompleted: (result: ReviewResultView) => void
}) {
  const formId = useId()
  const [outcome, setOutcome] = useState<ReviewOutcome>('APPROVED')
  const [level, setLevel] = useState<InterventionLevel>('SHOULD_INTERVENE')
  const [cause, setCause] = useState<BusinessCause>('OTHER')
  const [actions, setActions] = useState<ActionType[]>([])
  const [reason, setReason] = useState('')
  const [executionNote, setExecutionNote] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [failure, setFailure] = useState<RequestFailure | null>(null)

  const options = detail.review_options
  if (!detail.can_review || !detail.review_token || !options) return null

  const toggleAction = (action: ActionType) => {
    setActions((current) =>
      current.includes(action) ? current.filter((item) => item !== action) : [...current, action],
    )
  }

  const submit = async () => {
    setSubmitting(true)
    setFailure(null)
    const common = {
      // 一次业务提交的幂等键；网络重试必须复用（规格 12.3）。
      submission_id: crypto.randomUUID(),
      review_token: detail.review_token,
      outcome,
    }
    const body =
      outcome === 'APPROVED'
        ? common
        : outcome === 'INSUFFICIENT_EVIDENCE'
          ? { ...common, review_reason: reason }
          : {
              ...common,
              final_intervention_level: level,
              final_cause: cause,
              final_actions: actions,
              review_reason: reason,
              execution_note: executionNote || null,
            }
    const result = await toResult(
      api.POST('/api/v1/batches/{batch_id}/cases/{case_id}/reviews', {
        params: { path: { batch_id: detail.batch_id, case_id: detail.case_id } },
        body: body as never,
      }),
    )
    setSubmitting(false)
    if (result.ok) onCompleted(result.data)
    else setFailure(result.failure)
  }

  const needsJudgment = outcome === 'MODIFIED_AND_APPROVED' || outcome === 'REJECTED_WITH_JUDGMENT'
  const needsReason = outcome !== 'APPROVED'

  return (
    <section className={styles.panel} aria-labelledby={`${formId}-title`}>
      <h3 id={`${formId}-title`} className={styles.title}>人工确认</h3>
      <fieldset className={styles.fieldset}>
        <legend className={styles.legend}>确认结果</legend>
        {(
          [
            ['APPROVED', '直接通过'],
            ['MODIFIED_AND_APPROVED', '修改后确认'],
            ['REJECTED_WITH_JUDGMENT', '驳回并给出判断'],
            ['INSUFFICIENT_EVIDENCE', '证据不足'],
          ] as const
        ).map(([value, label]) => (
          <label key={value} className={styles.radioLabel}>
            <input
              type="radio"
              name={`${formId}-outcome`}
              value={value}
              checked={outcome === value}
              onChange={() => setOutcome(value)}
            />
            {label}
          </label>
        ))}
      </fieldset>

      {needsJudgment && (
        <div className={styles.judgmentFields}>
          <label className={styles.fieldLabel}>
            最终介入等级
            <select value={level} onChange={(event) => setLevel(event.target.value as InterventionLevel)}>
              {options.intervention_levels.map((item) => (
                <option key={item.value} value={item.value}>{item.label}</option>
              ))}
            </select>
          </label>
          <label className={styles.fieldLabel}>
            最终原因
            <select value={cause} onChange={(event) => setCause(event.target.value as BusinessCause)}>
              {options.cause_categories.map((item) => (
                <option key={item.value} value={item.value}>{item.label}</option>
              ))}
            </select>
          </label>
          <fieldset className={styles.actionFieldset}>
            <legend className={styles.legend}>最终动作（至少一项）</legend>
            {options.action_types.map((item) => (
              <label key={item.value} className={styles.checkboxLabel}>
                <input
                  type="checkbox"
                  checked={actions.includes(item.value as ActionType)}
                  onChange={() => toggleAction(item.value as ActionType)}
                />
                {item.label}
              </label>
            ))}
          </fieldset>
          <label className={styles.fieldLabel}>
            执行说明（可选）
            <textarea value={executionNote} onChange={(event) => setExecutionNote(event.target.value)} rows={2} />
          </label>
        </div>
      )}

      {needsReason && (
        <label className={styles.fieldLabel}>
          {outcome === 'INSUFFICIENT_EVIDENCE' ? '证据缺口说明' : '审核原因'}
          <textarea value={reason} onChange={(event) => setReason(event.target.value)} rows={3} required />
        </label>
      )}

      {failure && (
        <div role="alert" className={styles.error}>
          {failure.kind === 'business' ? failure.error.message : '提交失败，请重试。'}
        </div>
      )}
      <button
        type="button"
        className={styles.submitButton}
        disabled={submitting || (needsJudgment && actions.length === 0) || (needsReason && !reason.trim())}
        onClick={() => void submit()}
      >
        {submitting ? '正在提交…' : '提交确认'}
      </button>
    </section>
  )
}

/** 重跑按钮（待确认或处理异常可用；已完成不可用）。 */
export function RerunButton({ detail, onStarted }: { detail: CaseDetailView; onStarted: () => void }) {
  const [submitting, setSubmitting] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  if (!detail.can_rerun) return null
  const rerun = async () => {
    setSubmitting(true)
    setMessage(null)
    const result = await toResult(
      api.POST('/api/v1/batches/{batch_id}/cases/{case_id}/reruns', {
        params: { path: { batch_id: detail.batch_id, case_id: detail.case_id } },
      }),
    )
    setSubmitting(false)
    if (result.ok) onStarted()
    else setMessage(result.failure.kind === 'business' ? result.failure.error.message : '重跑失败，请重试。')
  }
  return (
    <div className={styles.rerunArea}>
      <button type="button" className={styles.secondaryButton} disabled={submitting} onClick={() => void rerun()}>
        {submitting ? '正在重跑…' : '重新分析'}
      </button>
      {message && <p role="alert" className={styles.error}>{message}</p>}
    </div>
  )
}
