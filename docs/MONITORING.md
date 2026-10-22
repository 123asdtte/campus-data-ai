# 监控最小集（可用性）

- **状态**：已实现并在开发环境验证（2026-10-22）
- **目标**：用最少的组件回答一个问题——“服务还活着吗？”；不做全量指标平台。
- **组件**：Prometheus + blackbox-exporter + Alertmanager（profile `monitoring`，默认不启动）
- **端口**：Prometheus `127.0.0.1:9090`，Alertmanager `127.0.0.1:9093`；blackbox 不发布宿主端口

## 1. 为什么选这三个

| 方案 | 取舍 |
|---|---|
| **Prometheus + blackbox + Alertmanager**（采用） | 单机足够、配置可审计、无外部依赖；blackbox 从容器网络内部探测，不依赖宿主端口；规则与告警生命周期可验证 |
| Grafana | 展示更好，但需要额外镜像、数据源与面板维护；Prometheus 自带查询/告警页已能验证最小集，暂不引入 |
| Loki / ELK | 解决日志检索，不是可用性监控；等有真实排障需求再加 |
| 云监控 / SaaS | 需要外网与凭据，且会把运行数据带出本机；不作为默认方案 |

## 2. 被监控的入口

| 目标 | 地址（容器网络内） | 说明 |
|---|---|---|
| 统一入口 | `http://gateway:9180/healthz` | 网关进程存活；不依赖 DB/Redis |
| 业务服务 | `http://import-api:8000/health/ready` | 进程 + 数据库可用 |
| 前端 | `http://web:80/healthz` | nginx 存活 |

> 探测在容器网络内进行，因此“宿主端口未发布”不会被误判为服务故障；
> 宿主侧的真实路径由 `scripts/preflight.py` 的 `/gw/healthz` 检查覆盖。

## 3. 启动与停止

```bash
# 启动（三个容器）
docker compose --profile monitoring up -d prometheus alertmanager blackbox-exporter

# 查看
curl --noproxy '*' http://127.0.0.1:9090/-/healthy
curl --noproxy '*' http://127.0.0.1:9093/-/healthy

# 停止（数据卷保留）
docker compose --profile monitoring stop prometheus alertmanager blackbox-exporter
```

`up-main.ps1` 不自动启动监控，避免把约 150MB 镜像与常驻内存加到每台开发机；
需要时显式执行上面的命令。

## 4. 告警规则

规则文件：`monitoring/prometheus/rules/campus.yml`

| 告警 | 表达式 | for | 级别 |
|---|---|---|---|
| `CampusEndpointDown` | `probe_success == 0` | 1m | critical |
| `CampusTargetDown` | `up == 0` | 2m | warning |
| `CampusProbeSlow` | `probe_duration_seconds > 2` | 5m | warning |

`for: 1m` 约等于连续 4 次抓取失败（15s 间隔），避免容器重启抖动误报。

## 5. 告警去向（当前限制）

`monitoring/alertmanager/alertmanager.yml` 的 `default` receiver **没有任何投递渠道**：
告警只出现在 Prometheus `/alerts` 与 Alertmanager UI（`http://127.0.0.1:9093`）。

这是有意的最小集：仓库里不放 webhook 地址、邮箱密码或企业微信凭据。
正式部署必须补上真实 receiver，并由运维确认值班人与响应时限；凭据应通过
挂载 secrets 文件或环境变量注入，不得提交到仓库。

## 6. 验证记录（2026-10-22 实测）

| 步骤 | 结果 |
|---|---|
| `promtool check config` | SUCCESS，1 个规则文件 |
| `promtool check rules` | SUCCESS，3 条规则 |
| `amtool check-config` | SUCCESS，1 个 receiver |
| `/api/v1/targets` | 4 个 target 全部 `up`（prometheus + 3 个 HTTP 探测） |
| `probe_success` | 三个入口全部为 `1` |
| **故障演练**：`docker stop campus-import-api` | 约 75s 后 `CampusEndpointDown` 进入 `firing`，Alertmanager 收到 `active` 告警 |
| **恢复**：`docker start campus-import-api` | 约 75s 后告警解除，`/api/v1/alerts` 为空 |
| `scripts/preflight.py` | “监控组件” PASS（运行中），FAIL 从 3 降到 **2**（仅剩 TLS 与 dev jar 配置） |

## 7. 排查

| 现象 | 处理 |
|---|---|
| 容器起不来、日志 `no such file` | 确认 `monitoring/` 三个目录被正确挂载（相对仓库根） |
| Prometheus target `down` | 在 `campus-prometheus` 容器内 `wget -qO- http://gateway:9180/healthz` 验证网络；确认 `campus-net` |
| 告警不触发 | 看 `/api/v1/rules` 的 `lastEvaluation`；确认 `for` 时长已过 |
| 告警不消失 | 恢复后需等一个 `for` 周期；`probe_success` 回到 1 后自动 resolve |
| 镜像拉取失败 | 本机镜像加速器不可用时，可从可达的 registry 拉取后 `docker load`，或导入离线镜像包 |
