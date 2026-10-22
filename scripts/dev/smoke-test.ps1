<#
.SYNOPSIS
    主系统冒烟测试：健康检查 + 只读接口 + 一次完整导入（预览→校验→提交）。

.DESCRIPTION
    全部使用 samples/ 下的虚构数据，不碰真实业务数据。
    提交成功后会打印学号，便于在 down → up 之后验证「数据还在」。

    请求为什么在**容器里**发，而不是宿主机 curl：PR-D 把 Import API 的
    127.0.0.1:8010 宿主发布移除了，业务请求统一经网关；而网关镜像要
    ruoyi-admin jar（issue #1），本机通常构建不出来。宿主机因此没有任何
    入口能碰到 import-api。好在 compose 把 ./samples 挂进了容器的
    /app/samples，容器内是 127.0.0.1:8000 自访问，所以用 Python（stdlib，
    无第三方依赖）从容器内把这条链路走一遍。

    curl.exe 那套老写法（含 --noproxy '*'）已不再适用，这里没有保留。

.PARAMETER SkipCommit
    只做健康检查与预览，不真正写库。

.EXAMPLE
    .\scripts\dev\smoke-test.ps1
#>
[CmdletBinding()]
param(
    [switch]$SkipCommit
)

. (Join-Path $PSScriptRoot '_common.ps1')
$repo = Get-RepoRoot
$fail = 0

function Check([bool]$Ok, [string]$Message) {
    if ($Ok) { Write-Status PASS $Message } else { Write-Status FAIL $Message; $script:fail++ }
}

# 容器内跑的客户端：stdlib only，从 /app/samples 取样例文件。
# 每步的结果汇总成一个 JSON 行打印出来，PowerShell 侧只负责翻译成 PASS/FAIL。
$clientScript = @'
import json, os, sys, uuid, urllib.request, urllib.error

BASE = "http://127.0.0.1:8000"
SKIP_COMMIT = os.environ.get("SKIP_COMMIT") == "1"
CANDIDATES = [
    "/app/samples/students_clean.xlsx",
    "/app/samples/test_acceptance.csv",
]

steps = []


def step(name, ok, detail=""):
    steps.append({"name": name, "ok": bool(ok), "detail": detail})


def prepare_sample(path):
    """给学号加唯一前缀，让冒烟测试可以反复跑。

    样例文件是固定的：第一次跑完学号就落库了，第二次会因为
    DUPLICATE_STUDENT_NO 被全部判成无效行。#3 验收只跑过一次冒烟，
    所以没暴露这个问题——而「反复可跑」正是日常自检的基本要求。
    """
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
        return target

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
    return target


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

try:
    sample = prepare_sample(sample)
except Exception as exc:  # noqa: BLE001
    fatal("准备样例失败：%r" % (exc,))

try:
    health = get("/health/ready")
    step(
        "健康检查",
        health.get("status") in ("ok", "ready"),
        "status=%s database=%s" % (health.get("status"), health.get("database")),
    )
except Exception as exc:  # noqa: BLE001 - 冒烟测试要把任何异常摊开给人看
    fatal("健康检查失败：%r" % (exc,))

try:
    filters = get("/meta/filters")
    step("GET /meta/filters", isinstance(filters, (dict, list)),
         "字段数=%s" % (len(filters) if hasattr(filters, "__len__") else "?"))
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
    step(
        "校验",
        validate.get("valid_rows", 0) >= 1,
        "有效行 %s / 无效行 %s（错误 %s）"
        % (
            validate.get("valid_rows"),
            validate.get("invalid_rows"),
            validate.get("error_count"),
        ),
    )
except Exception as exc:
    step("校验", False, repr(exc))
    print(json.dumps({"steps": steps, "batch_id": batch_id}, ensure_ascii=False))
    sys.exit(0)

if validate.get("valid_rows", 0) < 1:
    print(json.dumps({"steps": steps, "batch_id": batch_id}, ensure_ascii=False))
    sys.exit(0)

if SKIP_COMMIT:
    print(json.dumps({"steps": steps, "batch_id": batch_id}, ensure_ascii=False))
    sys.exit(0)

try:
    commit = post("/imports/%s/commit" % batch_id)
    step("提交", commit.get("inserted_rows", 0) >= 1,
         "写入 %s 行" % commit.get("inserted_rows"))
except Exception as exc:
    fatal("提交失败：%r" % (exc,))

try:
    students = get("/students?page=1&page_size=5")
    items = students.get("items") or []
    if items:
        step("提交后可查", True,
             "学号 %s（共 %s 条）" % (items[0].get("student_no"), students.get("total")))
    else:
        step("提交后可查", False, "提交后查不到学生")
except Exception as exc:
    step("提交后可查", False, repr(exc))

print(json.dumps({"steps": steps, "batch_id": batch_id}, ensure_ascii=False))
'@

Push-Location $repo
try {
    # -SkipCommit 经环境变量传给容器内的客户端。
    # 脚本走 stdin 进容器（python - ），避免 PowerShell 转义一整段 Python。
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
try { $result = $jsonLine | ConvertFrom-Json } catch { $result = $null }

if (-not $result) {
    Write-Status FAIL "客户端输出不是合法 JSON："
    $raw | Out-Host
    exit 1
}

foreach ($s in $result.steps) {
    Check $s.ok ("{0}：{1}" -f $s.name, $s.detail)
}

$studentNo = ($result.steps | Where-Object { $_.name -eq '提交后可查' -and $_.ok }).detail
# \S+ 会把后面的「（共」一起吞掉，学号只可能是字母数字和下划线，收紧一下。
if ($studentNo -and $studentNo -match '学号\s+([A-Za-z0-9_-]+)') {
    Write-Host ''
    Write-Host ("记住这个学号，用于验证「停止→重启→数据还在」：{0}" -f $Matches[1]) -ForegroundColor Cyan
}

Write-Host ''
Write-Host "结果：FAIL=$fail" -ForegroundColor $(if ($fail -gt 0) { 'Red' } else { 'Green' })
exit $(if ($fail -gt 0) { 1 } else { 0 })
