# TLS 开发模板与生产启用清单

- **状态**：模板已实现并在开发环境验证；**正式入口仍为 HTTP，未切换**
- **边界**：证书签发、域名、443 对外监听与流量切换属于 C 类，必须单独人工授权

## 1. 组件与文件

| 文件 | 作用 |
|---|---|
| `web/nginx.tls.conf` | 443 server 模板（TLS 1.2/1.3、证书路径、动态解析网关） |
| `web/nginx-common.conf` | HTTP/HTTPS 共用的业务 location（`/healthz`、`/gw/`、静态资源、SPA 回退） |
| `docker-compose.tls.yml` | 覆盖文件：只给 web 增加 8443→443 与证书挂载，保留原 80 |
| `scripts/gen-dev-cert.sh` | 生成 30 天自签名证书到 `certs/`（已被 `.gitignore` 忽略） |

## 2. 开发环境验证

```bash
# 1) 生成自签名证书（Git Bash 自带 openssl；已存在时需 --force 才覆盖）
./scripts/gen-dev-cert.sh

# 2) 重建前端镜像（nginx-common.conf 已打进镜像，构建期执行 nginx -t）并启用 8443
docker compose -p campus-web -f docker-compose.web.yml -f docker-compose.tls.yml up -d --build

# 3) 验证
curl -k --noproxy '*' https://127.0.0.1:8443/healthz
curl -k --noproxy '*' https://127.0.0.1:8443/gw/healthz
```

Windows PowerShell 下的完整冒烟：

```powershell
.\scripts\dev\smoke-test.ps1 -BaseUrl https://127.0.0.1:8443/gw -Insecure
```

`-Insecure` 只放行自签名证书，默认仍然校验证书。

## 3. 实测记录（2026-10-22）

| 步骤 | 结果 |
|---|---|
| `docker exec campus-web nginx -t` | syntax ok |
| `https://127.0.0.1:8443/healthz` | 200 |
| `https://127.0.0.1:8443/gw/healthz` | 200（TLS → nginx → 网关） |
| `http://127.0.0.1:8082/healthz` | 200（HTTP 与 TLS 并存） |
| 完整冒烟（登录 → 只读 → 预览 → 校验 → 提交 → 按学号检索） | `FAIL=0` |
| `scripts/preflight.py` | TLS 仍为 FAIL，但说明改为“模板已就绪，正式入口仍为 HTTP” |

## 4. 正式启用前必须完成（C 类）

1. **证书**：由受控 CA 签发（或学校统一证书），私钥只进入受控目录，禁止入库；
   配置自动续期与到期告警。
2. **域名与 DNS**：确定正式域名，解析指向入口；校内/校外访问范围需安全确认。
3. **监听与前置代理**：决定 TLS 终止在 `campus-web` 还是前置负载均衡；
   若在前置代理终止，需同步调整本模板与健康探针。
4. **80 → 443**：补跳转规则，避免明文入口长期并存；如必须保留 80，需明确原因。
5. **安全头**：按需增加 HSTS（确认全站 HTTPS 后再开）、`X-Content-Type-Options` 等。
6. **回归**：登录、学生、导入（含 multipart 大文件）、健康探针全部经 HTTPS 验证。
7. **切换与回退**：先灰度/双入口并行，保留快速回退到 80 的方案；切换需人工批准。

## 5. 回退

```bash
# 停用 TLS 覆盖，恢复 HTTP-only
docker compose -p campus-web -f docker-compose.web.yml up -d --force-recreate
```

证书与模板文件可保留，不影响未启用时的运行。
