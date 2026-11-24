$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$runtimeDir = Join-Path $PSScriptRoot 'runtime'
$logDir = Join-Path $projectRoot 'logs'
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
if (-not (Test-Path -LiteralPath $runtimeDir)) { throw 'Run python deployment/prepare.py first.' }
docker info --format 'Server={{.ServerVersion}} Memory={{.MemTotal}} CPUs={{.NCPU}}'
if ($LASTEXITCODE -ne 0) { throw 'Docker Engine unavailable. Start Docker Desktop and retry.' }
Push-Location $runtimeDir
try {
    docker compose -p hfkg-ragflow -f docker-compose.yml config --quiet
    if ($LASTEXITCODE -ne 0) { throw 'Compose validation failed' }
    docker compose -p hfkg-ragflow -f docker-compose.yml pull 2>&1 | Tee-Object -FilePath (Join-Path $logDir 'compose-pull.log')
    if ($LASTEXITCODE -ne 0) { throw 'Image download failed; see logs/compose-pull.log' }
    docker compose -p hfkg-ragflow -f docker-compose.yml up -d 2>&1 | Tee-Object -FilePath (Join-Path $logDir 'compose-up.log')
    if ($LASTEXITCODE -ne 0) { throw 'Container startup failed; see logs/compose-up.log' }
    docker compose -p hfkg-ragflow -f docker-compose.yml ps
} finally { Pop-Location }
