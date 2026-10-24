[CmdletBinding()]
param(
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$repo = Resolve-Path (Join-Path $PSScriptRoot '..\..')
$stateDir = Join-Path $repo 'demo-api\state'
$ledger = Join-Path $stateDir 'ledger.json'
$backupDir = Join-Path $stateDir 'backups'

if (-not (Test-Path -LiteralPath $ledger)) {
    Write-Host '[demo] ledger is already empty.'
    exit 0
}

if (-not $Force) {
    Write-Host "[demo] this will delete: $ledger"
    Write-Host '[demo] re-run with -Force to confirm.'
    exit 1
}

# A running demo-api can re-create the file mid-delete, so reset only happens while it is stopped.
$wasRunning = (& docker inspect --format '{{.State.Running}}' campus-demo-api 2>$null) -eq 'true'
if ($wasRunning) {
    & docker stop campus-demo-api | Out-Null
}

try {
    New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
    $safety = Join-Path $backupDir ("ledger-before-reset-{0}.json" -f (Get-Date -Format 'yyyyMMdd-HHmmss'))
    Copy-Item -LiteralPath $ledger -Destination $safety -Force
    Remove-Item -LiteralPath $ledger -Force
    Write-Host "[demo] previous ledger saved to $safety"
} finally {
    if ($wasRunning) {
        & docker start campus-demo-api | Out-Null
    }
}

if ($wasRunning) {
    $health = ''
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Seconds 1
        $health = & docker inspect --format '{{.State.Health.Status}}' campus-demo-api 2>$null
        if ($health -eq 'healthy') { break }
    }
    if ($health -ne 'healthy') {
        throw "Ledger reset but demo-api did not become healthy: $health"
    }
}

Write-Host "[demo] demo ledger removed. Base demo data is unchanged."
Write-Host "[demo] to undo: .\scripts\demo\restore-ledger.ps1 -File <backup path> -Force"
