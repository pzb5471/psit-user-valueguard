// @vitest-environment node
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { expect, test } from 'vitest'
import { checkCommittedTypes, compareSources } from '../../scripts/checkApiTypes.mjs'
import { generateTypes, GENERATED_URL } from '../../scripts/generateApiTypes.mjs'

const generatedPath = fileURLToPath(GENERATED_URL)

/** 规格第 12.1 冻结的九条路径。 */
const frozenPaths = [
  '/api/v1/batches',
  '/api/v1/batches/{batch_id}',
  '/api/v1/batches/{batch_id}/runs',
  '/api/v1/batches/{batch_id}/cases',
  '/api/v1/batches/{batch_id}/cases/{case_id}',
  '/api/v1/batches/{batch_id}/cases/{case_id}/reruns',
  '/api/v1/batches/{batch_id}/cases/{case_id}/reviews',
  '/api/v1/batches/{batch_id}/cases/{case_id}/evidence/{evidence_id}/content',
  '/api/v1/health',
]

test('十接口类型齐备：九条路径 + 全部读写方法', async () => {
  const generated = await generateTypes()
  for (const path of frozenPaths) {
    expect(generated, `缺少路径 ${path}`).toContain(`"${path}"`)
  }
  // 十个操作（6 GET + 4 POST）的存在性由 tests/contracts/client.test.ts 的
  // 类型化 api.GET/POST 调用保证：路径或方法不存在时 TypeScript 直接编译失败。
  expect(generated).toContain('get?:')
  expect(generated).toContain('post?:')
})

test('关键业务 DTO 类型生成', async () => {
  const generated = await generateTypes()
  for (const schema of [
    'BatchWorkspaceView',
    'BatchListView',
    'CaseQueueView',
    'CaseDetailView',
    'ReviewResultView',
    'ReviewOptionsView',
    'BusinessError',
    'HealthView',
    'ApprovedReviewRequest',
    'ModifiedApprovedReviewRequest',
    'RejectedWithJudgmentReviewRequest',
    'InsufficientEvidenceReviewRequest',
  ]) {
    expect(generated, `缺少 Schema ${schema}`).toContain(schema)
  }
})

test('重新生成无差异（真实文件检查）', async () => {
  const result = await checkCommittedTypes()
  expect(result.ok).toBe(true)
})

test('Windows 换行符不被误判为合同漂移', async () => {
  const regenerated = await generateTypes()
  const windowsCheckout = regenerated.replaceAll('\n', '\r\n')

  expect(compareSources(regenerated, windowsCheckout).ok).toBe(true)
})

test('旧生成物可被检查发现（漂移检测自证）', async () => {
  const regenerated = await generateTypes()
  const committed = readFileSync(GENERATED_URL, 'utf-8')

  // 与已提交文件一致时通过
  expect(compareSources(regenerated, committed).ok).toBe(true)

  // 模拟旧生成物：替换一个 Schema 名，模拟旧版 OpenAPI 产物
  const stale = committed.replace('BatchWorkspaceView', 'BatchWorkspaceViewV0')
  const result = compareSources(regenerated, stale)
  expect(result.ok).toBe(false)
  if (!result.ok) {
    expect(result.message).toContain('gen:api')
  }

  // 模拟尾部截断的旧生成物
  const truncated = committed.slice(0, committed.length - 200)
  expect(compareSources(regenerated, truncated).ok).toBe(false)
})

test('检查脚本不写盘：检查前后生成文件内容一致', async () => {
  const before = readFileSync(generatedPath, 'utf-8')
  await checkCommittedTypes()
  const after = readFileSync(generatedPath, 'utf-8')
  expect(after).toBe(before)
})
