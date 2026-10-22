#!/usr/bin/env bash
# 生成开发用自签名证书（仅供本地/隔离环境验证 TLS 模板）
#
# 输出：certs/server.crt + certs/server.key（certs/ 已在 .gitignore 中）
# 用法：./scripts/gen-dev-cert.sh [输出目录]
#
# 安全边界：
#   - 私钥只留在本机，禁止提交、禁止用于正式环境；
#   - 正式证书必须由受控 CA 签发，部署与切换属于 C 类人工授权事项。
set -euo pipefail

OUT="${1:-certs}"

if ! command -v openssl >/dev/null 2>&1; then
  echo "未找到 openssl：请使用 Git Bash（自带 openssl）或在 WSL 中执行" >&2
  exit 1
fi

mkdir -p "$OUT"

# -addext 需要 OpenSSL 1.1.1+；Git for Windows 自带版本满足
openssl req -x509 -nodes -newkey rsa:2048 -days 30 \
  -keyout "$OUT/server.key" \
  -out "$OUT/server.crt" \
  -subj "/CN=localhost" \
  -addext "subjectAltName=DNS:localhost,IP:127.0.0.1" >/dev/null 2>&1

chmod 600 "$OUT/server.key"
echo "已生成开发证书：$OUT/server.crt（30 天有效，仅限本地验证）"
