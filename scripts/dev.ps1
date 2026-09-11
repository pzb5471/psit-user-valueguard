# 开发环境入口（技术实施规格第 14 节：用同一配置启动 FastAPI 和 Vite 开发环境）。
# FastAPI 与 Vite 由同一配置启动；Ctrl+C 统一停止两个开发进程。
[CmdletBinding()]
param(
    [switch]$Check
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$previousPythonPath = $env:PYTHONPATH
Push-Location $repoRoot
try {
    $env:PYTHONPATH = Join-Path $repoRoot 'backend'
    $arguments = @('run', 'python', '-m', 'app.modules.application.dev_supervisor')
    if ($Check) {
        $arguments += '--check'
    }
    & uv @arguments
    exit $LASTEXITCODE
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
