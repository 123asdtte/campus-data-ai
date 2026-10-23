[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
& docker rm -f campus-web-demo 2>$null | Out-Null
Write-Host '[demo] campus-web-demo stopped. The main stack and 8082 frontend are untouched.'
