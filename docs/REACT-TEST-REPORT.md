# React 前端：测试结果

**执行时间：** 2026-10-20 16:20–16:55
**范围：** 工程骨架、学生查询页、数据导入页
**环境：** Node 22.22.2 / npm 10.9.7 / Vite 6.4.4 / React 18.3.1 / antd 5

结果按四类分开列，不合并表述。

---

## 一、已通过

| # | 项目 | 方法 | 结果 |
|---|---|---|---|
| 1 | TypeScript 严格检查 | `npm run build` 中的 `tsc --noEmit` | 通过，0 error（`strict`、`noUnusedLocals` 均开启） |
| 2 | 生产构建 | `vite build` | 通过，3035 modules，`dist/index.html` 0.41 kB、JS 1180.59 kB（gzip 372 kB） |
| 3 | 开发服务器 | `npm run dev` | 监听 127.0.0.1:5173，返回 HTML 200 |
| 4 | 接口代理 | `curl http://127.0.0.1:5173/api/students` | 200，正确转发到 8010 并返回 JSON |
| 5 | 学生列表默认分页 | `GET /students?page=1&page_size=5` | 200，total=220，items=5 |
| 6 | 关键词搜索 | `GET /students?keyword=何` | 200，total=10，首行「何明」 |
| 7 | 学院筛选 | `GET /students?college=计算机学院` | 200，total=40，返回行全部为该学院 |
| 8 | 翻页 | `GET /students?page=2&page_size=5` | 200，page=2，首行学号 `DEMO2021010072` |
| 9 | 学生不存在的错误 | `GET /students/NOT_EXIST_404` | 404，`detail=学生不存在：NOT_EXIST_404` |
| 10 | 筛选项聚合 | `GET /meta/filters` | 200，学院 6 个、班级 16 个、在校 220 |
| 11 | 导入预览 | `POST /imports/preview-base64`（15 行样例） | 200，batch=12，rows=15 |
| 12 | 导入校验 | `POST /imports/12/validate` | 200，有效 10 / 异常 5，命中 4 类代码 |
| 13 | 导入提交 | `POST /imports/12/commit` | 200，写入 10 条，排除 5 条 |
| 14 | 重复提交保护 | 再次 `commit` | 409，未重复写入 |
| 15 | 批次查询 | `GET /imports/12` | 200，`status=imported`，异常 5 条 |
| 16 | 数据一致性 | 提交前后对比 | students 220→230（active），changes 保持 305，batches 11→12 |
| 17 | 原有服务未受影响 | `docker compose ps` | Appsmith / DB / Import API 三者仍 healthy |

---

## 二、未通过

无。

---

## 三、未执行

| 项目 | 原因 | 补充说明 |
|---|---|---|
| 浏览器渲染检查（Console / Network 面板） | 本机 Chromium 无法在沙箱内启动，`agent-browser open` 挂起后被强制终止 | 已改用接口级全链路验证替代；**页面视觉效果与前端运行时错误仍需人工确认** |
| 页面交互验收（点击筛选、打开详情抽屉、拖拽上传） | 同上 | 需人工在浏览器操作一遍 |
| 响应式与 1366×768 适配 | 无浏览器环境 | 布局按桌面优先设计，未做移动端 |
| 导入页的 UI 级重复提交 | 仅验证了接口幂等 | 前端按钮在请求期间 disabled，逻辑已实现但未在浏览器验证 |
| Docker 化前端部署 | 本轮不修改 `docker-compose.yml` | 方案见 `docs/REACT-MIGRATION-PLAN.md`，待确认后启用 |

**人工确认步骤（约 5 分钟）**

```bash
cd "Z:/ai/本地部署/campus-data-ai/web" && npm run dev
# 浏览器打开 http://127.0.0.1:5173/students
```

1. F12 → Console 应无红色报错
2. Network 中 `students?...` 请求应为 200
3. 输入「何」应只剩 10 条；切换学院应只剩该学院；翻页正常
4. 点「详情」抽屉应显示基本信息 + 异动列表
5. 切到「学生数据导入」，上传 `samples/students_demo.xlsx`，应显示 15 行 / 10 有效 / 5 异常，异常行号 12–16

---

## 四、存在安全风险（必须在真实数据前解决）

| 风险 | 现状 | 影响 |
|---|---|---|
| **无身份认证** | 任何人访问 5173 即可读写接口 | 不能接入真实数据 |
| **`X-Actor` 可伪造** | 前端从环境变量取值直接发送 | 审计记录不可信 |
| **无角色与数据权限** | 应用层无任何 RBAC，接口返回全量字段 | 越权可见全部学生 |
| **接口无 CORS 限制** | 未配置 CORS 中间件，默认仅同源 | 当前靠端口绑定 127.0.0.1 缓解，非体系化防护 |
| **HTTP 明文** | 本地无 TLS | 仅限本机使用 |

已做的缓解：

- 前端顶部常驻标注「本地测试 · 虚构数据」与「当前操作人（未认证）」。
- 未实现任何假登录、假设权限的按钮隐藏。
- 浏览器不直连数据库，全部经 API。
- 服务端口仅绑定 `127.0.0.1`。

---

## 五、结论

后端接口与前端工程可运行，两个页面的数据链路已验证到接口层。**浏览器内的视觉与交互尚未验证**，这是本轮唯一未覆盖的验收项，需人工按第三节步骤确认后再视为页面完成。

数据库未发生异常写入：导入的 10 条为预期新增，无重复、无丢失，历史批次与异动记录未被修改。

---

## 六、视觉重构（2026-10-20 16:45–17:05）

**背景：** 初版使用 AntD 默认观感，被判定视觉质量不足。

**做法：** 引入 TypeUI 设计规范（`web/DESIGN.md`，Refined 基线），按其令牌重做界面，而非继续叠加 AntD 默认样式。

| 项 | 初版 | 重构后 |
|---|---|---|
| 颜色 | AntD 默认蓝 + 大量灰阶 | 单一强调色 `#2563eb`，语义色仅用于状态 |
| 字体 | 系统默认 | 无衬线正文 + 等宽数字（学号/行号/计数），品牌字用衬线 |
| 边框 | AntD 默认阴影与描边 | 1px 发丝线 `#e4e4e7`，去除重阴影 |
| 圆角 | 6px | 8px（卡片 12px），4px 栅格间距 |
| 表头 | 常规加粗 | 10px 等宽大写 + 0.08em 字距，`#fafafa` 底 |
| 状态 | 实心 Tag | 圆点 + 文字，弱化视觉噪音 |
| 结构 | 卡片堆叠 | 页头 / 统计条 / 筛选面板 / 列表面板，层次明确 |
| 导入页 | 四个 Card | 步骤轨 + 编号面板 + 指标块 + 粘性操作条 |

新增组件：`components/ui.tsx`（PageHeader / StatTile / StatusBadge / Panel / EmptyState）。
新增样式：`src/styles.css` 全量重写（令牌 + AntD 覆写，约 700 行）。
后端补充：`/meta/filters` 增加 `change_total`，供统计条使用。

**验证状态**

| 项 | 结果 |
|---|---|
| `tsc --noEmit` | 通过，0 error |
| `vite build` | 通过，CSS 12.15 kB（gzip 2.91 kB） |
| dev server `/students`、`/import` | 均返回 200 |
| 接口 `change_total` | 305，与数据库一致 |
| 截图 / 浏览器渲染 | **未执行**：Chromium 在本沙箱无法创建渲染上下文（GPU 与 network service 崩溃），已用三种参数组合尝试均失败 |

