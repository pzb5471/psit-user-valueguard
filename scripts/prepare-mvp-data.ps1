# 固定演示与验收案例包生成入口（M1-09）。原始数据与产物均不进入 Git。
[CmdletBinding()]
param(
    [string]$SourceRoot
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$requiredSource = 'dataprocessing\output\data_with_context.csv'

if (-not $SourceRoot) {
    $SourceRoot = Join-Path (Split-Path -Parent $repoRoot) 'source_data\ecommercedata-main'
}
$resolvedSource = [System.IO.Path]::GetFullPath($SourceRoot)
if (-not (Test-Path -LiteralPath (Join-Path $resolvedSource $requiredSource) -PathType Leaf)) {
    Write-Error ("DATA_SOURCE_REQUIRED: missing {0} under {1}. Pass -SourceRoot explicitly." -f $requiredSource, $resolvedSource)
    exit 2
}

$previousSourceRoot = $env:PSIT_SOURCE_ROOT
Push-Location $repoRoot
try {
    $env:PSIT_SOURCE_ROOT = $resolvedSource
    & uv run python -m tools.data_preparation --source-root $resolvedSource
    if ($LASTEXITCODE -ne 0) {
        throw "MVP data generation failed (exit $LASTEXITCODE)."
    }
    & powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\test.ps1 -Task M1-09
    if ($LASTEXITCODE -ne 0) {
        throw "M1-09 acceptance failed (exit $LASTEXITCODE)."
    }
}
finally {
    if ($null -eq $previousSourceRoot) {
        Remove-Item Env:PSIT_SOURCE_ROOT -ErrorAction SilentlyContinue
    }
    else {
        $env:PSIT_SOURCE_ROOT = $previousSourceRoot
    }
    Pop-Location
}

Write-Host '[PASS] Fixed MVP (10 cases) and ACCEPTANCE (5 cases) packages passed M1-09.' -ForegroundColor Green
