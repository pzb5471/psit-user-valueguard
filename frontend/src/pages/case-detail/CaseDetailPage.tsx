import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import {
  CheckCircleFilled,
  CloseCircleFilled,
  DownOutlined,
  ExclamationCircleFilled,
  FileImageOutlined,
  LockOutlined,
  MessageOutlined,
  WarningFilled,
} from '@ant-design/icons'
import { evidenceContentUrl } from '../../api/client'
import type { components } from '../../api/schema.gen'
import { useCaseDetailQuery } from '../../queries/caseQueries'
import { queryKeys } from '../../queries/queryKeys'
import { presentAction, presentCause } from './businessLabels'
import { presentCaseStatus } from '../batch/statusPresentation'
import { presentInterventionLevel } from '../batch/statusPresentation'
import { StatusBadge } from '../batch/StatusBadge'
import { ReviewPanel, RerunButton } from './ReviewPanel'
import shell from '../page.module.css'
import styles from './caseDetailPage.module.css'

type CitedEvidenceView = components['schemas']['CitedEvidenceView']
type CaseDetailView = components['schemas']['CaseDetailView']

function EvidenceImage({ src, alt }: { src: string; alt: string }) {
  const [failed, setFailed] = useState(false)
  if (failed) {
    return <p className={styles.imageFallback}>图片暂无法显示，可稍后重试或参考文字摘要。</p>
  }
  return (
    <img
      className={styles.evidenceImage}
      src={src}
      alt={alt}
      loading="lazy"
      onError={() => setFailed(true)}
    />
  )
}

function EvidenceItem({
  evidence,
  batchId,
  caseId,
}: {
  evidence: CitedEvidenceView
  batchId: string
  caseId: string
}) {
  const [expanded, setExpanded] = useState(false)
  const isImage = evidence.modality === 'IMAGE'
  const Icon = isImage ? FileImageOutlined : MessageOutlined
  return (
    <li className={styles.evidenceItem}>
      <button
        type="button"
        className={styles.evidenceToggle}
        aria-expanded={expanded}
        onClick={() => setExpanded((value) => !value)}
      >
        <Icon aria-hidden />
        <span className={styles.evidenceLabel}>{evidence.label}</span>
        <span className={styles.evidenceModality}>{isImage ? '图片' : '文本'}</span>
        <DownOutlined aria-hidden className={expanded ? styles.caretOpen : styles.caret} />
      </button>
      {expanded && (
        <div className={styles.evidenceBody}>
          {isImage ? (
            <EvidenceImage
              src={evidenceContentUrl(batchId, caseId, evidence.evidence_id)}
              alt={evidence.label}
            />
          ) : (
            <>
              {evidence.text && <p className={styles.evidenceText}>{evidence.text}</p>}
              {evidence.summary && (
                <p className={styles.evidenceSummary}>摘要：{evidence.summary}</p>
              )}
            </>
          )}
        </div>
      )}
    </li>
  )
}

/** 案例详情页（规格 12.2 / 13.2：结论优先、证据按需展开、图片受控加载）。 */
export function CaseDetailPage() {
  const { batchId = '', caseId = '' } = useParams()
  const queryClient = useQueryClient()
  const { data: result, refetch } = useCaseDetailQuery(batchId, caseId)

  if (result && !result.ok) {
    const failure = result.failure
    const detail =
      failure.kind === 'business'
        ? failure.error.message
        : failure.kind === 'network'
          ? '请确认应用已启动，然后重试。'
          : '服务返回了无法识别的响应，请重试；若持续出现请联系团队。'
    return (
      <section className={shell.page} aria-labelledby="case-detail-title">
        <h1 id="case-detail-title" className={shell.pageTitle}>
          案例详情
        </h1>
        <div className={shell.card}>
          <div role="alert" className={styles.errorPanel}>
            <p className={styles.errorHeadline}>
              <ExclamationCircleFilled aria-hidden />
              操作未能完成
            </p>
            <p className={styles.errorText}>{detail}</p>
          </div>
          <button type="button" className={styles.secondaryButton} onClick={() => void refetch()}>
            重新加载
          </button>
        </div>
      </section>
    )
  }

  if (!result?.ok || !result.data) {
    return (
      <section className={shell.page} aria-labelledby="case-detail-title" aria-busy="true">
        <h1 id="case-detail-title" className={shell.pageTitle}>
          案例详情
        </h1>
        <div className={shell.card}>
          <p className={shell.body} aria-live="polite">
            正在加载案例…
          </p>
        </div>
      </section>
    )
  }

  const detail = result.data
  const statusBadge = presentCaseStatus(detail.status)
  const analyzed = detail.primary_cause !== null || detail.intervention_level !== null

  return (
    <section className={shell.page} aria-labelledby="case-detail-title">
      <h1 id="case-detail-title" className={shell.pageTitle}>
        案例详情
      </h1>

      <div className={styles.titleRow}>
        <h2 className={styles.caseTitle}>{detail.customer_display_id}</h2>
        <StatusBadge presentation={statusBadge} />
        {detail.is_mock && <span className={styles.mockTag}>Mock 数据</span>}
      </div>

      {detail.status === 'PROCESSING_ERROR' && detail.processing_error && (
        <div className={`${shell.card} ${styles.errorCard}`}>
          <h3 className={styles.errorHeading}>
            <ExclamationCircleFilled aria-hidden />
            分析未能完成
          </h3>
          <p className={shell.body}>{detail.processing_error.message}</p>
          {detail.processing_error.next_action && (
            <p className={shell.body}>建议：{detail.processing_error.next_action}</p>
          )}
        </div>
      )}

      <div className={shell.card}>
        <h3 className={shell.sectionTitle}>高价值结论</h3>
        <p className={styles.conclusion}>{detail.is_high_value ? '高价值客户' : '非高价值客户'}</p>
        {detail.customer_value_summary && (
          <p className={shell.body}>{detail.customer_value_summary}</p>
        )}
        {detail.is_mock && (
          <p className={styles.mockNote}>
            <WarningFilled aria-hidden />
            Mock 数据金额：源数据未提供币种，请勿据此推断真实客户价值。
          </p>
        )}
      </div>

      {detail.risk_summary && (
        <div className={shell.card}>
          <h3 className={shell.sectionTitle}>风险原因</h3>
          <p className={shell.body}>{detail.risk_summary}</p>
          {detail.primary_cause && (
            <div className={styles.causeBlock}>
              <span
                className={`${styles.causeBadge} ${
                  styles[`cause${presentCause(detail.primary_cause.category).className}`]
                }`}
              >
                {presentCause(detail.primary_cause.category).label}
              </span>
              <p className={shell.body}>{detail.primary_cause.explanation}</p>
            </div>
          )}
        </div>
      )}

      {detail.intervention_level && (
        <div className={shell.card}>
          <h3 className={shell.sectionTitle}>介入等级</h3>
          <span className={styles.interventionText}>
            {presentInterventionLevel(detail.intervention_level).label}
          </span>
        </div>
      )}

      {detail.actions && detail.actions.length > 0 && (
        <div className={shell.card}>
          <h3 className={shell.sectionTitle}>处理建议</h3>
          <ul className={styles.actionList}>
            {detail.actions.map((action, index) => (
              <li key={index} className={styles.actionItem}>
                <span className={styles.actionType}>{presentAction(action.action_type).label}</span>
                <p className={styles.actionText}>{action.description}</p>
                {action.reason && <p className={styles.actionReason}>依据：{action.reason}</p>}
              </li>
            ))}
          </ul>
        </div>
      )}

      {detail.communication_points && detail.communication_points.length > 0 && (
        <div className={shell.card}>
          <h3 className={shell.sectionTitle}>沟通重点</h3>
          <ul className={styles.commList}>
            {detail.communication_points.map((point, index) => (
              <li key={index} className={styles.commItem}>
                {point}
              </li>
            ))}
          </ul>
        </div>
      )}

      {(detail.uncertainty && detail.uncertainty.length > 0) ||
      (detail.missing_evidence && detail.missing_evidence.length > 0) ? (
        <div className={shell.card}>
          <h3 className={shell.sectionTitle}>不确定性与证据缺口</h3>
          {detail.uncertainty && detail.uncertainty.length > 0 && (
            <ul className={styles.commList}>
              {detail.uncertainty.map((item, index) => (
                <li key={index} className={styles.commItem}>
                  <WarningFilled aria-hidden className={styles.warningIcon} />
                  {item}
                </li>
              ))}
            </ul>
          )}
          {detail.missing_evidence && detail.missing_evidence.length > 0 && (
            <ul className={styles.commList}>
              {detail.missing_evidence.map((item, index) => (
                <li key={index} className={styles.commItem}>
                  <CloseCircleFilled aria-hidden className={styles.missingIcon} />
                  缺少：{item}
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : null}

      {detail.cited_evidence && detail.cited_evidence.length > 0 && (
        <div className={shell.card}>
          <h3 className={shell.sectionTitle}>证据</h3>
          <p className={styles.evidenceHint}>点击证据可展开查看内容；图片加载失败不阻断其余证据。</p>
          <ul className={styles.evidenceList}>
            {detail.cited_evidence.map((evidence, index) => (
              <EvidenceItem key={index} evidence={evidence} batchId={batchId} caseId={caseId} />
            ))}
          </ul>
        </div>
      )}

      {analyzed && (
        <p className={styles.mockNote}>
          <CheckCircleFilled aria-hidden />
          以上为程序对当前证据的分析结论，供运营人员作人工决策初稿。
        </p>
      )}

      {detail.review_result && (
        <div className={shell.card}>
          <h3 className={shell.sectionTitle}>人工确认结果</h3>
          <p className={styles.reviewOutcome}>{reviewOutcomeLabel(detail.review_result.outcome)}</p>
          {detail.review_result.review_reason && (
            <p className={shell.body}>说明：{detail.review_result.review_reason}</p>
          )}
          {detail.review_result.execution_note && (
            <p className={shell.body}>执行说明：{detail.review_result.execution_note}</p>
          )}
        </div>
      )}

      <ActionSection
        detail={detail}
        onDataChange={() => void queryClient.invalidateQueries({ queryKey: queryKeys.caseDetail(batchId, caseId) })}
      />
    </section>
  )
}

function reviewOutcomeLabel(outcome: string): string {
  switch (outcome) {
    case 'APPROVED':
      return '直接通过'
    case 'MODIFIED_AND_APPROVED':
      return '修改后确认'
    case 'REJECTED_WITH_JUDGMENT':
      return '驳回并给出判断'
    case 'INSUFFICIENT_EVIDENCE':
      return '标记证据不足'
    default:
      return outcome
  }
}

/** 案例操作区：可确认则显示表单，可重跑则显示重跑，已完成只读（规格 13.3）。 */
function ActionSection({ detail, onDataChange }: { detail: CaseDetailView; onDataChange: () => void }) {
  const readonly = detail.status === 'COMPLETED'
  const canReview = detail.can_review && !!detail.review_token && !!detail.review_options
  const canRerun = detail.can_rerun
  if (readonly) {
    return (
      <p className={styles.readonlyNote}>
        <LockOutlined aria-hidden />
        该案例已完成人工确认，结果已锁定为只读。
      </p>
    )
  }
  return (
    <div className={styles.actionArea}>
      {canReview && <ReviewPanel detail={detail} onCompleted={() => void onDataChange()} />}
      {canRerun && <RerunButton detail={detail} onStarted={() => void onDataChange()} />}
    </div>
  )
}