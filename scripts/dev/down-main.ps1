<#
.SYNOPSIS
    停止主系统（默认保留数据卷）。

.DESCRIPTION
    日常停止只用 `.\down-main.ps1`（等价于 compose down，不带 -v），数据卷保留，
    下次 up-main 数据还在。

    删卷是**破坏性**操作，必须显式 -Purge，并且要手工输入卷名确认：
    这是 issue #3 的红线——日常 stop 绝不能带 -v。

.PARAMETER Purge
    连带删除数据卷（campus_pgdata / campus_appsmith_stacks / campus_uploads）。
    需要再输入 DELETE 二次确认；可加 -Force 跳过输入（仅 CI/脚本用）。

.EXAMPLE
    .\scripts\dev\down-main.ps1              # 日常停止，保留数据
    .\scripts\dev\down-main.ps1 -Purge       # 清库重来，二次确认后删卷
#>
[CmdletBinding()]
param(
    [switch]$Purge,
    [switch]$Force
)

. (Join-Path $PSScriptRoot '_common.ps1')

if (-not $Purge) {
    $code = Invoke-Compose down
    if ($code -eq 0) {
        Write-Status PASS '主栈已停止，数据卷保留（下次 up-main 数据仍在）'
        Write-Host '  保留的卷：campus_pgdata / campus_uploads / campus_gateway_pgdata / campus_gateway_redis'
        Write-Host '  历史卷：campus_appsmith_stacks（Appsmith 已下线，仅为不丢数据保留）'
    }
    exit $code
}

# --- 删卷：二次确认 ---
Write-Host '即将删除下列数据卷（不可恢复）：' -ForegroundColor Red
Write-Host '  campus_pgdata            业务数据库（学生、异动、导入批次）'
Write-Host '  campus_uploads           上传的导入文件'
Write-Host '  campus_gateway_pgdata    网关认证库（RuoYi sys_* 表、账号、权限）'
Write-Host '  campus_gateway_redis     网关会话缓存'
Write-Host '  campus_appsmith_stacks   历史 Appsmith 元数据（已下线，删了不影响主栈）'
Write-Host ''
Write-Host '建议先备份：.\scripts\backup.sh' -ForegroundColor Yellow

if (-not $Force) {
    $answer = Read-Host '确认删除请输入 DELETE（大写）'
    if ($answer -cne 'DELETE') {
        Write-Status INFO '未确认，已取消。未做任何改动'
        exit 1
    }
}

$code = Invoke-Compose down -v
if ($code -eq 0) { Write-Status INFO '容器与数据卷已删除（裸库状态，up-main 后需重新初始化）' }
exit $code
