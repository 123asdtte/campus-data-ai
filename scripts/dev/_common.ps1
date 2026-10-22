# 公共辅助：仓库根定位、状态输出、compose 调用、随机密钥生成。
# 被 scripts/dev 下其它脚本点名加载，不单独执行。

$script:RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path

# 让 native 命令（curl / docker / psql）的 UTF-8 输出按 UTF-8 解码。
# 不设置的话 Windows PowerShell 5.1 会按系统 ANSI（GBK）解码，
# 接口返回的中文会变成乱码，ConvertFrom-Json 也会跟着失败。
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# 另一条独立的坑，管的是反方向——把字符串**喂给** native 命令时用的编码
# 是 $OutputEncoding，PS 5.1 默认 ASCII，中文会直接变成问号。
# （把 Python 脚本管道给 `docker compose exec ... python -` 时踩到：
#  脚本里的「学号」变成「??」，openpyxl 报 '??' is not list。）
# Console::OutputEncoding 只管显示，救不了这一路。
$OutputEncoding = [System.Text.Encoding]::UTF8

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
    # -Encoding UTF8 不能省，见下面 Get-EnvFileGaps 里的说明。
    foreach ($line in (Get-Content $Path -Encoding UTF8)) {
        if ($line -match '^\s*#') { continue }
        if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') {
            $map[$Matches[1]] = $Matches[2].Trim().Trim('"')
        }
    }
    return $map
}

# 以 .env.example 为准，算出当前 .env 还差什么。
#
# 为什么以 .env.example 为准，而不是写死一份「已知键」清单：
# compose 文件里加了新服务（gateway 就是这么进来的）之后，已经存在的 .env
# 里没有那些变量，docker compose 会直接报
#     error while interpolating services.gateway.environment.X:
#     required variable X is missing a value
# 整个栈起不来，而报错指向 compose 文件，极容易被误判成 compose 写错了。
# 写死清单跟不上 compose 的改动——gateway 那四个变量就是这么漏掉的。
#
# 另外 compose 的「取不到就报错」语法把**空值**也算缺失，所以空值和缺键
# 必须同等看待，否则 .env 里明明写着 INTERNAL_HMAC_SECRET= 却照样起不来。
#
# 还有个更阴的：本仓库的文件都是 UTF-8，而 PowerShell 5.1 的 Get-Content
# 默认按系统 ANSI（GBK）解码。UTF-8 里一个汉字是三字节，末尾那个字节如果
# 落在 0x81-0xFE（很常见），GBK 解码器会把它当成双字节字符的**前导字节**，
# 顺手把紧跟其后的换行符 \n 当后半个字节吃掉 —— 于是那一行和下一行被合并。
# 后果：KEEP_UPLOAD_FILES 明明写在 .env.example 里，却因为前一行是中文注释
# 而被并进那行，行首锚点 ^KEY= 匹配不上，被判成「不存在」。实测 .env.example
# 45 行，默认解码只剩 40 行。所以读数一律显式 -Encoding UTF8。
function Get-EnvFileGaps {
    $envPath = Join-Path $script:RepoRoot '.env'
    $examplePath = Join-Path $script:RepoRoot '.env.example'

    $gaps = [pscustomobject]@{
        Exists      = $false
        HasExample  = (Test-Path $examplePath)
        Missing     = @()
        Placeholder = @()
        Empty       = @()
    }
    if (-not $gaps.HasExample) { return $gaps }
    if (-not (Test-Path $envPath)) { return $gaps }

    $current = Read-EnvFile $envPath
    foreach ($line in (Get-Content $examplePath -Encoding UTF8)) {
        if ($line -notmatch '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') { continue }
        $key = $Matches[1]
        # 取值口径必须和 Read-EnvFile 一致（同样去引号），否则 .env.example 里
        # 写成 KEY="__CHANGE_ME__" 时，这里会因为开头是引号而匹配不上占位符，
        # 把占位符连引号一起抄进 .env。
        $exampleValue = $Matches[2].Trim().Trim('"')
        if (-not $current.ContainsKey($key)) {
            $gaps.Missing += [pscustomobject]@{ Key = $key; ExampleValue = $exampleValue }
            continue
        }
        if ($current[$key] -eq '') { $gaps.Empty += $key; continue }
        if ($current[$key] -match '^__CHANGE_ME') { $gaps.Placeholder += $key }
    }
    $gaps.Exists = $true
    return $gaps
}
function Sync-EnvFile {
    $envPath = Join-Path $script:RepoRoot '.env'
    $examplePath = Join-Path $script:RepoRoot '.env.example'

    if (-not (Test-Path $examplePath)) {
        Write-Status FAIL "找不到 $examplePath，无法对齐 .env"
        return
    }
    if (-not (Test-Path $envPath)) {
        Copy-Item $examplePath $envPath
        Write-Status INFO '.env 不存在，已从 .env.example 复制'
    }

    $gaps = Get-EnvFileGaps
    $gapCount = ($gaps.Missing | Measure-Object).Count +
                ($gaps.Placeholder | Measure-Object).Count +
                ($gaps.Empty | Measure-Object).Count
    if ($gapCount -eq 0) { return }

    $lines = New-Object System.Collections.Generic.List[string]
    foreach ($l in (Get-Content $envPath -Encoding UTF8)) { $lines.Add($l) }

    # 占位符一律换成随机密钥——.env.example 的约定就是「__CHANGE_ME_* 表示
    # 这里需要一个随机值」。空值则要分情况，不能一律随机：
    #   - 密钥类（名字里带 PASSWORD/SECRET/SALT/TOKEN/KEY）必须填实，因为
    #     compose 的 ${VAR:?} 把空值也算缺失（INTERNAL_HMAC_SECRET 就是如此）；
    #   - 其它键留空往往是有意义的（开关没配、可选参数没填），填成随机串会
    #     把语义搞坏（比如 KEEP_UPLOAD_FILES 变成 32 位随机字符串）。
    $toFill = @{}
    foreach ($k in $gaps.Placeholder) { $toFill[$k] = $true }
    foreach ($k in $gaps.Empty) {
        if ($k -match '(?i)(PASSWORD|SECRET|SALT|TOKEN|KEY)') { $toFill[$k] = $true }
    }
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=') {
            if ($toFill.ContainsKey($Matches[1])) {
                $lines[$i] = "$($Matches[1])=$(New-RandomSecret)"
            }
        }
    }

    # 缺的键追加到末尾。.env.example 里已经给了具体值的（比如 GATEWAY_DB_NAME）
    # 照抄；是占位符或（密钥类）空值的，才生成随机密钥。
    foreach ($m in $gaps.Missing) {
        $needSecret = ($m.ExampleValue -match '^__CHANGE_ME') -or
                      ($m.ExampleValue -eq '' -and $m.Key -match '(?i)(PASSWORD|SECRET|SALT|TOKEN|KEY)')
        if ($needSecret) {
            $value = New-RandomSecret
        }
        else {
            $value = $m.ExampleValue
        }
        $lines.Add("$($m.Key)=$value")
        Write-Status INFO ".env 缺少 $($m.Key)（.env.example 里有，手上这份是旧版），已补上"
    }
    foreach ($k in $gaps.Placeholder) {
        Write-Status INFO ".env 的 $k 还是占位符，已替换为随机密钥"
    }
    foreach ($k in $gaps.Empty) {
        if ($toFill.ContainsKey($k)) {
            Write-Status INFO ".env 的 $k 是空值（密钥类，compose 把空值也算缺失），已填实"
        }
        else {
            Write-Status INFO ".env 的 $k 是空值，按 .env.example 保持留空（非密钥类，不填随机值）"
        }
    }

    # 不能用 Set-Content -Encoding UTF8：PowerShell 5.1 那样写会带 BOM，
    # 让 .env 的第一个键变成「<BOM>KEY」。compose 自己能忍，dotenv 之类
    # 的工具会直接读不出来，所以按无 BOM 写。
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($envPath, (($lines -join "`n") + "`n"), $utf8NoBom)
}

# 补齐 initdb 不负责的迁移：003 → 004 → 006（与 CI 的顺序一致）。
#
# 必须做这一步的原因：docker-compose.yml 只把 001/002 挂进 initdb，
# 003 需要 psql 变量（app_password / ro_password），不在容器初始化里执行。
# 不跑它，import-api 会一直「password authentication failed for user
# campus_app」并崩溃重启。
#
# 004 与 006 同样必须在这里跑，而且它们是**当前主干代码的硬依赖**，不是可选项：
# 006 建的 campus.clear_import_issues() / campus.record_import_issues()
# 是受控删除导入明细用的 SECURITY DEFINER 函数，service.py 在校验与提交时
# 直接调用。缺 006 的话，预览能过、一进「校验 / 提交」就 500：
#     function campus.clear_import_issues(...) does not exist
# 004 是内部请求认证的 nonce 表。两者都不需要 psql 变量、都可重复执行。
# 顺序必须是 003 → 004 → 006：后两个都要用到 003 建的 campus_app。
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

    $steps = @(
        @{ Name = '003_roles.sql'; Vars = @{ app_password = $app; ro_password = $ro } },
        @{ Name = '004_internal_auth.sql'; Vars = @{} },
        @{ Name = '006_import_scope.sql'; Vars = @{} }
    )

    Push-Location $script:RepoRoot
    try {
        foreach ($step in $steps) {
            $path = Join-Path $script:RepoRoot "sql/$($step.Name)"
            if (-not (Test-Path $path)) {
                Write-Status FAIL "找不到 sql/$($step.Name)"
                return $false
            }
            # -Encoding UTF8 必须带上：不然 003 里那条以「。」结尾的中文注释
            # 会把下一行的 GRANT DELETE 吞进 -- 注释里，语句静默不执行。
            $sql = Get-Content $path -Raw -Encoding UTF8
            $psqlArgs = @('exec', '-T', 'campus-db', 'psql',
                '-U', $user, '-d', $db, '-v', 'ON_ERROR_STOP=1')
            foreach ($k in $step.Vars.Keys) {
                $psqlArgs += @('-v', "$k=$($step.Vars[$k])")
            }
            $psqlArgs += @('-f', '/dev/stdin')

            # 先把输出收下再判退出码，别把 psql 的正常输出当返回值。
            $output = ($sql | & docker compose @psqlArgs 2>&1) |
                ForEach-Object { $_.ToString() }
            $code = $LASTEXITCODE
            if ($code -ne 0) {
                $output | Out-Host
                Write-Status FAIL "sql/$($step.Name) 执行失败"
                return $false
            }
            Write-Status PASS "sql/$($step.Name) 已执行"
        }
        return $true
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
