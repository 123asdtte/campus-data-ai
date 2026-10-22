<#
.SYNOPSIS
    停止 RuoYi POC（保留其数据卷）。

.DESCRIPTION
    与 down-main.ps1 同规则：日常停止不带 -v。
    -Purge 删卷时需输入 DELETE 二次确认。

.EXAMPLE
    .\scripts\dev\down-poc.ps1
    .\scripts\dev\down-poc.ps1 -Purge
#>
[CmdletBinding()]
param(
    [string]$PocRoot,
    [switch]$Purge,
    [switch]$Force
)

. (Join-Path $PSScriptRoot '_common.ps1')
$repo = Get-RepoRoot

$candidates = @()
if ($PocRoot) { $candidates += $PocRoot }
if ($env:POC_ROOT) { $candidates += $env:POC_ROOT }
$candidates += (Join-Path (Split-Path $repo -Parent) 'ruoyi-plus-poc')
$candidates += (Join-Path $repo 'ruoyi-plus-poc')

$root = $null
foreach ($c in $candidates) { if ($c -and (Test-Path $c)) { $root = (Resolve-Path $c).Path; break } }
if (-not $root) { Write-Status FAIL '未找到 POC 源码目录（设置 $env:POC_ROOT）'; exit 1 }

if ($Purge -and -not $Force) {
    Write-Host '即将删除 ruoyi-poc 项目的数据卷（不可恢复）。' -ForegroundColor Red
    $answer = Read-Host '确认删除请输入 DELETE（大写）'
    if ($answer -cne 'DELETE') { Write-Status INFO '已取消'; exit 1 }
}

$args = @('compose', '-p', 'ruoyi-poc', '-f', (Join-Path $root 'docker-compose.poc.yml'), 'down')
if ($Purge) { $args += '-v' }

& docker @args
$code = $LASTEXITCODE
if ($code -eq 0) {
    if ($Purge) { Write-Status INFO 'POC 容器与数据卷已删除' }
    else { Write-Status PASS 'POC 已停止，数据卷保留' }
}
exit $code
