# 本机演示启动入口（技术实施规格第 14 节；M3-08）。
# 仅负责发现项目根与启动 Python 入口；配置、迁移、锁和恢复由 M3 生命周期适配层统一处理。
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$previousPythonPath = $env:PYTHONPATH
Push-Location $repoRoot
try {
    & pnpm --dir frontend run build
    if ($LASTEXITCODE -ne 0) {
        throw "PSIT frontend build failed (exit $LASTEXITCODE)."
    }

    $env:PYTHONPATH = Join-Path $repoRoot 'backend'
    & uv run python -m app.modules.application.launcher
    if ($LASTEXITCODE -ne 0) {
        throw "PSIT demo startup failed (exit $LASTEXITCODE)."
    }
}
finally {
    if ($null -eq $previousPythonPath) {
        Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
    }
    else {
        $env:PYTHONPATH = $previousPythonPath
    }
    Pop-Location
}
