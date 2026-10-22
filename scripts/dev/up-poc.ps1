<#
.SYNOPSIS
    启动 RuoYi POC（独立 Compose 项目 ruoyi-poc）。

.DESCRIPTION
    POC 源码目前**不在本仓库**（见 docs/POC-SHARING-PLAN.md 与 issue #1），
    所以本脚本先定位 POC 目录：
      1) -PocRoot 参数
      2) 环境变量 POC_ROOT
      3) 仓库同级目录 ruoyi-plus-poc
    找不到就明确报错并退出，不会“猜一个路径然后半启动”。

    跨栈依赖：POC 的 poc-importapi 复用主项目构建的镜像 campus-import-api:0.1.0，
    因此必须先跑过 .\up-main.ps1。

.EXAMPLE
    $env:POC_ROOT = 'D:\ai\ruoyi-plus-poc'
    .\scripts\dev\up-poc.ps1
#>
[CmdletBinding()]
param(
    [string]$PocRoot
)

. (Join-Path $PSScriptRoot '_common.ps1')
$repo = Get-RepoRoot

# --- 1. 定位 POC ---
$candidates = @()
if ($PocRoot) { $candidates += $PocRoot }
if ($env:POC_ROOT) { $candidates += $env:POC_ROOT }
$candidates += (Join-Path (Split-Path $repo -Parent) 'ruoyi-plus-poc')
$candidates += (Join-Path $repo 'ruoyi-plus-poc')

$root = $null
foreach ($c in $candidates) {
    if ($c -and (Test-Path $c)) { $root = (Resolve-Path $c).Path; break }
}
if (-not $root) {
    Write-Status FAIL '未找到 POC 源码目录'
    Write-Host '  POC 尚未入库（issue #1 / docs/POC-SHARING-PLAN.md）。请任选一种：'
    Write-Host '   1) $env:POC_ROOT = ''<POC 目录>'' 后再执行'
    Write-Host '   2) .\scripts\dev\up-poc.ps1 -PocRoot ''<POC 目录>'''
    exit 1
}
Write-Status PASS "POC 目录：$root"

$pocCompose = Join-Path $root 'docker-compose.poc.yml'
if (-not (Test-Path $pocCompose)) {
    Write-Status FAIL "POC 目录里没有 docker-compose.poc.yml：$root"
    exit 1
}

# --- 2. 跨栈依赖：主项目镜像 ---
$image = & docker images -q 'campus-import-api:0.1.0'
if (-not $image) {
    Write-Status FAIL '镜像 campus-import-api:0.1.0 不存在：POC 复用主项目镜像，请先跑 .\scripts\dev\up-main.ps1'
    exit 1
}
Write-Status PASS '主项目镜像 campus-import-api:0.1.0 已就位'

# --- 3. 启动（独立项目名与网络，不连主库） ---
Push-Location $root
try {
    & docker compose -p ruoyi-poc -f $pocCompose up -d --build
    $code = $LASTEXITCODE
}
finally { Pop-Location }

if ($code -ne 0) { Write-Status FAIL 'POC compose up 失败'; exit $code }

Write-Status INFO 'POC 已启动（独立项目 ruoyi-poc，网络/库与主栈隔离）'
Write-Host '  FastAPI 不发布宿主端口，仅容器内可达 —— 这是刻意的，见 issue #3 红线'
Write-Host '  查看状态：docker compose -p ruoyi-poc ps'
exit 0
