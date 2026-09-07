/**
 * 合同差异检查（M4-02 自动验收：重新生成无差异、旧生成物可被检查发现）。
 * 用法：node scripts/checkApiTypes.mjs（差异时 exit 1）；比较逻辑导出给 vitest 复用。
 * 本脚本不写盘：在内存重新生成后与已提交文件逐字符比较。
 */
import { readFileSync } from 'node:fs'
import { pathToFileURL } from 'node:url'
import { generateTypes, GENERATED_URL } from './generateApiTypes.mjs'

/**
 * 比较重新生成内容与已提交生成物；任何漂移（含旧生成物）都会被发现。
 * @returns {{ ok: true } | { ok: false, message: string }}
 */
export function compareSources(regenerated, committed) {
  if (regenerated === committed) {
    return { ok: true }
  }
  let firstDiff = -1
  const shorter = Math.min(regenerated.length, committed.length)
  for (let i = 0; i <= shorter; i += 1) {
    if (regenerated[i] !== committed[i]) {
      firstDiff = i
      break
    }
  }
  return {
    ok: false,
    message:
      `src/api/schema.gen.d.ts 与 OpenAPI 快照（tests/m3/openapi/openapi_snapshot.json）不一致，` +
      `首个差异在字符偏移 ${firstDiff}。请运行 pnpm --dir frontend run gen:api 重新生成并提交，不要手改生成文件。`,
  }
}

/** 对已提交的生成文件执行完整检查（不写盘）。 */
export async function checkCommittedTypes() {
  const regenerated = await generateTypes()
  const committed = readFileSync(GENERATED_URL, 'utf-8')
  return compareSources(regenerated, committed)
}

if (import.meta.url === pathToFileURL(process.argv[1] ?? '').href) {
  const result = await checkCommittedTypes()
  if (!result.ok) {
    console.error(`[check:api] FAIL：${result.message}`)
    process.exit(1)
  }
  console.log('[check:api] 生成物与 OpenAPI 快照一致。')
}
