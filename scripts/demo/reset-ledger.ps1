[CmdletBinding()]
param(
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$repo = Resolve-Path (Join-Path $PSScriptRoot '..\..')
$ledger = Join-Path $repo 'demo-api\state\ledger.json'

if (-not (Test-Path -LiteralPath $ledger)) {
    Write-Host '[demo] ledger is already empty.'
    exit 0
}

if (-not $Force) {
    Write-Host "[demo] this will delete: $ledger"
    Write-Host '[demo] re-run with -Force to confirm.'
    exit 1
}

Remove-Item -LiteralPath $ledger -Force
Write-Host '[demo] demo ledger removed. Base demo data is unchanged.'
