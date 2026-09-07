import { readdirSync, readFileSync, statSync } from 'node:fs'
import { dirname, extname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const frontendRoot = resolve(here, '..')

function listSourceFiles(dir: string): string[] {
  const found: string[] = []
  for (const name of readdirSync(dir)) {
    const full = join(dir, name)
    if (statSync(full).isDirectory()) {
      found.push(...listSourceFiles(full))
    } else if (['.html', '.ts', '.tsx', '.css'].includes(extname(name))) {
      found.push(full)
    }
  }
  return found
}

test('源码与页面不引用任何外部资源地址', () => {
  const scanned = [
    resolve(frontendRoot, 'index.html'),
    ...listSourceFiles(resolve(frontendRoot, 'src')),
  ]
  for (const file of scanned) {
    const content = readFileSync(file, 'utf-8')
    expect(content, `${file} 引用了外部地址`).not.toMatch(/https?:\/\//)
    expect(content, `${file} 使用了外部 @import`).not.toMatch(/@import\s+url\(/)
  }
})

test('字体与许可证本地存在', () => {
  const font = statSync(resolve(frontendRoot, 'src/assets/fonts/InterVariable.woff2'))
  expect(font.size).toBeGreaterThan(100_000)
  const license = readFileSync(
    resolve(frontendRoot, 'src/assets/fonts/LICENSE-OFL.txt'),
    'utf-8',
  )
  expect(license).toContain('SIL OPEN FONT LICENSE')
})
