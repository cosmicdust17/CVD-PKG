$ErrorActionPreference = 'Stop'
$previousToken = $env:RAGFLOW_API_KEY
$tokenMemory = [IntPtr]::Zero
try {
    $localToken = Read-Host 'Paste your LOCAL RAGFlow API token (input is hidden)' -AsSecureString
    $tokenMemory = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($localToken)
    $env:RAGFLOW_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($tokenMemory).Trim()
    & (Join-Path $PSScriptRoot 'run.ps1') -m hfkg.configure
    if ($LASTEXITCODE -ne 0) { throw 'Token or default-model verification failed. No new token was saved.' }
    $credentialDir = Join-Path $PSScriptRoot '.secrets'
    New-Item -ItemType Directory -Path $credentialDir -Force | Out-Null
    $localToken | ConvertFrom-SecureString | Set-Content -LiteralPath (Join-Path $credentialDir 'ragflow-token.dpapi') -Encoding UTF8
    Write-Host 'Token saved with Windows current-user encryption in .secrets/ragflow-token.dpapi.'
    Write-Host 'Configuration complete. No PDF has been submitted yet.'
} finally {
    if ($tokenMemory -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($tokenMemory) }
    $env:RAGFLOW_API_KEY = $previousToken
}
