# 工具链检查与依赖同步入口（技术实施规格第 14 节）。
# 只使用项目相对路径与 PATH，不写成员电脑绝对路径。
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot

function Test-Tool([string]$Name) {
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

Write-Host '== PSIT 工具链检查 ==' -ForegroundColor Cyan

$backendReady = $true
if (Test-Tool 'uv') {
    Write-Host ("uv      {0}" -f (uv --version))
}
else {
    Write-Warning '缺少 uv：请先安装 https://docs.astral.sh/uv/getting-started/installation/'
    $backendReady = $false
}

if (Test-Tool 'python') {
    Write-Host ("python  {0}" -f (python --version))
}
else {
    Write-Host 'python  未在 PATH（uv 会按 .python-version 自动提供 3.12）'
}

foreach ($tool in @('node', 'pnpm')) {
    if (Test-Tool $tool) {
        Write-Host ("{0,-7} {1}" -f $tool, (& $tool --version))
    }
    else {
        Write-Warning ("缺少 {0}：M4-01 前端初始化前需要安装（node: https://nodejs.org/；pnpm: corepack enable）" -f $tool)
    }
}

if (-not $backendReady) { exit 1 }

$frontendExit = 0
Write-Host '== 同步后端依赖（uv.lock）==' -ForegroundColor Cyan
Push-Location $repoRoot
uv sync --frozen
$syncExit = $LASTEXITCODE
if (Test-Path 'frontend\package.json') {
    Write-Host '== 同步前端依赖（pnpm-lock.yaml）==' -ForegroundColor Cyan
    pnpm --dir frontend install --frozen-lockfile
    $frontendExit = $LASTEXITCODE
}
else {
    Write-Host 'frontend 尚未初始化（等待 M4-01），跳过前端依赖同步。'
}
Pop-Location

if ($syncExit -ne 0) { exit $syncExit }
if ($frontendExit -ne 0) { exit $frontendExit }
Write-Host 'bootstrap 完成。' -ForegroundColor Green
exit 0
