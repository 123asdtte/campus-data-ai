[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$repo = Resolve-Path (Join-Path $PSScriptRoot '..\..')
Set-Location $repo

$gateway = & docker ps --filter 'name=campus-gateway' --filter 'status=running' --format '{{.Names}}'
if (-not $gateway) {
    throw 'campus-gateway is not running. Start the main campus-data-ai stack first.'
}

Write-Host '[demo] building local web image ...'
& docker build -f web/Dockerfile.web -t campus-data-web:local-demo web
if ($LASTEXITCODE -ne 0) { throw 'docker build failed' }

& docker rm -f campus-web-demo 2>$null | Out-Null
Write-Host '[demo] starting campus-web-demo on 127.0.0.1:8083 ...'
& docker run -d --name campus-web-demo --network campus-net -p 127.0.0.1:8083:80 --restart unless-stopped campus-data-web:local-demo | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'docker run failed' }

Start-Sleep -Seconds 3
$code = & curl.exe -s -o NUL -w '%{http_code}' http://127.0.0.1:8083/healthz
if ($code -ne '200') { throw "web health check failed: HTTP $code" }

Write-Host ''
Write-Host 'Local demo: http://127.0.0.1:8083' -ForegroundColor Cyan
Write-Host 'Login: admin / admin123' -ForegroundColor Cyan
Write-Host 'Existing 8082 frontend is untouched.'
Start-Process 'http://127.0.0.1:8083'
