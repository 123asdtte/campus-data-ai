[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$File,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$repo = Resolve-Path (Join-Path $PSScriptRoot '..\..')
$stateDir = Join-Path $repo 'demo-api\state'
$ledger = Join-Path $stateDir 'ledger.json'
$backupDir = Join-Path $stateDir 'backups'

if (-not (Test-Path -LiteralPath $File)) {
    throw "Backup file not found: $File"
}
$source = (Resolve-Path -LiteralPath $File).Path
if ($source -eq [System.IO.Path]::GetFullPath($ledger)) {
    throw 'The current ledger cannot be used as the restore source.'
}

$payload = Get-Content -LiteralPath $source -Raw -Encoding UTF8 | ConvertFrom-Json
if ($null -eq $payload.changes -or $null -eq $payload.checked) {
    throw 'Invalid ledger backup: changes or checked field is missing.'
}
if (-not ($payload.changes -is [System.Array])) {
    throw 'Invalid ledger backup: changes must be an array.'
}
if ($payload.changes.Count -gt 500) {
    throw 'Backup exceeds the local demo limit of 500 changes; restore refused.'
}

if (Test-Path -LiteralPath $ledger) {
    New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
    $safety = Join-Path $backupDir ("ledger-before-restore-{0}.json" -f (Get-Date -Format 'yyyyMMdd-HHmmss'))
    Copy-Item -LiteralPath $ledger -Destination $safety -Force
    Write-Host "[demo] current ledger saved to $safety"
} elseif (-not $Force) {
    Write-Host '[demo] no current ledger; restore will create one. Re-run with -Force to confirm.'
    exit 1
}

$wasRunning = (& docker inspect --format '{{.State.Running}}' campus-demo-api 2>$null) -eq 'true'
if ($wasRunning) {
    & docker stop campus-demo-api | Out-Null
}

$temp = Join-Path $stateDir 'ledger.restore.tmp'
try {
    Copy-Item -LiteralPath $source -Destination $temp -Force
    $null = Get-Content -LiteralPath $temp -Raw -Encoding UTF8 | ConvertFrom-Json
    Move-Item -LiteralPath $temp -Destination $ledger -Force
} finally {
    if (Test-Path -LiteralPath $temp) {
        Remove-Item -LiteralPath $temp -Force
    }
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
        throw "Ledger restored but demo-api did not become healthy: $health"
    }
}

Write-Host "[demo] ledger restored from $source"
