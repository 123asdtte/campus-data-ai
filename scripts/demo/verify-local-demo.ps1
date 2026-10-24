[CmdletBinding()]
param(
    [switch]$SkipE2E
)

$ErrorActionPreference = 'Stop'
$repo = Resolve-Path (Join-Path $PSScriptRoot '..\..')
Set-Location $repo

function Assert-LastExit([string]$Step) {
    if ($LASTEXITCODE -ne 0) {
        throw "$Step failed with exit code $LASTEXITCODE"
    }
}

Write-Host '== 1/4 web health'
$code = & curl.exe -s -o NUL -w '%{http_code}' 'http://127.0.0.1:8083/healthz'
if ($code -ne '200') {
    throw "demo stack is not healthy on http://127.0.0.1:8083 (HTTP $code). Run scripts/demo/start-local-demo.ps1 first."
}
Write-Host "web health: HTTP $code"

Write-Host '== 2/4 read-only smoke'
& python scripts/demo/smoke-demo.py
Assert-LastExit 'smoke-demo.py'

Write-Host '== 3/4 demo-api unit tests'
& python -m unittest discover -s demo-api/tests -p 'test_*.py'
Assert-LastExit 'demo-api unit tests'

if ($SkipE2E) {
    Write-Host '== 4/4 E2E skipped (-SkipE2E)'
} else {
    Write-Host '== 4/4 Playwright E2E'
    Push-Location (Join-Path $repo 'web')
    try {
        & npm run test:e2e
        Assert-LastExit 'Playwright E2E'
    } finally {
        Pop-Location
    }
}

Write-Host 'All local demo checks passed.'
