#!/usr/bin/env bash
# 下载 Import API 构建所需的 Linux wheel。
# 适用场景：容器无法直连 PyPI（本机实测外网被拒），需在宿主机预取后再构建镜像。
# 用法：./scripts/fetch-wheels.sh
#       WITH_DEV=1 ./scripts/fetch-wheels.sh   # 额外下载 pytest/httpx（跑测试用，不进运行镜像）
set -euo pipefail

cd "$(dirname "$0")/../import-api"

PYTHON_BIN="${PYTHON:-python}"
INDEX="${PIP_INDEX_URL:-https://pypi.org/simple}"
# 运行镜像只需要 requirements.txt；测试依赖按需额外下载，避免把 pytest 带进生产镜像
REQ_FILE="requirements.txt"
if [ "${WITH_DEV:-0}" = "1" ]; then
  REQ_FILE="requirements-dev.txt"
  echo "包含开发与测试依赖"
fi

echo "index: ${INDEX}"
echo "requirements: ${REQ_FILE}"
"$PYTHON_BIN" -m pip download -r "$REQ_FILE" -d wheels \
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
