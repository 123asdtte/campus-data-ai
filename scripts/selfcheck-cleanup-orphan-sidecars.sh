#!/usr/bin/env bash
# cleanup-orphan-sidecars.sh 的自检。
#
# 这个脚本删的是磁盘上的文件，而且判定逻辑有个很阴的反例
# （`ls "$stem."*` 会命中 sidecar 自己，导致一个孤儿都找不到），
# 所以给它配一套能在本机直接跑的回归检查，CI 也复用它。
#
# 用法：
#   ./scripts/selfcheck-cleanup-orphan-sidecars.sh
set -euo pipefail

cd "$(dirname "$0")/.."

SCRIPT="${SELFCHECK_TARGET:-scripts/cleanup-orphan-sidecars.sh}"
# 必须显式 -p /tmp：否则在 Git Bash 下 mktemp 会把 TMPDIR 展开成
# C:\Users\…\Temp/tmp.XXXX 这种混合分隔符的形式，后续 rm 会被工具链拦下。
FIXTURES="$(mktemp -d -p /tmp)"
trap 'rm -rf "$FIXTURES"' EXIT

FAILED=0
fail() { echo "FAIL: $*" >&2; FAILED=1; }

# 在造出来的临时目录里放一个文件（含子目录）
mk() { mkdir -p "$(dirname "$FIXTURES/$1")"; : > "$FIXTURES/$1"; }

# 造 6 个文件，覆盖 3 种情况：
#   A-1.xlsx          + A-1.mapping.json        → 在用，全程绝不能动
#   A-2.mapping.json                            → 孤儿
#   sub/B-1.csv.xlsx.mapping.json               → 孤儿，文件名里本来就带点号
#   sub/B-2.csv       + B-2.mapping.json        → 在用，且在子目录里
#   sub/C-3.mapping.json                        → 孤儿，且在子目录里
mk "A-1.xlsx"
mk "A-1.mapping.json"
mk "A-2.mapping.json"
mk "sub/B-1.csv.xlsx.mapping.json"
mk "sub/B-2.csv"
mk "sub/B-2.mapping.json"
mk "sub/C-3.mapping.json"

EXPECTED="$(LC_ALL=C sort <<EOF
$FIXTURES/A-2.mapping.json
$FIXTURES/sub/B-1.csv.xlsx.mapping.json
$FIXTURES/sub/C-3.mapping.json
EOF
)"

# ---- 1. dry-run 识别出的孤儿必须正好是这 3 个 ----
# 结尾的 || true 不能省：一个孤儿都没报时 grep 退出码是 1，
# 配上 set -e / pipefail 会让本脚本在这里直接静默死掉，
# 于是「什么都识别不出来」这个最该抓的故障反而测不出来。
GOT_DRY="$(
    bash "$SCRIPT" --path "$FIXTURES" |
        grep '^orphan: ' | sed 's/^orphan: //' | LC_ALL=C sort || true
)"

if [ "$GOT_DRY" != "$EXPECTED" ]; then
    fail "dry-run 结果不符。期望：
$EXPECTED
实际：
$GOT_DRY"
fi

# ---- 2. dry-run 不能删任何东西（含它自己报出来的那 3 个） ----
for f in "$FIXTURES/A-2.mapping.json" \
         "$FIXTURES/sub/B-1.csv.xlsx.mapping.json" \
         "$FIXTURES/sub/C-3.mapping.json"; do
    [ -e "$f" ] || fail "dry-run 竟然删了文件：$f"
done

# ---- 3. --apply 之后，孤儿没了 ----
bash "$SCRIPT" --path "$FIXTURES" --apply >/dev/null

for f in "$FIXTURES/A-2.mapping.json" \
         "$FIXTURES/sub/B-1.csv.xlsx.mapping.json" \
         "$FIXTURES/sub/C-3.mapping.json"; do
    [ -e "$f" ] && fail "--apply 没有删掉孤儿：$f"
done

# ---- 4. --apply 之后，在用的一个都不能少 ----
for f in "$FIXTURES/A-1.xlsx" \
         "$FIXTURES/A-1.mapping.json" \
         "$FIXTURES/sub/B-2.csv" \
         "$FIXTURES/sub/B-2.mapping.json"; do
    [ -e "$f" ] || fail "--apply 误删了在用的文件：$f"
done

# ---- 5. 清干净之后再扫，必须报「没有发现孤儿 sidecar」 ----
bash "$SCRIPT" --path "$FIXTURES" --apply >/dev/null
LEFT="$(bash "$SCRIPT" --path "$FIXTURES" | grep -c '^orphan: ' || true)"
[ "$LEFT" = "0" ] || fail "清空后仍报出 $LEFT 个孤儿"

if [ "$FAILED" -eq 0 ]; then
    echo "PASS：孤儿识别、dry-run 不删、--apply 只删孤儿 —— 5 项全过。"
else
    exit 1
fi
