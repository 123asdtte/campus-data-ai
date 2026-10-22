<#
.SYNOPSIS
    启动主系统（PostgreSQL + Import API；网关 jar 存在时一并启动统一入口）。

.DESCRIPTION
    依次完成：环境自检 → 对齐 .env（以 .env.example 为准）→ 必要时拉取离线 wheel
    → compose up → 等待健康检查 → 补齐迁移 003 → 004 → 006。

    网关是否启动由 jar 决定（gateway/Dockerfile 只 COPY 宿主构建产物）：
      - gateway/ruoyi-admin/target/ruoyi-admin.jar 存在 → 启动
        campus-gateway-db / campus-gateway-redis / campus-gateway，并等待 healthy；
      - 不存在 → 只启动 campus-db + import-api，并提示构建命令。
    这样全新检出无需 JDK/Maven 也能先把核心栈跑起来，而具备 jar 的机器
    会自动恢复完整拓扑（统一入口 9190）。

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
# check-prereqs 对「.env 缺失 / wheels 为空 / 网关 jar 缺失」只判 WARN 或由本脚本补齐，
# 因此这里不因它退出，继续走自动补齐流程。
Write-Host ''

# --- 2. 对齐 .env ---
# 以 .env.example 为准，缺的键补上、密钥类空值与占位符填实；已有值不动。
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
# 必须点名服务，不能直接 compose up：Appsmith 已按 R2 下线（点名会报 no such service），
# 而网关镜像只 COPY 宿主构建好的 jar（target/ 不入库），没有 jar 时连带构建会失败。
$gatewayJar = Join-Path $repo 'gateway/ruoyi-admin/target/ruoyi-admin.jar'
$withGateway = Test-Path $gatewayJar
$composeArgs = @('up', '-d')
if (-not $NoBuild) { $composeArgs += '--build' }
$composeArgs += @('campus-db', 'import-api')
if ($withGateway) {
    $composeArgs += @('gateway-db', 'gateway-redis', 'gateway')
    Write-Status INFO '检测到 ruoyi-admin jar：将一并启动网关（统一入口 9190）'
}
else {
    Write-Status WARN '未检测到 ruoyi-admin jar：本次只启动核心栈。需要统一入口时先执行：'
    Write-Host '         cd gateway; mvn -B -DskipTests -pl ruoyi-admin -am package' -ForegroundColor DarkGray
}
$code = Invoke-Compose @composeArgs
if ($code -ne 0) { Write-Status FAIL 'compose up 失败，见上方输出'; exit $code }

# --- 5. 等健康检查 ---
Write-Host ''
Write-Status INFO '等待健康检查（业务库、导入 API；启用网关时另含认证库/Redis/网关）...'
$dbOk = Wait-ContainerHealthy -Name 'campus-db' -TimeoutSeconds 180
if ($dbOk) { Write-Status PASS 'campus-db 健康' } else { Write-Status FAIL 'campus-db 未进入 healthy'; }

# 补齐 initdb 不管的迁移（003/004/006 都不在 initdb 里）
$rolesOk = $false
if ($dbOk) {
    Write-Status INFO '执行迁移 003 → 004 → 006'
    $rolesOk = Initialize-DbRoles
    if ($rolesOk) {
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

$gwOk = $true
if ($withGateway) {
    # 网关依赖认证库与 Redis；两者健康后网关才开始连库，超时窗口按 start_period 60s 留足
    $gwDbOk = Wait-ContainerHealthy -Name 'campus-gateway-db' -TimeoutSeconds 180
    if ($gwDbOk) { Write-Status PASS 'campus-gateway-db 健康' } else { Write-Status FAIL 'campus-gateway-db 未进入 healthy'; $gwOk = $false }

    $gwRedisOk = Wait-ContainerHealthy -Name 'campus-gateway-redis' -TimeoutSeconds 120
    if ($gwRedisOk) { Write-Status PASS 'campus-gateway-redis 健康' } else { Write-Status FAIL 'campus-gateway-redis 未进入 healthy'; $gwOk = $false }

    $gwHealthy = Wait-ContainerHealthy -Name 'campus-gateway' -TimeoutSeconds 300
    if ($gwHealthy) { Write-Status PASS 'campus-gateway 健康' }
    else {
        Write-Status FAIL 'campus-gateway 未进入 healthy（看日志：docker compose logs gateway；常见原因：JWT_SECRET_KEY 为空或认证库初始化失败）'
        $gwOk = $false
    }
}

Write-Host ''
Write-Host '访问地址：' -ForegroundColor Cyan
if ($withGateway) {
    Write-Host '  统一入口（网关）  http://127.0.0.1:9190    （前端经 nginx /gw 也走这里）'
}
else {
    Write-Host '  统一入口（网关）  未启动（缺 ruoyi-admin jar）'
}
Write-Host '  Import API        仅容器内 http://import-api:8000（宿主 8010 已关闭）'
Write-Host '  PostgreSQL        127.0.0.1:55432'
Write-Host '  网关认证库        127.0.0.1:55434（仅启用网关时）'
Write-Host '  网关 Redis        127.0.0.1:6382（仅启用网关时）'
Write-Host '  前端静态站        http://127.0.0.1:8082（需单独启动 docker-compose.web.yml）'
Write-Host '下一步：.\scripts\dev\smoke-test.ps1'
exit $(if ($dbOk -and $rolesOk -and $apiOk -and $gwOk) { 0 } else { 1 })
