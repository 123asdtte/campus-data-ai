# 本地演示公共资产

- `change-import-template.csv`：学籍异动导入模板，不含学生记录。
- 完整演示数据（学生/课表/异动）和四件套 Excel 已移到服务端 `demo-api/data/`，
  不再由 `web/public` 公开提供。
- 登录后通过 `/demo-api/data` 按网关角色获取授权范围；四件套下载仅学工处/管理员可用。
