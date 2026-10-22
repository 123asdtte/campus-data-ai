<#
.SYNOPSIS
    启动主系统（PostgreSQL + 网关认证库 + Redis + Java 网关 + Import API）。

.DESCRIPTION
    依次完成：环境自检 → 补齐 .env（占位符自动生成随机密钥）→ 必要时拉取离线 wheel
    → compose up → 等待健康检查 → 建最小权限角色并补齐 004/006。

    2026-10-22 对齐统一入口（PR-D 之后）：
      - Appsmith 已下线，不再等待 campus-appsmith；
      - 8010 宿主发布已移除，业务请求统一经网关 http://127.0.0.1:9190；
      - 网关需要 JWT_SECRET_KEY / GATEWAY_DB_PASSWORD / GATEWAY_REDIS_PASSWORD /
        INTERNAL_HMAC_SECRET，缺失时 compose 直接拒绝启动。

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
$envFile = Join-Path $repo '.env'
if (-not (Test-Path $envFile)) {
    Copy-Item (Join-Path $repo '.env.example') $envFile
    Write-Status INFO '.env 不存在，已从 .env.example 复制'
}
$envText = Get-Content $envFile -Raw
# 业务库两角色 + 网关认证库 / Redis / HMAC + Sa-Token JWT。
# 与 docker-compose.yml 的 ${VAR:?} 必填项保持一致；空值也视为未填写。
foreach ($key in 'POSTGRES_PASSWORD', 'APP_DB_PASSWORD', 'RO_DB_PASSWORD',
    'GATEWAY_DB_PASSWORD', 'GATEWAY_REDIS_PASSWORD',
    'INTERNAL_HMAC_SECRET', 'JWT_SECRET_KEY') {
    if ($envText -match "(?m)^$key=(__CHANGE_ME.*)?$") {
        $secret = New-RandomSecret
        $envText = $envText -replace "(?m)^$key=.*$", "$key=$secret"
        Write-Status INFO "$key 仍是占位符或空值，已替换为随机 32 位密钥"
    }
    elseif ($envText -notmatch "(?m)^$key=") {
        $secret = New-RandomSecret
        $envText = $envText.TrimEnd() + "`n$key=$secret`n"
        Write-Status INFO ".env 缺少 $key，已追加随机密钥"
    }
}
Set-Content -Path $envFile -Value $envText -Encoding UTF8 -NoNewline:$false

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
$code = Invoke-Compose @composeArgs
if ($code -ne 0) { Write-Status FAIL 'compose up 失败，见上方输出'; exit $code }

# --- 5. 等健康检查 ---
Write-Host ''
Write-Status INFO '等待健康检查（业务库、网关认证库、Redis、导入 API、网关）...'
$dbOk = Wait-ContainerHealthy -Name 'campus-db' -TimeoutSeconds 180
if ($dbOk) { Write-Status PASS 'campus-db 健康' } else { Write-Status FAIL 'campus-db 未进入 healthy'; }

# 建最小权限角色并补齐 004/006（003 不在 initdb 里，缺了它 import-api 会崩溃重启；
# 004 建 nonce 表，006 建导入范围与审计函数——两者都不在 initdb 中，必须显式重放）
$rolesOk = $false
if ($dbOk) {
    Write-Status INFO '执行 sql/003_roles.sql + 重放 004/006（建 campus_app / campus_ro、nonce、导入审计）'
    $rolesOk = Initialize-DbRoles
    if ($rolesOk) {
        Write-Status PASS '最小权限角色与 004/006 已就位'
        # 角色的密码若与 import-api 启动时缓存的连接不同，需重启一次让它重连
        $apiState = & docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' campus-import-api 2>$null
        if ($apiState -ne 'healthy') {
            Write-Status INFO 'import-api 尚未健康，重启一次让它用新角色重连'
            Invoke-Compose restart import-api | Out-Null
        }
    }
    else { Write-Status FAIL '003/004/006 执行失败，import-api 将无法连库或导入审计缺失' }
}

$apiOk = Wait-ContainerHealthy -Name 'campus-import-api' -TimeoutSeconds 240
if ($apiOk) { Write-Status PASS 'campus-import-api 健康' } else { Write-Status FAIL 'campus-import-api 未进入 healthy（看日志：docker compose logs import-api）' }

# 网关依赖认证库与 Redis；两者健康后网关才开始连库，超时窗口按网关启动期（start_period 60s）留足
$gwDbOk = Wait-ContainerHealthy -Name 'campus-gateway-db' -TimeoutSeconds 180
if ($gwDbOk) { Write-Status PASS 'campus-gateway-db 健康' } else { Write-Status FAIL 'campus-gateway-db 未进入 healthy' }

$gwRedisOk = Wait-ContainerHealthy -Name 'campus-gateway-redis' -TimeoutSeconds 120
if ($gwRedisOk) { Write-Status PASS 'campus-gateway-redis 健康' } else { Write-Status FAIL 'campus-gateway-redis 未进入 healthy' }

$gwOk = Wait-ContainerHealthy -Name 'campus-gateway' -TimeoutSeconds 300
if ($gwOk) { Write-Status PASS 'campus-gateway 健康' }
else {
    Write-Status FAIL 'campus-gateway 未进入 healthy（看日志：docker compose logs gateway；常见原因：JWT_SECRET_KEY 为空或认证库初始化失败）'
}

Write-Host ''
Write-Host '访问地址：' -ForegroundColor Cyan
Write-Host '  统一入口（网关）  http://127.0.0.1:9190    （前端经 nginx /gw 也走这里）'
Write-Host '  Import API        仅容器内 http://import-api:8000（宿主 8010 已关闭）'
Write-Host '  PostgreSQL        127.0.0.1:55432'
Write-Host '  网关认证库        127.0.0.1:55434'
Write-Host '  网关 Redis        127.0.0.1:6382'
Write-Host '  前端静态站        http://127.0.0.1:8082（需单独启动 docker-compose.web.yml）'
Write-Host '下一步：.\scripts\dev\smoke-test.ps1'
exit $(if ($dbOk -and $rolesOk -and $apiOk -and $gwOk) { 0 } else { 1 })
