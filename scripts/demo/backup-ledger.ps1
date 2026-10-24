[CmdletBinding()]
param(
    [string]$Destination,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$repo = Resolve-Path (Join-Path $PSScriptRoot '..\..')
$ledger = Join-Path $repo 'demo-api\state\ledger.json'

if (-not (Test-Path -LiteralPath $ledger)) {
    Write-Host '[demo] ledger is empty; nothing to back up.'
    exit 0
}

if (-not $Destination) {
    $backupDir = Join-Path $repo 'demo-api\state\backups'
    New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
    $Destination = Join-Path $backupDir ("ledger-{0}.json" -f (Get-Date -Format 'yyyyMMdd-HHmmss'))
}

$destinationPath = [System.IO.Path]::GetFullPath($Destination)
if ((Test-Path -LiteralPath $destinationPath) -and -not $Force) {
    throw "Backup target already exists: $destinationPath. Use -Force to overwrite."
}

$parent = Split-Path -Parent $destinationPath
if ($parent -and -not (Test-Path -LiteralPath $parent)) {
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
}

Copy-Item -LiteralPath $ledger -Destination $destinationPath -Force
try {
    $payload = Get-Content -LiteralPath $destinationPath -Raw -Encoding UTF8 | ConvertFrom-Json
} catch {
    Remove-Item -LiteralPath $destinationPath -Force
    throw "Backup validation failed; removed partial copy: $destinationPath"
}
if ($null -eq $payload.changes -or $null -eq $payload.checked) {
    Remove-Item -LiteralPath $destinationPath -Force
    throw 'Backup validation failed: changes or checked field is missing.'
}

Write-Host "[demo] ledger backed up to $destinationPath"
