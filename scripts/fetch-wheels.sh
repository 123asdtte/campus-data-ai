#!/usr/bin/env bash
# 下载 Import API 构建所需的 Linux wheel。
# 适用场景：容器无法直连 PyPI（本机实测外网被拒），需在宿主机预取后再构建镜像。
# 用法：./scripts/fetch-wheels.sh
set -euo pipefail

cd "$(dirname "$0")/../import-api"

PYTHON_BIN="${PYTHON:-python}"
INDEX="${PIP_INDEX_URL:-https://pypi.org/simple}"

echo "index: ${INDEX}"
"$PYTHON_BIN" -m pip download -r requirements.txt -d wheels \
  --only-binary=:all: \
  --platform manylinux2014_x86_64 \
  --platform manylinux_2_28_x86_64 \
  --platform manylinux_2_17_x86_64 \
  --python-version 312 --implementation cp --abi cp312 \
  --index-url "$INDEX"

# uvloop 带 sys_platform != "win32" 标记，在 Windows 宿主上会被依赖解析跳过，需单独拉取
"$PYTHON_BIN" -m pip download uvloop -d wheels \
  --only-binary=:all: \
  --platform manylinux2014_x86_64 \
  --platform manylinux_2_17_x86_64 \
  --python-version 312 --implementation cp --abi cp312 \
  --index-url "$INDEX" --no-deps

echo "wheel 数量: $(ls wheels/*.whl | wc -l)"
