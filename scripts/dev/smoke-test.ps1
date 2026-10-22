<#
.SYNOPSIS
    统一入口冒烟测试：网关登录 + 只读接口 + 一次完整导入（预览→校验→提交）。

.DESCRIPTION
    全部使用 samples/ 下的虚构数据，不碰真实业务数据。
    提交成功后会打印学号，便于在 down → up 之后验证「数据还在」。

    2026-10-22 对齐统一入口（PR-D 之后）：
      - 宿主 8010 已关闭，所有业务请求必须经 Java 网关 http://127.0.0.1:9190；
      - 先 POST /auth/login 取 token，再带 Authorization + clientid 调 /internal/proxy/*；
      - 额外验证两条安全边界：无 token 被拒、宿主 8010 不可达。

    统一用 curl.exe 而不是 Invoke-RestMethod，原因有两个（都实测过）：
      1) PowerShell 5.1 的 Invoke-RestMethod 没有 -Form，发 multipart 要手工拼；
      2) 它会走系统代理去访问 127.0.0.1，被中间层掐断（"基础连接已经关闭"）。
    curl 加 --noproxy '*' 可直连本机端口。

.PARAMETER BaseUrl
    网关地址，默认 http://127.0.0.1:9190（不带 /gw 前缀，/gw 是前端 nginx 的反代路径）。

.PARAMETER Username / Password
    登录账号，默认 admin / admin123（sql/005 开发夹具）。

.PARAMETER SkipCommit
    只做健康检查与预览，不真正写库。

.EXAMPLE
    .\scripts\dev\smoke-test.ps1
#>
[CmdletBinding()]
param(
    [string]$BaseUrl = 'http://127.0.0.1:9190',
    [string]$Username = 'admin',
    [string]$Password = 'admin123',
    [switch]$SkipCommit
)

. (Join-Path $PSScriptRoot '_common.ps1')
$repo = Get-RepoRoot
$fail = 0
$token = $null

# 与 web/src/api/auth.ts 的 GW_CLIENT_ID 一致（sql/005 的 sys_client 种子）
$ClientId = 'e5cd7e4891bf95d1d19206ce24a7b32e'

function Check([bool]$Ok, [string]$Message) {
    if ($Ok) { Write-Status PASS $Message } else { Write-Status FAIL $Message; $script:fail++ }
}

# curl 的多行输出在 PowerShell 里是字符串数组，直接喂 ConvertFrom-Json 会报
# “传入的数组无效”，必须先拼成单个字符串。
function Invoke-Curl([string[]]$CurlArgs) {
    $raw = (& curl.exe -sS --noproxy '*' --max-time 60 @CurlArgs 2>&1) -join "`n"
    return @{ Output = $raw; Code = $LASTEXITCODE }
}

function Convert-JsonSafe([string]$Raw) {
    if (-not $Raw) { return $null }
    try { return ($Raw | ConvertFrom-Json) } catch { return $null }
}

# 带登录凭据调用网关业务接口（/internal/proxy/*）
function Invoke-Gw([string]$Method, [string]$Path, [string[]]$Extra = @()) {
    $args = @(
        '-X', $Method,
        '-H', "Authorization: Bearer $script:token",
        '-H', "clientid: $ClientId"
    ) + $Extra + @("$BaseUrl$Path")
    return Invoke-Curl $args
}

$curl = Get-Command curl.exe -ErrorAction SilentlyContinue
if (-not $curl) { Write-Status FAIL '未找到 curl.exe'; exit 1 }

Write-Host "BaseUrl: $BaseUrl" -ForegroundColor Cyan

# --- 1. 网关存活（公开探针，不需要登录） ---
# /healthz 返回纯文本 ok；某些网关版本返回 JSON，两种都接受
$healthRaw = (Invoke-Curl @("$BaseUrl/healthz")).Output
Check ($healthRaw -match 'ok') "网关存活：/healthz -> $($healthRaw.Trim())"

# --- 2. 登录 ---
$loginBody = @{
    clientId = $ClientId
    grantType = 'password'
    username = $Username
    password = $Password
    tenantId = '000000'
} | ConvertTo-Json -Compress
$tmp = New-TemporaryFile
# 显式写无 BOM 的 UTF-8：PS 5.1 的 Set-Content -Encoding UTF8 会带 BOM
[System.IO.File]::WriteAllText($tmp, $loginBody, (New-Object System.Text.UTF8Encoding($false)))
$loginRes = Invoke-Curl @('-X', 'POST', '-H', 'Content-Type: application/json', '-d', "@$tmp", "$BaseUrl/auth/login")
Remove-Item $tmp -ErrorAction SilentlyContinue
$login = Convert-JsonSafe $loginRes.Output
if (-not $login -or $login.code -ne 200 -or -not $login.data.access_token) {
    Write-Status FAIL "登录失败：$($loginRes.Output)"
    Write-Status INFO '排查：.env 的 JWT_SECRET_KEY 是否非空；docker compose logs gateway 是否报 SaJwtException'
    exit 1
}
$script:token = $login.data.access_token
Check ($script:token.Length -gt 20) "登录成功：$Username（token ${($script:token.Substring(0,12))}...）"

# --- 3. 安全边界：无 token 必须被拒；宿主 8010 不可达 ---
$anon = Convert-JsonSafe (Invoke-Curl @("$BaseUrl/internal/proxy/students")).Output
$anonDenied = (-not $anon) -or ($anon.code -and $anon.code -ne 200) -or (-not ($anon.PSObject.Properties.Name -contains 'items'))
Check $anonDenied '无 token 访问 /internal/proxy/students 被拒绝'

$probe8010 = Invoke-Curl @('-o', 'NUL', '--max-time', '3', 'http://127.0.0.1:8010/health/ready')
Check ($probe8010.Code -ne 0) '宿主 8010 已关闭（import-api 只能经网关访问）'

# --- 4. 只读接口 ---
$filters = Convert-JsonSafe (Invoke-Gw 'GET' '/internal/proxy/meta/filters').Output
Check ($null -ne $filters) 'GET /internal/proxy/meta/filters 可读'

$overview = Convert-JsonSafe (Invoke-Gw 'GET' '/internal/proxy/stats/overview').Output
Check ($overview -and $null -ne $overview.students_total) "GET /internal/proxy/stats/overview：学生总数 $($overview.students_total)"

$studentsPage = Convert-JsonSafe (Invoke-Gw 'GET' '/internal/proxy/students').Output
Check ($studentsPage -and $studentsPage.total -ge 0) "GET /internal/proxy/students：共 $($studentsPage.total) 条"

# --- 5. 导入链路（经网关 multipart 转发） ---
# 每次生成唯一学号的 CSV：samples/students_clean.xlsx 用的是固定学号，
# 第二次跑会全部命中 DUPLICATE_STUDENT_NO，冒烟测试就失去意义。
$sample = Join-Path $env:TEMP ("campus_smoke_{0}.csv" -f (Get-Date -Format 'yyyyMMddHHmmss'))
$stamp = Get-Date -Format 'MMddHHmmss'
$lines = @('学号,姓名,学院,专业,班级,入学年份,在校状态')
foreach ($i in 1..3) {
    $no = "SMK$stamp$('{0:D3}' -f $i)"
    $lines += "$no,冒烟测试$i,计算机学院,软件技术,软件2601,2026,在校"
}
# 无 BOM 的 UTF-8：BOM 会被 CSV 解析器当成第一个表头的一部分
[System.IO.File]::WriteAllLines($sample, $lines, (New-Object System.Text.UTF8Encoding($false)))
Write-Status INFO "使用本次生成的样例：$sample（学号前缀 SMK$stamp）"

$previewRes = Invoke-Gw 'POST' '/internal/proxy/imports/preview' @(
    '-F', "file=@$sample",
    '-F', 'target_type=students'
)
$preview = Convert-JsonSafe $previewRes.Output
if (-not $preview -or -not $preview.batch_id) {
    Write-Status FAIL "预览失败：$($previewRes.Output)"
    Remove-Item $sample -ErrorAction SilentlyContinue
    exit 1
}
Check ($preview.batch_id -gt 0) "预览成功：batch_id=$($preview.batch_id) 行数=$($preview.total_rows)"

$batchId = $preview.batch_id
$validate = Convert-JsonSafe (Invoke-Gw 'POST' "/internal/proxy/imports/$batchId/validate").Output
if (-not $validate) {
    Remove-Item $sample -ErrorAction SilentlyContinue
    Write-Status FAIL '校验请求失败'
    exit 1
}
Check ($validate.valid_rows -ge 1) "校验通过：有效行 $($validate.valid_rows) / 异常行 $($validate.invalid_rows)"

$studentNo = $null
if (-not $SkipCommit -and $validate.valid_rows -ge 1) {
    $commit = Convert-JsonSafe (Invoke-Gw 'POST' "/internal/proxy/imports/$batchId/commit").Output
    if (-not $commit) { Write-Status FAIL '提交请求失败' }
    else {
        Check ($commit.inserted_rows -ge 1) "提交成功：写入 $($commit.inserted_rows) 行"
        $found = Convert-JsonSafe (Invoke-Gw 'GET' "/internal/proxy/students?keyword=SMK$stamp").Output
        if ($found -and $found.items.Count -ge 3) {
            $studentNo = $found.items[0].student_no
            Check $true "可查到本次导入的学生：$($found.items[0].student_no)（匹配 $($found.total) 条）"
        }
        else { Write-Status FAIL '提交后查不到本次导入的学生' }
    }
}

Remove-Item $sample -ErrorAction SilentlyContinue

Write-Host ''
if ($studentNo) { Write-Host "记住这个学号，用于验证「停止→重启→数据还在」：$studentNo" -ForegroundColor Cyan }
Write-Host "结果：FAIL=$fail" -ForegroundColor $(if ($fail -gt 0) { 'Red' } else { 'Green' })
exit $(if ($fail -gt 0) { 1 } else { 0 })
