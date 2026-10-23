#!/usr/bin/env python
"""渲染 Alertmanager 配置：按环境变量决定是否启用 webhook 投递。

背景：
- 仓库内的 `monitoring/alertmanager/alertmanager.yml` 使用空 receiver，
  告警只在 UI 中可见，不会通知任何人；
- 真实 webhook 地址通常含 token，不能提交到仓库；
- 与网关生产配置一样，采用“仓库内模板 + 运行时渲染到 runtime-config/”的方式。

用法：
    ALERT_WEBHOOK_URL=https://example.invalid/alerts \
        python scripts/render-alertmanager-config.py

行为：
- 未设置 ALERT_WEBHOOK_URL：生成空 receiver（与仓库默认一致）；
- 设置后：生成 webhook receiver，send_resolved=true；
- 只接受 http/https；不打印 URL（避免 token 进入日志）；
- 输出文件权限尽量设为 600，目录 700（Windows 上忽略 chmod）。
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import urllib.parse

OUTPUT = pathlib.Path("runtime-config/alertmanager.yml")


def build_null() -> str:
    return """route:
  receiver: default
  group_by: [alertname, instance]
  group_wait: 10s
  group_interval: 1m
  repeat_interval: 4h

receivers:
  - name: default
    # 未配置 ALERT_WEBHOOK_URL：告警可见但不外发
"""


def build_webhook(url: str) -> str:
    # json.dumps 生成带引号的 YAML 标量，避免 URL 中的特殊字符破坏配置
    quoted = json.dumps(url)
    return f"""route:
  receiver: default
  group_by: [alertname, instance]
  group_wait: 10s
  group_interval: 1m
  repeat_interval: 4h

receivers:
  - name: default
    webhook_configs:
      - url: {quoted}
        send_resolved: true
"""


def main() -> int:
    url = os.environ.get("ALERT_WEBHOOK_URL", "").strip()
    if url:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            print("ERROR: ALERT_WEBHOOK_URL 必须是 http(s) 地址", file=sys.stderr)
            return 1
        content = build_webhook(url)
        mode = "webhook"
    else:
        content = build_null()
        mode = "null"

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(content, encoding="utf-8")
    try:
        os.chmod(OUTPUT.parent, 0o700)
        os.chmod(OUTPUT, 0o600)
    except OSError:
        pass

    print(f"written: {OUTPUT} ({len(content)} bytes, receiver={mode})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
