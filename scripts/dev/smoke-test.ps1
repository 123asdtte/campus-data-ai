<#
.SYNOPSIS
    主系统冒烟测试：优先走统一入口（网关登录 + 签名代理），网关不可用时降级到容器内直连。

.DESCRIPTION
    全部使用虚构数据，不碰真实业务数据。提交成功后会打印学号，
    便于在 down → up 之后验证「数据还在」。

    两种模式：
      1. 网关模式（默认，推荐）：检测 http://127.0.0.1:9190/healthz。
         可用时走真实入口：POST /auth/login 取 token，再带 Authorization + clientid
         调 /internal/proxy/*（学生、筛选、总览、预览→校验→提交），
         并额外断言“无 token 被拒”“宿主 8010 不可达”。
      2. 容器模式（降级）：网关未启动（典型原因：没有 ruoyi-admin jar）。
         经由 `docker compose exec -T import-api python -` 在容器内直连
         127.0.0.1:8000；会显式提示“未覆盖统一入口”，避免把降级结果
         当成安全边界验证。此模式要求 INTERNAL_AUTH_ENABLED=false。

    为什么仍然保留 curl.exe：PS 5.1 的 Invoke-RestMethod 没有 -Form，
    且会走系统代理访问 127.0.0.1 被掐断；curl --noproxy '*' 可直连本机。

.PARAMETER BaseUrl
    网关地址，默认 http://127.0.0.1:9190（不带 /gw，/gw 是前端 nginx 的反代路径）。

.PARAMETER Username / Password
    登录账号，默认 admin / admin123（sql/005 开发夹具）。

.PARAMETER SkipCommit
    只做健康检查与预览，不真正写库。

.PARAMETER ForceContainer
    跳过网关检测，强制使用容器内直连模式（排查用）。

.EXAMPLE
    .\scripts\dev\smoke-test.ps1
#>
[CmdletBinding()]
param(
    [string]$BaseUrl = 'http://127.0.0.1:9190',
    [string]$Username = 'admin',
    [string]$Password = 'admin123',
    [switch]$SkipCommit,
    [switch]$ForceContainer
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

# 断言宿主 8010 不可达（PR-D 的安全边界）
function Test-Host8010Closed {
    $probe = Invoke-Curl @('-o', 'NUL', '--max-time', '3', 'http://127.0.0.1:8010/health/ready')
    return ($probe.Code -ne 0)
}

$curl = Get-Command curl.exe -ErrorAction SilentlyContinue
if (-not $curl) { Write-Status FAIL '未找到 curl.exe'; exit 1 }

# --- 0. 选择模式 ---
$gatewayReachable = $false
if (-not $ForceContainer) {
    $probe = Invoke-Curl @('--max-time', '3', "$BaseUrl/healthz")
    $gatewayReachable = ($probe.Code -eq 0 -and $probe.Output -match 'ok')
}

if ($gatewayReachable) {
    Write-Host "模式：网关（$BaseUrl）" -ForegroundColor Cyan
    # --- 1. 网关存活 ---
    Check $true "网关存活：/healthz -> ok"

    # --- 2. 登录 ---
    $loginBody = @{
        clientId = $ClientId
        grantType = 'password'
        username = $Username
        password = $Password
        tenantId = '000000'
    } | ConvertTo-Json -Compress
    $tmpBody = New-TemporaryFile
    # 显式写无 BOM 的 UTF-8：PS 5.1 的 Set-Content -Encoding UTF8 会带 BOM
    [System.IO.File]::WriteAllText($tmpBody, $loginBody, (New-Object System.Text.UTF8Encoding($false)))
    $loginRes = Invoke-Curl @('-X', 'POST', '-H', 'Content-Type: application/json', '-d', "@$tmpBody", "$BaseUrl/auth/login")
    Remove-Item $tmpBody -ErrorAction SilentlyContinue
    $login = Convert-JsonSafe $loginRes.Output
    if (-not $login -or $login.code -ne 200 -or -not $login.data.access_token) {
        Write-Status FAIL "登录失败：$($loginRes.Output)"
        Write-Status INFO '排查：.env 的 JWT_SECRET_KEY 是否非空；docker compose logs gateway 是否报 SaJwtException'
        exit 1
    }
    $script:token = $login.data.access_token
    Check ($script:token.Length -gt 20) "登录成功：$Username（token ${($script:token.Substring(0,12))}...）"

    # --- 3. 安全边界 ---
    $anon = Convert-JsonSafe (Invoke-Curl @("$BaseUrl/internal/proxy/students")).Output
    $anonDenied = (-not $anon) -or ($anon.code -and $anon.code -ne 200) -or (-not ($anon.PSObject.Properties.Name -contains 'items'))
    Check $anonDenied '无 token 访问 /internal/proxy/students 被拒绝'
    Check (Test-Host8010Closed) '宿主 8010 已关闭（import-api 只能经网关访问）'

    # --- 4. 只读接口 ---
    $filters = Convert-JsonSafe (Invoke-Gw 'GET' '/internal/proxy/meta/filters').Output
    Check ($null -ne $filters) 'GET /internal/proxy/meta/filters 可读'

    $overview = Convert-JsonSafe (Invoke-Gw 'GET' '/internal/proxy/stats/overview').Output
    Check ($overview -and $null -ne $overview.students_total) "GET /internal/proxy/stats/overview：学生总数 $($overview.students_total)"

    $studentsPage = Convert-JsonSafe (Invoke-Gw 'GET' '/internal/proxy/students').Output
    Check ($studentsPage -and $studentsPage.total -ge 0) "GET /internal/proxy/students：共 $($studentsPage.total) 条"

    # --- 5. 导入链路（经网关 multipart 转发） ---
    # 每次生成唯一学号的 CSV：固定样例第二次跑会全部命中 DUPLICATE_STUDENT_NO。
    $sample = Join-Path $env:TEMP ("campus_smoke_{0}.csv" -f (Get-Date -Format 'yyyyMMddHHmmss'))
    $stamp = Get-Date -Format 'MMddHHmmss'
    $lines = @('学号,姓名,学院,专业,班级,入学年份,在校状态')
    foreach ($i in 1..3) {
        $no = "SMK$stamp$('{0:D3}' -f $i)"
        $lines += "$no,冒烟测试$i,计算机学院,软件技术,软件2601,2026,在校"
    }
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
}
else {
    # --- 降级：容器内直连 ---
    Write-Host '模式：容器内直连（网关不可用）' -ForegroundColor Yellow
    Write-Status WARN '未检测到可用网关：本次不覆盖登录、HMAC 签名与统一入口；仅验证 FastAPI 自身链路'
    Write-Status WARN '该模式要求 INTERNAL_AUTH_ENABLED=false；要验证统一入口请先构建网关 jar 并运行 up-main.ps1'
    Check (Test-Host8010Closed) '宿主 8010 已关闭（import-api 只能经网关访问）'

    # 容器内客户端：stdlib + openpyxl（import-api 镜像自带，xlsx 解析依赖）。
    # 每步结果汇总成一个 JSON 行打印，PowerShell 侧只负责翻译成 PASS/FAIL。
    $clientScript = @'
import json, os, sys, uuid, urllib.request

BASE = "http://127.0.0.1:8000"
SKIP_COMMIT = os.environ.get("SKIP_COMMIT") == "1"
CANDIDATES = ["/app/samples/students_clean.xlsx", "/app/samples/test_acceptance.csv"]
steps = []


def step(name, ok, detail=""):
    steps.append({"name": name, "ok": bool(ok), "detail": detail})


def prepare_sample(path):
    """给学号加唯一前缀，让冒烟测试可以反复跑。返回 (临时文件, 前缀)。"""
    tag = "SMK" + uuid.uuid4().hex[:4].upper()
    if path.endswith(".xlsx"):
        from openpyxl import load_workbook
        workbook = load_workbook(path)
        sheet = workbook.active
        header = [cell.value for cell in sheet[1]]
        column = header.index("学号") + 1
        for row in range(2, sheet.max_row + 1):
            cell = sheet.cell(row=row, column=column)
            if cell.value:
                cell.value = "%s%s" % (tag, cell.value)
        target = "/tmp/smoke_%s.xlsx" % tag
        workbook.save(target)
        return target, tag
    import csv
    with open(path, newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.reader(handle))
    column = rows[0].index("学号")
    for row in rows[1:]:
        if len(row) > column and row[column]:
            row[column] = tag + row[column]
    target = "/tmp/smoke_%s.csv" % tag
    with open(target, "w", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerows(rows)
    return target, tag


def _call(req, timeout):
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get(path):
    return _call(urllib.request.Request(BASE + path, method="GET"), 60)


def post(path):
    return _call(urllib.request.Request(BASE + path, method="POST", data=b""), 120)


def upload(path, filepath, fields):
    boundary = uuid.uuid4().hex
    body = bytearray()
    for key, value in fields.items():
        body += (
            "--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n"
            % (boundary, key, value)
        ).encode()
    with open(filepath, "rb") as handle:
        content = handle.read()
    body += (
        "--%s\r\nContent-Disposition: form-data; name=\"file\"; filename=\"%s\"\r\n"
        "Content-Type: application/octet-stream\r\n\r\n"
        % (boundary, os.path.basename(filepath))
    ).encode()
    body += content
    body += ("\r\n--%s--\r\n" % boundary).encode()
    req = urllib.request.Request(BASE + path, data=bytes(body), method="POST")
    req.add_header("Content-Type", "multipart/form-data; boundary=%s" % boundary)
    return _call(req, 180)


def fatal(message):
    step("链路中断", False, message)
    print(json.dumps({"steps": steps}, ensure_ascii=False))
    sys.exit(0)


sample = next((p for p in CANDIDATES if os.path.exists(p)), None)
if sample is None:
    fatal("容器内找不到样例文件：%s" % ", ".join(CANDIDATES))
tag = ""
try:
    sample, tag = prepare_sample(sample)
except Exception as exc:
    fatal("准备样例失败：%r" % (exc,))

try:
    health = get("/health/ready")
    step("健康检查", health.get("status") in ("ok", "ready"),
         "status=%s database=%s" % (health.get("status"), health.get("database")))
except Exception as exc:
    fatal("健康检查失败：%r" % (exc,))

try:
    filters = get("/meta/filters")
    step("GET /meta/filters", isinstance(filters, (dict, list)), "字段数=%s" % len(filters))
except Exception as exc:
    step("GET /meta/filters", False, repr(exc))

try:
    overview = get("/stats/overview")
    step("GET /stats/overview", isinstance(overview, dict),
         "学生总数=%s" % overview.get("students_total"))
except Exception as exc:
    step("GET /stats/overview", False, repr(exc))

try:
    preview = upload("/imports/preview", sample, {"target_type": "students"})
    batch_id = preview.get("batch_id")
    step("预览", bool(batch_id and batch_id > 0),
         "batch_id=%s 行数=%s 样例=%s" % (batch_id, preview.get("total_rows"), sample))
except Exception as exc:
    fatal("预览失败：%r" % (exc,))

try:
    validate = post("/imports/%s/validate" % batch_id)
    step("校验", validate.get("valid_rows", 0) >= 1,
         "有效行 %s / 无效行 %s（错误 %s）"
         % (validate.get("valid_rows"), validate.get("invalid_rows"), validate.get("error_count")))
except Exception as exc:
    step("校验", False, repr(exc))
    print(json.dumps({"steps": steps, "batch_id": batch_id}, ensure_ascii=False))
    sys.exit(0)

if validate.get("valid_rows", 0) < 1 or SKIP_COMMIT:
    print(json.dumps({"steps": steps, "batch_id": batch_id}, ensure_ascii=False))
    sys.exit(0)

try:
    commit = post("/imports/%s/commit" % batch_id)
    step("提交", commit.get("inserted_rows", 0) >= 1, "写入 %s 行" % commit.get("inserted_rows"))
except Exception as exc:
    fatal("提交失败：%r" % (exc,))

try:
    students = get("/students?keyword=%s&page=1&page_size=5" % tag)
    items = students.get("items") or []
    if items:
        step("提交后可查", True, "学号 %s（共 %s 条）" % (items[0].get("student_no"), students.get("total")))
    else:
        step("提交后可查", False, "提交后查不到学生")
except Exception as exc:
    step("提交后可查", False, repr(exc))

print(json.dumps({"steps": steps, "batch_id": batch_id, "tag": tag}, ensure_ascii=False))
'@

    Push-Location $repo
    try {
        $skipFlag = if ($SkipCommit) { '1' } else { '0' }
        $raw = ($clientScript |
            & docker compose exec -T -e "SKIP_COMMIT=$skipFlag" import-api python -) -join "`n"
    }
    finally { Pop-Location }

    if (-not $raw) {
        Write-Status FAIL '容器内客户端没有输出：docker compose exec 失败或容器未运行'
        exit 1
    }
    $jsonLine = ($raw -split "`n" | Where-Object { $_.Trim().StartsWith('{') } | Select-Object -Last 1)
    $result = Convert-JsonSafe $jsonLine
    if (-not $result) {
        Write-Status FAIL '客户端输出不是合法 JSON：'
        $raw | Out-Host
        exit 1
    }
    foreach ($s in $result.steps) {
        Check $s.ok ("{0}：{1}" -f $s.name, $s.detail)
    }
    $detail = ($result.steps | Where-Object { $_.name -eq '提交后可查' -and $_.ok }).detail
    $studentNo = $null
    if ($detail -and $detail -match '学号\s+([A-Za-z0-9_-]+)') { $studentNo = $Matches[1] }
}

Write-Host ''
if ($studentNo) { Write-Host "记住这个学号，用于验证「停止→重启→数据还在」：$studentNo" -ForegroundColor Cyan }
Write-Host "结果：FAIL=$fail" -ForegroundColor $(if ($fail -gt 0) { 'Red' } else { 'Green' })
exit $(if ($fail -gt 0) { 1 } else { 0 })
