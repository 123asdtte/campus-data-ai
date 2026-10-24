// 悬浮助手和侧边栏共用：一份路由→页面名，避免同一页在两处显示不同称呼。
export const PAGE_TITLES: Record<string, string> = {
  '/': '总览',
  '/my-schedule': '我的课表',
  '/students': '学生信息',
  '/import': '数据导入',
  '/workbench': '数据工作台',
  '/pipeline': '资料库流水线',
  '/reports': '报表中心',
  '/assistant': 'AI 问数',
  '/changes': '学籍异动',
  '/counselor': '辅导员工作台',
  '/portal': '学生自助填报',
};
