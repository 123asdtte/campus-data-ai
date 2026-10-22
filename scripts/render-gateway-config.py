#!/usr/bin/env python
"""渲染生产网关配置：替换 Maven 占位符，输出可挂载的 application-prod.yml。

背景：
- `application-prod.yml` 被 .gitignore 排除，且包含 `@monitor.username@` 等
  Maven 过滤占位符；直接挂载源文件会导致 Spring 解析 YAML 失败。
- 生产镜像使用 `-Pprod` 构建（不含 dev/prod 配置），运行时必须挂载一份
  “已过滤”的配置。

用法：
    GATEWAY_MONITOR_PASSWORD=<secret> python scripts/render-gateway-config.py \
        --source gateway/ruoyi-admin/src/main/resources/application-prod.yml \
        --output-dir runtime-config

行为：
- 只替换已知占位符；存在未知占位符时失败退出；
- 输出文件权限尽量设为 600（Windows 上忽略）；
- 不打印任何配置值。
"""
from __future__ import annotations

import argparse
import os
import pathlib
import re
import sys

PLACEHOLDER = re.compile(r"@([A-Za-z0-9_.-]+)@")


def main() -> int:
    parser = argparse.ArgumentParser(description="渲染生产网关配置")
    parser.add_argument(
        "--source",
        default="gateway/ruoyi-admin/src/main/resources/application-prod.yml",
        help="原始配置路径",
    )
    parser.add_argument("--output-dir", default="runtime-config", help="输出目录")
    args = parser.parse_args()

    source = pathlib.Path(args.source)
    if not source.exists():
        print(f"ERROR: 源配置不存在：{source}", file=sys.stderr)
        return 1

    values = {
        "monitor.username": os.environ.get("GATEWAY_MONITOR_USERNAME", "ruoyi"),
        "monitor.password": os.environ.get("GATEWAY_MONITOR_PASSWORD", ""),
    }
    missing = [key for key, value in values.items() if not value]
    if missing:
        print(f"ERROR: 缺少环境变量值：{', '.join(missing)}", file=sys.stderr)
        return 1

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in values:
            raise KeyError(key)
        return values[key]

    try:
        rendered = PLACEHOLDER.sub(replace, source.read_text(encoding="utf-8"))
    except KeyError as exc:
        print(f"ERROR: 未知占位符 @{exc.args[0]}@，请补充映射", file=sys.stderr)
        return 1

    remaining = PLACEHOLDER.findall(rendered)
    if remaining:
        print(f"ERROR: 仍有未替换占位符：{', '.join(sorted(set(remaining)))}", file=sys.stderr)
        return 1

    output_dir = pathlib.Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / source.name
    target.write_text(rendered, encoding="utf-8")
    try:
        os.chmod(target, 0o600)
    except OSError:
        pass

    print(f"written: {target} ({len(rendered)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
