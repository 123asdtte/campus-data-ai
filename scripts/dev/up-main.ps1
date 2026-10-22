<#
.SYNOPSIS
    启动主系统（PostgreSQL + Appsmith + Import API）。

.DESCRIPTION
    依次完成：环境自检 → 补齐 .env（占位符自动生成随机密钥）→ 必要时拉取离线 wheel
    → compose up → 等待健康检查。Appsmith 首次启动慢（start_period 180s），
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
$envFile = Join-Path $repo '.env'
if (-not (Test-Path $envFile)) {
    Copy-Item (Join-Path $repo '.env.example') $envFile
    Write-Status INFO '.env 不存在，已从 .env.example 复制'
}
$envText = Get-Content $envFile -Raw
foreach ($key in 'POSTGRES_PASSWORD', 'APP_DB_PASSWORD', 'RO_DB_PASSWORD',
    'APPSMITH_ENCRYPTION_PASSWORD', 'APPSMITH_ENCRYPTION_SALT') {
    if ($envText -match "(?m)^$key=(__CHANGE_ME.*)?$") {
        $secret = New-RandomSecret
        $envText = $envText -replace "(?m)^$key=.*$", "$key=$secret"
        Write-Status INFO "$key 仍是占位符，已替换为随机 32 位密钥"
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
Write-Status INFO '等待健康检查（数据库与导入 API）...'
$dbOk = Wait-ContainerHealthy -Name 'campus-db' -TimeoutSeconds 180
if ($dbOk) { Write-Status PASS 'campus-db 健康' } else { Write-Status FAIL 'campus-db 未进入 healthy'; }

# 建最小权限角色（003 不在 initdb 里，缺了它 import-api 会崩溃重启）
if ($dbOk) {
    Write-Status INFO '执行 sql/003_roles.sql（建 campus_app / campus_ro）'
    if (Initialize-DbRoles) {
        Write-Status PASS '最小权限角色已就位'
        # 角色的密码若与 import-api 启动时缓存的连接不同，需重启一次让它重连
        $apiState = & docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' campus-import-api 2>$null
        if ($apiState -ne 'healthy') {
            Write-Status INFO 'import-api 尚未健康，重启一次让它用新角色重连'
            Invoke-Compose restart import-api | Out-Null
        }
    }
    else { Write-Status FAIL '003_roles.sql 执行失败，import-api 将无法连库' }
}

$apiOk = Wait-ContainerHealthy -Name 'campus-import-api' -TimeoutSeconds 240
if ($apiOk) { Write-Status PASS 'campus-import-api 健康' } else { Write-Status FAIL 'campus-import-api 未进入 healthy（看日志：docker compose logs import-api）' }

$appsmithOk = Wait-ContainerHealthy -Name 'campus-appsmith' -TimeoutSeconds 300
if ($appsmithOk) { Write-Status PASS 'campus-appsmith 健康' }
else { Write-Status WARN 'campus-appsmith 仍在启动（首次约 3-5 分钟），不影响导入链路' }

Write-Host ''
Write-Host '访问地址：' -ForegroundColor Cyan
Write-Host '  Import API   http://127.0.0.1:8010/docs'
Write-Host '  Appsmith     http://127.0.0.1:8081'
Write-Host '  PostgreSQL   127.0.0.1:55432'
Write-Host '下一步：.\scripts\dev\smoke-test.ps1'
exit $(if ($dbOk -and $apiOk) { 0 } else { 1 })
