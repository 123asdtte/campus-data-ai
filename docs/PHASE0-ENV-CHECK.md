# 阶段 0 环境检查报告

**执行时间：** 2026-10-20 15:13–16:00
**方式：** 只读检查 + 版本核验（GitHub / Docker Hub 官方接口）

---

## 1. 实测结果

| 检查项 | 实测值 | 判定 |
|---|---|---|
| Docker Engine | 29.2.0 | 可用 |
| Docker Compose | v5.0.2 | 可用 |
| 容器可用资源 | 24 vCPU / 15.5 GiB | 满足 Appsmith（2 vCPU/8 GB 建议）+ PostgreSQL + Import API |
| 宿主机 | Windows 11 家庭中文版，31.8 GB 内存 | 满足 |
| Docker 数据目录 | `F:\DockerData\docker`（`docker_data.vhdx` 19.8 GB） | **不在 C 盘**，符合要求 |
| 磁盘余量 | Z: 141.6 GB / F: 26.7 GB / C: 12.2 GB | 项目在 Z:，镜像与卷在 F:，C: 不承载数据 |
| 项目目录 | `Z:\ai\本地部署` 为空 | 无覆盖风险 |
| WSL 核验 | `wsl.exe` 被本机安全策略列入黑名单 | 无法核验发行版；Docker 正常运行，后端可用 |

## 2. 端口冲突与重排

原生默认端口在本机不可用：

| 端口 | 占用进程 | 处置 |
|---|---|---|
| 5432 | 宿主 PostgreSQL（PID 7000） | 业务库改为 **55432** |
| 8000 | 既有容器 `diet-gateway` | Import API 改为 **8010** |
| 8080 | `verge-mihomo`（代理） | 避开 80 段，Appsmith 改为 **8081 / 8443** |

最终端口：Appsmith `8081`→80、`8443`→443；PostgreSQL `55432`→5432；Import API `8010`→8000。全部绑定 `127.0.0.1`。

## 3. 磁盘处置

- 检查时 F 盘仅 27 GB 可用，Dify 全栈预计 9–12 GB，存在撑满风险。
- 执行 `docker builder prune -f`，回收构建缓存 **11.16 GB**（12.49 GB → 1.33 GB），未触碰运行中的镜像与容器。
- 说明：vhdx 为稀疏文件，回收后宿主 `df` 仍显示 27 GB，但容器内空间已释放；拉取 Appsmith（4.31 GB）后 vhdx 仅增长 0.1 GB，验证了这一点。
- **决策：不迁移数据目录。** 迁移需 GUI 操作并复制约 20 GB，收益不抵风险；F 盘余量足以支撑阶段 1，阶段 2 部署 Dify 前重新评估。
- 已设置日志上限（每容器 10 MB × 3）与磁盘检查脚本 `scripts/check-disk.sh`（<10 GB 告警，<5 GB 停止拉取与批量导入）。

## 4. 版本锁定

| 组件 | 版本 | 来源 |
|---|---|---|
| `postgres` | `16.15-alpine` | Docker Hub 实际可用标签（2026-09-21 发布） |
| `appsmith/appsmith-ce` | `v2.5.0` | Docker Hub 实际可用标签（2026-10-09 发布） |
| `python` | `3.12-slim` | 官方镜像 |
| pandas / pandera / fastapi / psycopg | 2.3.3 / 0.34.1 / 0.150.0 / 3.3.6 | 构建日志实测 |

均未使用 `latest`。

## 5. 构建环境限制（已解决）

容器**无外网出口**（PyPI、国内镜像均 `Connection refused`），但镜像拉取正常（走 Docker Desktop 代理）。

处置：在宿主机下载 `manylinux` wheel（37 个，41 MB）放入 `import-api/wheels/`，Dockerfile 优先离线安装，无 wheels 时回退 `PIP_INDEX_URL`。

注意：`uvicorn[standard]` 的 `uvloop` 带 `sys_platform != "win32"` 标记，在 Windows 宿主下载会被跳过，需单独指定 `--platform` 补下。

## 6. 阶段 0 结论

环境满足阶段 1 要求，无阻断项。唯一遗留为 WSL 发行版状态无法核验，因 Docker 全链路正常，不影响实施。
