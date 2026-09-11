# 统一确定性测试入口（技术实施规格第 16.3 节）：
#   .\scripts\test.ps1 -Task <Task-ID>          运行单张卡声明的测试
#   .\scripts\test.ps1 -Module <M1|M2|M3|M4>    合并前运行所属模块
#   .\scripts\test.ps1                          无参数运行全量确定性测试（M3-09 / M4-09 门槛）
# 分发注册表：config\test_tasks.json。仅 M2-10 调用真实 GLM，其余入口均为确定性测试。
param(
    [string]$Task,
    [ValidateSet('M1', 'M2', 'M3', 'M4')]
    [string]$Module
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$registryPath = Join-Path $repoRoot 'config\test_tasks.json'

function Write-Fail([string]$Message) {
    Write-Host "[FAIL] $Message" -ForegroundColor Red
    exit 1
}

function Invoke-Checked([string]$Label, [string]$File, [string[]]$Arguments) {
    Write-Host "== $Label ==" -ForegroundColor Cyan
    & $File @Arguments
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "$Label 未通过（exit $LASTEXITCODE）。"
    }
}

if ($Task -and $Module) {
    Write-Fail '不能同时指定 -Task 与 -Module。'
}

if (-not (Test-Path $registryPath)) {
    Write-Fail "缺少测试分发注册表：$registryPath"
}
$registry = Get-Content $registryPath -Raw -Encoding UTF8 | ConvertFrom-Json

$scopeLabel = ''
$entry = $null
if ($Task) {
    $entry = $registry.tasks.$Task
    if (-not $entry) {
        $known = ($registry.tasks.PSObject.Properties.Name | Sort-Object) -join ', '
        Write-Fail "未知 Task ID：'$Task'。已注册：$known"
    }
    $scopeLabel = "Task $Task"
}
elseif ($Module) {
    $entry = $registry.modules.$Module
    if (-not $entry) {
        Write-Fail "未知模块：'$Module'。"
    }
    $scopeLabel = "Module $Module"
}

Push-Location $repoRoot
try {
    if ($Task -or $Module) {
        switch ($entry.runner) {
            'pytest' {
                $declared = @($entry.paths)
                $paths = @($declared | Where-Object { Test-Path $_ })
                if ($paths.Count -eq 0) {
                    Write-Fail "$scopeLabel 声明的测试路径尚不存在：$($declared -join ', ')"
                }
                $skipped = @($declared | Where-Object { -not (Test-Path $_) })
                if ($skipped.Count -gt 0) {
                    Write-Warning "跳过尚不存在的路径：$($skipped -join ', ')"
                }
                $pytestArgs = @('run', 'pytest') + $paths
                if ($entry.marker) {
                    $pytestArgs += @('-m', [string]$entry.marker)
                }
                Invoke-Checked 'Ruff' 'uv' @('run', 'ruff', 'check', '.')
                Invoke-Checked 'Pyright' 'uv' @('run', 'pyright')
                $previousRequireSource = $env:PSIT_REQUIRE_SOURCE_ROOT
                try {
                    if ($Task -eq 'M1-09') {
                        $env:PSIT_REQUIRE_SOURCE_ROOT = '1'
                    }
                    Invoke-Checked "Pytest（$scopeLabel）" 'uv' $pytestArgs
                }
                finally {
                    if ($null -eq $previousRequireSource) {
                        Remove-Item Env:PSIT_REQUIRE_SOURCE_ROOT -ErrorAction SilentlyContinue
                    }
                    else {
                        $env:PSIT_REQUIRE_SOURCE_ROOT = $previousRequireSource
                    }
                }
            }
            'frontend' {
                if (-not (Test-Path 'frontend\package.json')) {
                    Write-Fail "frontend 尚未初始化（等待 M4-01），无法运行 $scopeLabel 的前端测试。"
                }
                $script = [string]$entry.script
                if (-not $script) { $script = 'test' }
                Invoke-Checked "前端测试（$scopeLabel）" 'pnpm' @('--dir', 'frontend', 'run', $script)
            }
            default {
                Write-Fail "未知 runner：'$($entry.runner)'（$scopeLabel）。"
            }
        }
    }
    else {
        $scopeLabel = '全量'
        Invoke-Checked 'Ruff' 'uv' @('run', 'ruff', 'check', '.')
        Invoke-Checked 'Pyright' 'uv' @('run', 'pyright')
        Invoke-Checked 'Pytest（全量，不含 live_glm）' 'uv' @('run', 'pytest')
        if (Test-Path 'frontend\package.json') {
            Invoke-Checked '前端测试' 'pnpm' @('--dir', 'frontend', 'run', 'test')
        }
        else {
            Write-Warning 'frontend 未初始化（等待 M4-01），全量测试暂不含前端。'
        }
    }
}
finally {
    Pop-Location
}

$passKind = if ($Task -eq 'M2-10') { '真实模型验证' } else { '确定性测试' }
Write-Host "[PASS] $scopeLabel 已通过$passKind。" -ForegroundColor Green
exit 0
