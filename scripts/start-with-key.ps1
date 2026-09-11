# 安全输入 ZAI_API_KEY 后启动正式本机入口；密钥只存在于本进程与子进程环境。
$ErrorActionPreference = 'Stop'
$secureKey = Read-Host -Prompt 'ZAI API Key' -AsSecureString
$secretPtr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)

try {
    $env:ZAI_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($secretPtr)
    & (Join-Path $PSScriptRoot 'start.ps1')
    $runExit = $LASTEXITCODE
}
finally {
    Remove-Item Env:ZAI_API_KEY -ErrorAction SilentlyContinue
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($secretPtr)
}

exit $runExit
