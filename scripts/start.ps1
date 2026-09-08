# 本机演示启动入口（技术实施规格第 14 节；M3-08）。
# 仅负责发现项目根与启动 Python 入口；配置、迁移、锁和恢复由 M3 生命周期适配层统一处理。
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
Push-Location $repoRoot
try {
    & uv run python -m app.modules.application.launcher
    if ($LASTEXITCODE -ne 0) {
        throw "本机演示启动失败（exit $LASTEXITCODE）。"
    }
}
finally {
    Pop-Location
}
