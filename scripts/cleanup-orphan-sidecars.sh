#!/usr/bin/env bash
# 清理孤儿 sidecar（.mapping.json）。
#
# 背景：D-1 修复前（PR #29 之前），提交只删暂存文件、不删同目录同名的
# .mapping.json，而这些文件在 import_batches.staged_path 置 NULL 后无法从库里
# 反查，只能扫盘。现在提交路径已改为同删（_remove_staged），本脚本只负责
# **存量**环境里已经留下的那批。
#
# 孤儿判定：sidecar 的名字是「暂存文件去掉扩展名 + .mapping.json」，
# 所以同名的暂存文件还在时，这个 sidecar **正在被使用**，绝不能删。
#
# 默认只打印不删除（dry-run），必须显式 --apply 才真的删。
#
# 用法：
#   ./scripts/cleanup-orphan-sidecars.sh                  # 扫容器内的 /data/uploads
#   ./scripts/cleanup-orphan-sidecars.sh --apply          # 真的删
#   ./scripts/cleanup-orphan-sidecars.sh --path /some/dir # 扫宿主机目录（非 Docker 部署）
set -euo pipefail

cd "$(dirname "$0")/.."

APPLY=0
TARGET=""
UPLOAD_DIR="${UPLOAD_DIR:-/data/uploads}"

while [ $# -gt 0 ]; do
    case "$1" in
        --apply) APPLY=1; shift ;;
        --path) TARGET="${2:?--path 需要一个目录}"; shift 2 ;;
        -h|--help)
            grep '^#   ' "$0" | sed 's/^#   //'
            exit 0
            ;;
        *) echo "未知参数：$1" >&2; exit 1 ;;
    esac
done

# 容器内是 python:3.12-slim，/bin/sh 是 dash，不支持 read -d，
# 所以用换行分隔 + POSIX 语法，一次 exec 完成扫描与删除。
# 注意不要写成 `ls "$stem."*`：那个通配符会命中 sidecar 自己，
# 于是每个 sidecar 都「看起来有伴」，一个孤儿都找不出来（实测踩过）。
# 必须逐个候选判断，并排除 .mapping.json 自身。
CONTAINER_SNIPPET='
find "$UPLOAD_DIR" -type f -name "*.mapping.json" | while read -r f; do
    stem="${f%.mapping.json}"
    has_staged=0
    for cand in "$stem".*; do
        [ -e "$cand" ] || continue
        case "$cand" in *.mapping.json) continue ;; esac
        has_staged=1
        break
    done
    [ "$has_staged" = "1" ] && continue
    if [ "$APPLY" = "1" ]; then
        rm -f "$f"
        echo "deleted: $f"
    else
        echo "orphan: $f"
    fi
done
'

run_in_container() {
    # 注意两点，都是实测踩出来的：
    #
    # 1. compose exec 认的是**服务名**（import-api），不是容器名
    #    （campus-import-api）。写容器名会直接报 no such service。
    #
    # 2. 在 Git Bash / MSYS 下跑时，MSYS 会把命令行里的 /data/uploads
    #    改写成 E:/…/PortableGit/data/uploads 再传给 docker.exe，
    #    容器里就变成查一个不存在的目录（find 报 No such file）。
    #    MSYS_NO_PATHCONV=1 关掉这个改写。Linux 上这个变量没有作用，
    #    留着无害。
    MSYS_NO_PATHCONV=1 docker compose exec -T import-api \
        env UPLOAD_DIR="$UPLOAD_DIR" APPLY="$APPLY" \
        sh -c "$CONTAINER_SNIPPET"
}

run_local() {
    find "$TARGET" -type f -name '*.mapping.json' -print0 2>/dev/null |
    while IFS= read -r -d '' f; do
        stem="${f%.mapping.json}"
        # 同名的暂存文件还在 → 这个 sidecar 正在被使用，跳过。
        # 不能只判断通配符有没有匹配：它一定会命中 sidecar 自己。
        has_staged=0
        for cand in "$stem".*; do
            [ -e "$cand" ] || continue
            case "$cand" in *.mapping.json) continue ;; esac
            has_staged=1
            break
        done
        if [ "$has_staged" -eq 1 ]; then
            continue
        fi
        if [ "$APPLY" -eq 1 ]; then
            rm -f "$f"
            echo "deleted: $f"
        else
            echo "orphan: $f"
        fi
    done
}

if [ -n "$TARGET" ]; then
    echo "扫描目录：$TARGET"
    OUTPUT="$(run_local)"
else
    echo "扫描容器 campus-import-api 的 $UPLOAD_DIR"
    OUTPUT="$(run_in_container || true)"
fi

if [ -z "$OUTPUT" ]; then
    echo "没有发现孤儿 sidecar。"
    exit 0
fi

echo "$OUTPUT"

COUNT=$(printf '%s\n' "$OUTPUT" | wc -l | tr -d ' ')
if [ "$APPLY" -eq 0 ]; then
    echo ""
    echo "共 $COUNT 个。上面是 dry-run，没有删除任何文件；确认后加 --apply 再跑一次。"
else
    echo ""
    echo "已删除 $COUNT 个孤儿 sidecar。"
fi
