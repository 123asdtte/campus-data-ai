# 公共辅助：仓库根定位、状态输出、compose 调用、随机密钥生成。
# 被 scripts/dev 下其它脚本点名加载，不单独执行。

$script:RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path

# 让 native 命令（curl / docker / psql）的 UTF-8 输出按 UTF-8 解码。
# 不设置的话 Windows PowerShell 5.1 会按系统 ANSI（GBK）解码，
# 接口返回的中文会变成乱码，ConvertFrom-Json 也会跟着失败。
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

function Get-RepoRoot {
    return $script:RepoRoot
}

function Write-Status {
    param(
        [ValidateSet('PASS', 'WARN', 'FAIL', 'INFO')]
        [string]$Level,
        [string]$Message
    )
    $color = switch ($Level) {
        'PASS' { 'Green' }
        'WARN' { 'Yellow' }
        'FAIL' { 'Red' }
        default { 'Gray' }
    }
    Write-Host ("[{0,-4}] {1}" -f $Level, $Message) -ForegroundColor $color
}

function Invoke-Compose {
    param(
        [Parameter(ValueFromRemainingArguments = $true)]
        [string[]]$ComposeArgs
    )
    Push-Location $script:RepoRoot
    try {
        # 必须先收下 docker 的输出再取退出码：直接 return $LASTEXITCODE 会把
        # 终端输出一起当作返回值，调用方拿到的就是数组而不是退出码（实测踩过）。
        # 2>&1 会把 stderr 变成 ErrorRecord，回显时渲染成红色报错。
        # 统一转成字符串，避免把 compose 的正常进度误显示成错误。
        $output = & docker compose @ComposeArgs 2>&1 | ForEach-Object { $_.ToString() }
        $code = $LASTEXITCODE
        $output | Out-Host
        return $code
    }
    finally {
        Pop-Location
    }
}

# 生成 32 位字母数字密钥（占位符替换用，避免新同事手工想密码）
function New-RandomSecret {
    param([int]$Length = 32)
    $bytes = New-Object 'byte[]' ($Length * 2)
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    $raw = [Convert]::ToBase64String($bytes) -replace '[^A-Za-z0-9]', ''
    return $raw.Substring(0, [Math]::Min($Length, $raw.Length))
}

# 找可用的 python（fetch wheels 需要）。优先环境变量，其次常见命令名。
function Find-Python {
    if ($env:PYTHON) { return $env:PYTHON }
    foreach ($cmd in 'python', 'python3', 'py') {
        $found = Get-Command $cmd -ErrorAction SilentlyContinue
        if ($found) { return $found.Source }
    }
    return $null
}

# 读取 .env 成哈希表（只认 KEY=VALUE，忽略注释与空行）
function Read-EnvFile {
    param([string]$Path)
    $map = @{}
    if (-not (Test-Path $Path)) { return $map }
    foreach ($line in (Get-Content $Path)) {
        if ($line -match '^\s*#') { continue }
        if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') {
            $map[$Matches[1]] = $Matches[2].Trim().Trim('"')
        }
    }
    return $map
}

# 建最小权限角色。
# 必须做这一步的原因：docker-compose.yml 只把 001/002 挂进 initdb，
# 003_roles.sql 需要 psql 变量（app_password / ro_password），
# 不在容器初始化里执行。不跑它，import-api 会一直
# 「password authentication failed for user campus_app」并崩溃重启。
# 003 本身幂等（CREATE 带 WHERE NOT EXISTS + ALTER），重复执行安全。
function Initialize-DbRoles {
    $envMap = Read-EnvFile (Join-Path $script:RepoRoot '.env')
    $user = $envMap['POSTGRES_USER']
    $db = $envMap['POSTGRES_DB']
    $app = $envMap['APP_DB_PASSWORD']
    $ro = $envMap['RO_DB_PASSWORD']
    if (-not $user -or -not $db -or -not $app -or -not $ro) {
        Write-Status FAIL '.env 缺少 POSTGRES_USER / POSTGRES_DB / APP_DB_PASSWORD / RO_DB_PASSWORD'
        return $false
    }
    $sqlPath = Join-Path $script:RepoRoot 'sql/003_roles.sql'
    if (-not (Test-Path $sqlPath)) { Write-Status FAIL "找不到 $sqlPath"; return $false }

    Push-Location $script:RepoRoot
    try {
        $sql = Get-Content $sqlPath -Raw
        $sql | & docker compose exec -T campus-db psql -U $user -d $db `
            -v ON_ERROR_STOP=1 -v app_password=$app -v ro_password=$ro -f /dev/stdin 2>&1 | Out-Null
        return ($LASTEXITCODE -eq 0)
    }
    finally { Pop-Location }
}

# 等待容器进入 healthy；超时返回 $false（不抛异常，交给调用方决定）
function Wait-ContainerHealthy {
    param(
        [string]$Name,
        [int]$TimeoutSeconds = 240
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $status = & docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' $Name 2>$null
        if ($LASTEXITCODE -eq 0 -and $status -eq 'healthy') { return $true }
        Start-Sleep -Seconds 5
    }
    return $false
}
