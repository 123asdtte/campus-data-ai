[CmdletBinding()]
param(
    [string]$Bind = '127.0.0.1',
    [int]$Port = 8083,
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
$repo = Resolve-Path (Join-Path $PSScriptRoot '..\..')
Set-Location $repo

$gateway = & docker ps --filter 'name=campus-gateway' --filter 'status=running' --format '{{.Names}}'
if (-not $gateway) {
    throw 'campus-gateway is not running. Start the main campus-data-ai stack first.'
}

# 旧版脚本用 docker run 创建的同名容器会与 Compose 冲突，先清理
foreach ($name in @('campus-demo-api', 'campus-web-demo')) {
    if (& docker ps -a --filter "name=^/$name$" --format '{{.Names}}') {
        & docker rm -f $name | Out-Null
    }
}

$env:DEMO_BIND = $Bind
$env:DEMO_PORT = "$Port"
$composeArgs = @('compose', '-p', 'campus-demo', '-f', 'docker-compose.demo.yml')

Write-Host "[demo] compositing demo stack on ${Bind}:${Port} ..."
& docker @composeArgs up -d --build
if ($LASTEXITCODE -ne 0) { throw 'docker compose up failed' }

$url = if ($Bind -in @('0.0.0.0', '::', '[::]')) { "http://127.0.0.1:$Port" } else { "http://${Bind}:$Port" }
$code = ''
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 1
    $code = & curl.exe -s -o NUL -w '%{http_code}' "$url/healthz"
    if ($code -eq '200') { break }
}
if ($code -ne '200') { throw "web health check failed: HTTP $code" }

Write-Host ''
Write-Host "Local demo: $url" -ForegroundColor Cyan
if ($Bind -ne '127.0.0.1') {
    Write-Host "Listening on ${Bind}:${Port}; confirm security group / IP allowlist before sharing." -ForegroundColor Yellow
}
Write-Host 'Login: admin / admin123' -ForegroundColor Cyan
Write-Host 'Existing 8082 frontend is untouched.'
if (-not $NoBrowser) { Start-Process $url }
