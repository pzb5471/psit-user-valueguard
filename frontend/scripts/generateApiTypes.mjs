/**
 * 从 M3 OpenAPI 快照（tests/m3/openapi/openapi_snapshot.json，唯一合同真源）生成
 * TypeScript 类型到 src/api/schema.gen.d.ts（M4-02；生成文件禁止手改）。
 * generateTypes 是纯函数（只在内存生成）；只有直接运行本脚本时才写盘。
 */
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import openapiTS, { astToString } from 'openapi-typescript'

export const SNAPSHOT_URL = new URL(
  '../../tests/m3/openapi/openapi_snapshot.json',
  import.meta.url,
)
export const GENERATED_URL = new URL('../src/api/schema.gen.d.ts', import.meta.url)
export const SNAPSHOT_PATH = fileURLToPath(SNAPSHOT_URL)

/**
 * 在内存中重新生成生成物内容（字符串），不写任何文件。
 * 直接读取文件内容传入：避免 openapi-typescript 对 Windows 盘符路径与 file: URL 的解析差异。
 */
export async function generateTypes() {
  const document = readFileSync(SNAPSHOT_PATH, 'utf-8')
  const ast = await openapiTS(document)
  return astToString(ast)
}

/** 把生成内容写入生成文件。 */
export async function writeGeneratedTypes() {
  mkdirSync(dirname(fileURLToPath(GENERATED_URL)), { recursive: true })
  writeFileSync(GENERATED_URL, await generateTypes())
}

if (import.meta.url === pathToFileURL(process.argv[1] ?? '').href) {
  await writeGeneratedTypes()
  console.log('[gen:api] 已生成 src/api/schema.gen.d.ts')
}
