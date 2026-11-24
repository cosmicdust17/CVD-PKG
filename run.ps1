param([Parameter(ValueFromRemainingArguments=$true)][string[]]$TaskArgs)
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$depsDir = Join-Path $projectRoot '.deps'
$oldPythonPath = $env:PYTHONPATH
$previousToken = $env:RAGFLOW_API_KEY
$previousChatModel = $env:RAGFLOW_CHAT_MODEL
$previousEmbeddingModel = $env:RAGFLOW_EMBEDDING_MODEL
$tokenMemory = [IntPtr]::Zero
$locationPushed = $false
try {
    if (Test-Path -LiteralPath $depsDir) { $env:PYTHONPATH = "$depsDir;$projectRoot;$oldPythonPath" }
    $credentialFile = Join-Path $projectRoot '.secrets\ragflow-token.dpapi'
    if (-not $env:RAGFLOW_API_KEY -and (Test-Path -LiteralPath $credentialFile)) {
        $encryptedToken = (Get-Content -LiteralPath $credentialFile -Raw).Trim()
        $localToken = ConvertTo-SecureString -String $encryptedToken
        $tokenMemory = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($localToken)
        $env:RAGFLOW_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($tokenMemory).Trim()
    }
    $modelFile = Join-Path $projectRoot 'data\model-selection.json'
    if (Test-Path -LiteralPath $modelFile) {
        $selectedModels = Get-Content -LiteralPath $modelFile -Raw | ConvertFrom-Json
        if (-not $env:RAGFLOW_CHAT_MODEL) { $env:RAGFLOW_CHAT_MODEL = $selectedModels.chat_model }
        if (-not $env:RAGFLOW_EMBEDDING_MODEL) { $env:RAGFLOW_EMBEDDING_MODEL = $selectedModels.embedding_model }
    }
    Push-Location $projectRoot
    $locationPushed = $true
    python @TaskArgs
    $pythonExit = $LASTEXITCODE
} finally {
    if ($locationPushed) { Pop-Location }
    $env:PYTHONPATH = $oldPythonPath
    $env:RAGFLOW_API_KEY = $previousToken
    $env:RAGFLOW_CHAT_MODEL = $previousChatModel
    $env:RAGFLOW_EMBEDDING_MODEL = $previousEmbeddingModel
    if ($tokenMemory -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($tokenMemory) }
}
exit $pythonExit
