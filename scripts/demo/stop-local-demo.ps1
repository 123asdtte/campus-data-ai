[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$repo = Resolve-Path (Join-Path $PSScriptRoot '..\..')
Set-Location $repo

& docker compose -p campus-demo -f docker-compose.demo.yml down
foreach ($name in @('campus-demo-api', 'campus-web-demo')) {
    if (& docker ps -a --filter "name=^/$name$" --format '{{.Names}}') {
        & docker rm -f $name | Out-Null
    }
}
Write-Host '[demo] demo stack stopped. The main stack and 8082 frontend are untouched.'
