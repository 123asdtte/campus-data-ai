<#
.SYNOPSIS
    启动主系统（PostgreSQL + Appsmith + Import API）。

.DESCRIPTION
    依次完成：环境自检 → 对齐 .env（以 .env.example 为准，缺键补、空值填）→
    必要时拉取离线 wheel → compose up（只起主系统三个服务）→ 等待健康检查 →
    补齐迁移 003/004/006。Appsmith 首次启动慢（start_period 180s），
    超过等待窗口只报 WARN，不阻断——它不参与导入链路。

.PARAMETER SkipWheels
    跳过 wheel 拉取（已有 wheels 或你自行处理时使用）。

.PARAMETER NoBuild
    只启动，不重新构建镜像。

.EXAMPLE
    .\scripts\dev\up-main.ps1
#>
[CmdletBinding()]
param(
    [switch]$SkipWheels,
    [switch]$NoBuild
)

. (Join-Path $PSScriptRoot '_common.ps1')
$repo = Get-RepoRoot

# --- 1. 前置检查 ---
& (Join-Path $PSScriptRoot 'check-prereqs.ps1')
# check-prereqs 对「.env 缺失 / wheels 为空」判 FAIL，这两项本脚本会自动补齐，
# 因此这里只看退出码是否为「除了这两项之外还有问题」：直接尝试补齐后再自检一次。
Write-Host ''

# --- 2. 补齐 .env ---
# 以 .env.example 为准，缺的键补上、空值与占位符填实；已有值不动。
# 详见 _common.ps1 里 Sync-EnvFile 的注释。
Sync-EnvFile

# --- 3. 离线 wheel ---
$wheelDir = Join-Path $repo 'import-api/wheels'
$wheels = @(Get-ChildItem $wheelDir -Filter '*.whl' -ErrorAction SilentlyContinue)
if ($wheels.Count -eq 0 -and -not $SkipWheels) {
    $py = Find-Python
    if (-not $py) {
        Write-Status FAIL '未找到 python，无法拉取 wheel：请安装 Python 或改用 bash 跑 scripts/fetch-wheels.sh'
        exit 1
    }
    Write-Status INFO "wheels 为空，用 $py 拉取（约 1-3 分钟）"
    Push-Location (Join-Path $repo 'import-api')
    try {
        & $py -m pip download -r requirements.txt -d wheels `
            --only-binary=:all: `
            --platform manylinux2014_x86_64 --platform manylinux_2_28_x86_64 --platform manylinux_2_17_x86_64 `
            --python-version 312 --implementation cp --abi cp312
        # uvloop 带 sys_platform 标记，在 Windows 宿主上会被依赖解析跳过，需单独拉
        & $py -m pip download uvloop -d wheels --only-binary=:all: `
            --platform manylinux2014_x86_64 --platform manylinux_2_17_x86_64 `
            --python-version 312 --implementation cp --abi cp312 --no-deps
    }
    finally { Pop-Location }
}

# --- 4. 启动 ---
$composeArgs = @('up', '-d')
if (-not $NoBuild) { $composeArgs += '--build' }
# 必须点名服务，不能直接 compose up。两个原因，都是实测撞过的：
# 1. 网关（gateway / gateway-db / gateway-redis）要从
#    ruoyi-admin/target/ruoyi-admin.jar 构建，而 RuoYi 源码还没入库（issue #1），
#    不点名就会连带构建网关，然后整个 up 一起失败：
#        COPY ruoyi-admin/target/ruoyi-admin.jar: not found
# 2. Appsmith 已按 R2 路线图下线（服务定义从 compose 里删了，数据卷保留），
#    点名它会直接报 no such service。
# 主系统只剩这两个：PostgreSQL + Import API。
$composeArgs += @('campus-db', 'import-api')
$code = Invoke-Compose @composeArgs
if ($code -ne 0) { Write-Status FAIL 'compose up 失败，见上方输出'; exit $code }

# --- 5. 等健康检查 ---
Write-Host ''
Write-Status INFO '等待健康检查（数据库与导入 API）...'
$dbOk = Wait-ContainerHealthy -Name 'campus-db' -TimeoutSeconds 180
if ($dbOk) { Write-Status PASS 'campus-db 健康' } else { Write-Status FAIL 'campus-db 未进入 healthy'; }

# 补齐 initdb 不管的迁移（003/004/006 都不在 initdb 里）
if ($dbOk) {
    Write-Status INFO '执行迁移 003 → 004 → 006'
    if (Initialize-DbRoles) {
        Write-Status PASS '迁移已就位'
        # 角色的密码若与 import-api 启动时缓存的连接不同，需重启一次让它重连
        $apiState = & docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' campus-import-api 2>$null
        if ($apiState -ne 'healthy') {
            Write-Status INFO 'import-api 尚未健康，重启一次让它用新角色重连'
            Invoke-Compose restart import-api | Out-Null
        }
    }
    else { Write-Status FAIL '迁移执行失败：003 缺了 import-api 连不了库，006 缺了校验/提交会 500' }
}

$apiOk = Wait-ContainerHealthy -Name 'campus-import-api' -TimeoutSeconds 240
if ($apiOk) { Write-Status PASS 'campus-import-api 健康' } else { Write-Status FAIL 'campus-import-api 未进入 healthy（看日志：docker compose logs import-api）' }

Write-Host ''
Write-Host '访问地址：' -ForegroundColor Cyan
Write-Host '  PostgreSQL   127.0.0.1:55432'
Write-Host '  Import API   无宿主端口（PR-D 起统一走网关；容器内 127.0.0.1:8000）'
Write-Host '  Java 网关    127.0.0.1:9190（需要 ruoyi-admin jar，issue #1）'
Write-Host '  campus-web   127.0.0.1:8082（前端栈需单独启动）'
Write-Host ''
Write-Host 'Appsmith 已按 R2 下线，主栈不再包含它。' -ForegroundColor DarkGray
Write-Host '下一步：.\scripts\dev\smoke-test.ps1（在容器内跑完整导入链路）'
exit $(if ($dbOk -and $apiOk) { 0 } else { 1 })
