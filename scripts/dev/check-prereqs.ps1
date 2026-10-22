<#
.SYNOPSIS
    启动前的环境自检：Docker、端口、.env、构建前置产物、磁盘。

.DESCRIPTION
    只做检查，不改任何东西。任何一项 FAIL 都会让退出码为 1，
    up-main.ps1 会先跑它，失败即停，避免带着缺口启动再出现难懂的报错。

    2026-10-22 对齐统一入口（PR-D 之后）：
      - 宿主不再发布 8010（import-api 只能经网关访问）；
      - Appsmith 已下线，改为检查网关相关端口；
      - 网关要求 JWT_SECRET_KEY / GATEWAY_DB_PASSWORD / GATEWAY_REDIS_PASSWORD /
        INTERNAL_HMAC_SECRET 全部非空（缺失时 compose 直接拒绝启动）。

.EXAMPLE
    .\scripts\dev\check-prereqs.ps1
#>
[CmdletBinding()]
param()

. (Join-Path $PSScriptRoot '_common.ps1')

$repo = Get-RepoRoot
$fail = 0
$warn = 0

function Assert([string]$Level, [string]$Message) {
    Write-Status $Level $Message
    if ($Level -eq 'FAIL') { $script:fail++ }
    if ($Level -eq 'WARN') { $script:warn++ }
}

Write-Host '=== 校园数据平台 环境自检 ===' -ForegroundColor Cyan
Write-Host "仓库根: $repo"

# --- 1. Docker 与守护进程 ---
$dockerCmd = Get-Command docker -ErrorAction SilentlyContinue
if (-not $dockerCmd) {
    Assert FAIL '未找到 docker 命令：请先安装 Docker Desktop（WSL2 后端）'
}
else {
    $server = & docker version --format '{{.Server.Version}}' 2>$null
    if ($LASTEXITCODE -eq 0 -and $server) {
        Assert PASS "Docker 引擎可用（Server $server）"
    }
    else {
        Assert FAIL 'docker 命令存在但连不上引擎：请确认 Docker Desktop 已启动且鲸鱼图标稳定'
    }
    $compose = & docker compose version 2>$null
    if ($LASTEXITCODE -eq 0) { Assert PASS "Compose 可用：$compose" }
    else { Assert FAIL 'docker compose 不可用' }
}

# --- 2. 端口占用 ---
# 主栈：业务库 55432；网关侧 55434（认证库）/ 6382（Redis）/ 9190（统一入口）；
# 前端独立编排（docker-compose.web.yml）：8082。
# 8010 / 8081 / 8443 不再属于本栈：8010 是已关闭的 import-api 直连口，
# 8081/8443 是已下线的 Appsmith。它们被占用不代表冲突，因此不再检查。
# 网关三件套只有构建出 ruoyi-admin jar 后才会启动；未构建时它们空闲属正常。
$ports = @{
    55432 = 'PostgreSQL 业务库'
    55434 = 'PostgreSQL 网关认证库（需网关 jar）'
    6382  = 'Redis 网关缓存（需网关 jar）'
    9190  = 'Java 网关（统一入口，需网关 jar）'
    8082  = '前端静态站（独立 compose）'
}
foreach ($p in ($ports.Keys | Sort-Object)) {
    $busy = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue
    if ($busy) {
        $owner = (Get-Process -Id $busy[0].OwningProcess -ErrorAction SilentlyContinue).ProcessName
        Assert WARN "端口 $p（$($ports[$p])）已被占用，占用进程：$owner —— 启动会失败，请先释放或修改端口映射"
    }
    else {
        Assert PASS "端口 $p（$($ports[$p])）空闲"
    }
}

# --- 3. .env 与必填项（以 .env.example 为准） ---
$envFile = Join-Path $repo '.env'
if (-not (Test-Path $envFile)) {
    Assert FAIL '.env 不存在：up-main.ps1 会从 .env.example 自动生成，也可先手动 cp .env.example .env'
}
else {
    $gaps = Get-EnvFileGaps
    if (-not $gaps.HasExample) {
        Assert FAIL '.env.example 不存在，无法判断 .env 是否齐全'
    }
    elseif (($gaps.Missing | Measure-Object).Count -eq 0 -and
            ($gaps.Placeholder | Measure-Object).Count -eq 0 -and
            ($gaps.Empty | Measure-Object).Count -eq 0) {
        Assert PASS '.env 与 .env.example 对齐：无缺失、无占位符、无空值'
    }
    else {
        foreach ($m in $gaps.Missing) {
            Assert FAIL ".env 缺少 $($m.Key)（.env.example 里有）——compose 会报 missing a value"
        }
        foreach ($k in $gaps.Placeholder) {
            Assert FAIL ".env 的 $k 仍是占位符，未填写"
        }
        foreach ($k in $gaps.Empty) {
            Assert FAIL ".env 的 $k 是空值——compose 把空值也算缺失，会报 missing a value"
        }
    }
}

# --- 4. 构建前置产物 ---
$wheels = @(Get-ChildItem (Join-Path $repo 'import-api/wheels') -Filter '*.whl' -ErrorAction SilentlyContinue)
if ($wheels.Count -eq 0) {
    Assert FAIL 'import-api/wheels 为空：容器无外网，构建会失败。请跑 scripts\fetch-wheels.sh，或让 up-main.ps1 自动拉取'
}
else {
    Assert PASS "离线 wheel 已就位（$($wheels.Count) 个）"
}

if (Test-Path (Join-Path $repo 'web/dist')) {
    Assert PASS 'web/dist 已构建'
}
else {
    Assert WARN 'web/dist 不存在：前端栈（docker-compose.web.yml）需要它，主栈不受影响'
}

# 网关镜像只 COPY 宿主构建好的 jar（gateway/Dockerfile），target/ 不入库。
# 没有 jar 时 up-main 只启动核心栈；要验证统一入口，先构建：
#   cd gateway; mvn -B -DskipTests -pl ruoyi-admin -am package
$gatewayJar = Join-Path $repo 'gateway/ruoyi-admin/target/ruoyi-admin.jar'
if (Test-Path $gatewayJar) {
    Assert PASS '网关 jar 已就绪：up-main 会一并启动网关（统一入口 9190）'
}
else {
    Assert WARN '网关 jar 不存在：up-main 只启动核心栈；需要统一入口时先构建 ruoyi-admin（见文档第 2 节）'
}

# --- 5. 磁盘 ---
$drive = (Get-Item $repo).PSDrive.Name
$free = (Get-PSDrive $drive).Free / 1GB
if ($free -lt 10) { Assert FAIL ('磁盘剩余 {0:N1} GB，低于 10 GB（镜像+数据卷需要空间）' -f $free) }
else { Assert PASS ('磁盘剩余 {0:N1} GB' -f $free) }

Write-Host ''
Write-Host "结果：FAIL=$fail  WARN=$warn" -ForegroundColor $(if ($fail -gt 0) { 'Red' } else { 'Yellow' })
exit $(if ($fail -gt 0) { 1 } else { 0 })
