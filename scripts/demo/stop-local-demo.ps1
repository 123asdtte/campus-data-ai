[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
& docker rm -f campus-web-demo 2>$null | Out-Null
& docker rm -f campus-demo-api 2>$null | Out-Null
Write-Host '[demo] campus-web-demo and campus-demo-api stopped. The main stack and 8082 frontend are untouched.'
