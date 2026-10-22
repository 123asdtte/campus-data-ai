<#
.SYNOPSIS
    主系统冒烟测试：健康检查 + 只读接口 + 一次完整导入（预览→校验→提交）。

.DESCRIPTION
    全部使用 samples/ 下的虚构数据，不碰真实业务数据。
    提交成功后会打印学号，便于在 down → up 之后验证「数据还在」。

    统一用 curl.exe 而不是 Invoke-RestMethod，原因有两个（都实测过）：
      1) PowerShell 5.1 的 Invoke-RestMethod 没有 -Form，发 multipart 要手工拼；
      2) 它会走系统代理去访问 127.0.0.1，被中间层掐断（"基础连接已经关闭"）。
    curl 加 --noproxy '*' 可直连本机端口。

.PARAMETER BaseUrl
    Import API 地址，默认 http://127.0.0.1:8010。

.PARAMETER SkipCommit
    只做健康检查与预览，不真正写库。

.EXAMPLE
    .\scripts\dev\smoke-test.ps1
#>
[CmdletBinding()]
param(
    [string]$BaseUrl = 'http://127.0.0.1:8010',
    [switch]$SkipCommit
)

. (Join-Path $PSScriptRoot '_common.ps1')
$repo = Get-RepoRoot
$fail = 0

function Check([bool]$Ok, [string]$Message) {
    if ($Ok) { Write-Status PASS $Message } else { Write-Status FAIL $Message; $script:fail++ }
}

# curl 的多行输出在 PowerShell 里是字符串数组，直接喂 ConvertFrom-Json 会报
# “传入的数组无效”，必须先拼成单个字符串。
function Get-Json([string]$Url) {
    $raw = (& curl.exe -sS --noproxy '*' --max-time 20 $Url) -join "`n"
    if ($LASTEXITCODE -ne 0 -or -not $raw) { return $null }
    try { return ($raw | ConvertFrom-Json) } catch { return $null }
}

function Post-Json([string]$Url) {
    $raw = (& curl.exe -sS --noproxy '*' --max-time 60 -X POST $Url) -join "`n"
    if ($LASTEXITCODE -ne 0 -or -not $raw) { return $null }
    try { return ($raw | ConvertFrom-Json) } catch { return $null }
}

$curl = Get-Command curl.exe -ErrorAction SilentlyContinue
if (-not $curl) { Write-Status FAIL '未找到 curl.exe'; exit 1 }

Write-Host "BaseUrl: $BaseUrl" -ForegroundColor Cyan

# --- 1. 健康检查 ---
$health = Get-Json "$BaseUrl/health/ready"
if (-not $health) { Write-Status FAIL '健康检查失败：接口不可达'; exit 1 }
Check ($health.status -eq 'ok' -or $health.status -eq 'ready') "健康检查：status=$($health.status) database=$($health.database)"

# --- 2. 只读接口 ---
$filters = Get-Json "$BaseUrl/meta/filters"
Check ($null -ne $filters) 'GET /meta/filters 可读'
$overview = Get-Json "$BaseUrl/stats/overview"
Check ($null -ne $overview) "GET /stats/overview：学生总数 $($overview.students_total)"

# --- 3. 导入链路 ---
$sample = Join-Path $repo 'samples/students_clean.xlsx'
if (-not (Test-Path $sample)) { $sample = Join-Path $repo 'samples/test_acceptance.csv' }
Write-Status INFO "使用样例：$sample"

$rawPreview = (& curl.exe -sS --noproxy '*' --max-time 60 `
    -F "file=@$sample" -F 'target_type=students' "$BaseUrl/imports/preview") -join "`n"
if ($LASTEXITCODE -ne 0 -or -not $rawPreview) { Write-Status FAIL '预览请求失败'; exit 1 }
try { $preview = $rawPreview | ConvertFrom-Json } catch { $preview = $null }
if (-not $preview) { Write-Status FAIL '预览响应不是合法 JSON'; exit 1 }
Check ($preview.batch_id -gt 0) "预览成功：batch_id=$($preview.batch_id) 行数=$($preview.total_rows)"

$batchId = $preview.batch_id
$validate = Post-Json "$BaseUrl/imports/$batchId/validate"
if (-not $validate) { Write-Status FAIL '校验请求失败'; exit 1 }
Check ($validate.valid_rows -ge 1) "校验通过：有效行 $($validate.valid_rows) / 异常行 $($validate.error_rows)"

$studentNo = $null
if (-not $SkipCommit -and $validate.valid_rows -ge 1) {
    $commit = Post-Json "$BaseUrl/imports/$batchId/commit"
    if (-not $commit) { Write-Status FAIL '提交请求失败' }
    else {
        Check ($commit.inserted_rows -ge 1) "提交成功：写入 $($commit.inserted_rows) 行"
        $students = Get-Json "$BaseUrl/students?page=1&page_size=5"
        if ($students -and $students.items.Count -ge 1) {
            $studentNo = $students.items[0].student_no
            Check $true "可查到学生：$studentNo（共 $($students.total) 条）"
        }
        else { Write-Status FAIL '提交后查不到学生' }
    }
}

Write-Host ''
if ($studentNo) { Write-Host "记住这个学号，用于验证「停止→重启→数据还在」：$studentNo" -ForegroundColor Cyan }
Write-Host "结果：FAIL=$fail" -ForegroundColor $(if ($fail -gt 0) { 'Red' } else { 'Green' })
exit $(if ($fail -gt 0) { 1 } else { 0 })
