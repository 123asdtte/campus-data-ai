<#
.SYNOPSIS
    启动前的环境自检：Docker、端口、.env、构建前置产物、磁盘。

.DESCRIPTION
    只做检查，不改任何东西。任何一项 FAIL 都会让退出码为 1，
    up-main.ps1 会先跑它，失败即停，避免带着缺口启动再出现难懂的报错。

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

# --- 2. 端口占用（主栈 55432/8010/8081/8443，前端 8082） ---
$ports = @{
    55432 = 'PostgreSQL'
    8010  = 'Import API'
    8081  = 'Appsmith(HTTP)'
    8443  = 'Appsmith(HTTPS)'
    8082  = '前端静态站'
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

# --- 3. .env 与必填项 ---
$envFile = Join-Path $repo '.env'
if (-not (Test-Path $envFile)) {
    Assert FAIL '.env 不存在：up-main.ps1 会从 .env.example 自动生成，也可先手动 cp .env.example .env'
}
else {
    Assert PASS '.env 已存在'
    $envText = Get-Content $envFile -Raw
    $required = @('POSTGRES_PASSWORD', 'APP_DB_PASSWORD', 'RO_DB_PASSWORD',
        'APPSMITH_ENCRYPTION_PASSWORD', 'APPSMITH_ENCRYPTION_SALT')
    foreach ($key in $required) {
        if ($envText -notmatch "(?m)^$key=") {
            Assert FAIL ".env 缺少 $key"
        }
        elseif ($envText -match "(?m)^$key=(__CHANGE_ME.*)?$") {
            Assert FAIL ".env 的 $key 仍是占位符，未填写"
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

# --- 5. 磁盘 ---
$drive = (Get-Item $repo).PSDrive.Name
$free = (Get-PSDrive $drive).Free / 1GB
if ($free -lt 10) { Assert FAIL ('磁盘剩余 {0:N1} GB，低于 10 GB（镜像+数据卷需要空间）' -f $free) }
else { Assert PASS ('磁盘剩余 {0:N1} GB' -f $free) }

Write-Host ''
Write-Host "结果：FAIL=$fail  WARN=$warn" -ForegroundColor $(if ($fail -gt 0) { 'Red' } else { 'Yellow' })
exit $(if ($fail -gt 0) { 1 } else { 0 })
