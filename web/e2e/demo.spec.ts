import { test, expect, type Page } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import * as XLSX from 'xlsx';

const here = path.dirname(fileURLToPath(import.meta.url));
const ledger = path.resolve(here, '../../demo-api/state/ledger.json');

// CI 把台账放在容器命名卷里，宿主机上没有该文件且无权删除；
// 清理失败不应算测试失败（卷会随 compose down -v 回收）。
function resetLedger() {
  try {
    fs.rmSync(ledger, { force: true });
  } catch (error) {
    console.warn(`跳过台账清理：${(error as Error).message}`);
  }
}

async function login(page: Page, username: string, password: string) {
  await page.goto('/login');
  await page.getByRole('textbox', { name: '账号' }).fill(username);
  await page.getByRole('textbox', { name: '密码' }).fill(password);
  await page.getByRole('button', { name: /登\s*录/ }).click();
  await expect(page).not.toHaveURL(/\/login/);
}

test.describe('本地演示关键路径', () => {
  test.describe.configure({ mode: 'serial' });

  test.beforeAll(() => {
    resetLedger();
  });

  test.afterAll(() => {
    resetLedger();
  });

  test('未登录访问业务页会跳转登录', async ({ page }) => {
    await page.goto('/workbench');
    await expect(page).toHaveURL(/\/login/);
  });

  test('不存在账号显示中文登录提示', async ({ page }) => {
    await page.goto('/login');
    await page.getByRole('textbox', { name: '账号' }).fill('__e2e_missing__');
    await page.getByRole('textbox', { name: '密码' }).fill('bad-password');
    await page.getByRole('button', { name: /登\s*录/ }).click();

    await expect(page).toHaveURL(/\/login/);
    await expect(page.getByRole('alert')).toContainText('账号不存在');
  });

  test('已登录访问登录页会回到角色首页', async ({ page }) => {
    await login(page, 'admin', 'admin123');
    await page.goto('/login');
    await expect(page).toHaveURL(/\/$/);
  });

  test('学生课表 + 悬浮 AI 查询、拒答与课表定位', async ({ page }) => {
    await login(page, 'SK-2026-000001', 'Demo@2026');
    await expect(page).toHaveURL(/\/my-schedule/);
    await expect(page.getByRole('heading', { name: '我的课表' })).toBeVisible();
    await expect(page.getByText('SK-2026-000001').first()).toBeVisible();
    await expect(page.getByText('条排课')).toBeVisible();
    await expect(page.getByRole('link', { name: /学生信息/ })).toHaveCount(0);
    await expect(page.getByRole('textbox', { name: '课表提问' })).toHaveCount(0);

    await page.goto('/students');
    await expect(page).toHaveURL(/\/my-schedule/);

    await page.getByRole('button', { name: '打开 AI 助手' }).click();
    const dialog = page.getByRole('dialog', { name: 'AI 助手' });
    await expect(dialog).toBeVisible();
    await expect(dialog.getByText(/当前页面 · 我的课表/)).toBeVisible();

    await dialog.getByRole('button', { name: '这周五第一节在哪？' }).click();
    const course = dialog.locator('.fa-course').first();
    await expect(course).toBeVisible({ timeout: 15000 });
    await expect(course).toContainText('程序设计基础');
    await course.click();
    await expect(page.locator('td.is-focus')).toHaveCount(1);

    await page.getByRole('button', { name: '打开 AI 助手' }).click();
    await expect(page.getByRole('dialog', { name: 'AI 助手' })).toContainText('程序设计基础');
    await page.keyboard.press('Escape');
    await expect(page.getByRole('dialog', { name: 'AI 助手' })).toHaveCount(0);

    await page.getByRole('button', { name: '打开 AI 助手' }).click();
    const reopened = page.getByRole('dialog', { name: 'AI 助手' });
    await reopened.getByRole('textbox', { name: '向 AI 助手提问' }).fill('我的成绩是多少？');
    await reopened.getByRole('button', { name: '发送问题' }).click();
    await expect(reopened.getByText(/只能查询本人课表/)).toBeVisible({ timeout: 15000 });
  });

  test('悬浮助手在移动端不溢出', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await login(page, 'SK-2026-000001', 'Demo@2026');
    await page.getByRole('button', { name: '打开 AI 助手' }).click();
    const dialog = page.getByRole('dialog', { name: 'AI 助手' });
    await expect(dialog).toBeVisible();
    const box = await dialog.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.x).toBeGreaterThanOrEqual(0);
    expect(box!.x + box!.width).toBeLessThanOrEqual(390);
    const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
    expect(scrollWidth).toBeLessThanOrEqual(390);
    // 仅看 scrollWidth 会漏掉“内容被压成 0 宽”的塌陷：必须断言内容列真的有宽度
    const contentWidth = await page.locator('.app-content').evaluate((el) => el.getBoundingClientRect().width);
    expect(contentWidth, '移动端内容列被压窄').toBeGreaterThanOrEqual(360);
    const pageWidth = await page.locator('.app-content > *').first().evaluate((el) => el.getBoundingClientRect().width);
    expect(pageWidth, '移动端页面容器被压窄').toBeGreaterThanOrEqual(340);
    await page.keyboard.press('Escape');
    await expect(dialog).toHaveCount(0);
  });

  test('移动端数据表格可横向滚动，不会被裁切', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await login(page, 'admin', 'admin123');
    let scrolledRoutes = 0;
    for (const route of ['/workbench', '/students', '/changes']) {
      await page.goto(route);
      const scroller = page.locator('.ant-table-content, .ant-table-body').first();
      await expect(scroller).toBeVisible();
      const state = await scroller.evaluate((el) => ({
        overflowX: getComputedStyle(el).overflowX,
        canScroll: el.scrollWidth > el.clientWidth + 1,
        clientWidth: el.clientWidth,
        scrollWidth: el.scrollWidth,
      }));
      expect(
        state.canScroll ? ['auto', 'scroll'].includes(state.overflowX) : true,
        `${route} 表格溢出但容器不可滚动（overflow-x:${state.overflowX} ${state.clientWidth}/${state.scrollWidth}）`,
      ).toBe(true);
      if (state.canScroll) {
        const scrolled = await scroller.evaluate((el) => {
          el.scrollLeft = 120;
          return el.scrollLeft;
        });
        expect(scrolled, `${route} 表格滚动无响应`).toBeGreaterThan(0);
        scrolledRoutes += 1;
      }
    }
    // 三条路由都不溢出的话，本用例就成了空断言：明确失败，提醒改测别的口径。
    expect(scrolledRoutes, '演示表格在 390px 下均未溢出，滚动保护已失效').toBeGreaterThan(0);
  });

  test('辅导员问全院人数时，助手说明数据范围而不是给出口径错误的数字', async ({ page }) => {
    await login(page, 'counselor01', 'Demo@2026');
    await page.getByRole('button', { name: '打开 AI 助手' }).click();
    const panel = page.getByRole('dialog', { name: 'AI 助手' });
    await panel.getByRole('textbox', { name: '向 AI 助手提问' }).fill('人工智能学院有多少学生？');
    await panel.getByRole('button', { name: '发送问题' }).click();
    await expect(panel.getByText(/不在你的数据范围/)).toBeVisible({ timeout: 15000 });
    await expect(panel.getByText(/人工智能学院共有/)).toHaveCount(0);
  });

  test('悬浮助手可回答异动待办，并给出台账跳转', async ({ page }) => {
    await login(page, 'admin', 'admin123');
    await page.goto('/changes');
    await page.getByRole('button', { name: '打开 AI 助手' }).click();
    const panel = page.getByRole('dialog', { name: 'AI 助手' });
    await panel.getByRole('textbox', { name: '向 AI 助手提问' }).fill('还有哪些异动没核对？');
    await panel.getByRole('button', { name: '发送问题' }).click();
    const bubble = panel.locator('.fa-message.is-assistant').last();
    await expect(bubble).toContainText('条异动已批但平台未核对', { timeout: 15000 });
    await expect(bubble.locator('.fa-action')).toContainText('打开学籍异动');
    await expect(bubble.locator('.fa-note')).toContainText('不返回身份证');
    await page.keyboard.press('Escape');
  });

  test('辅导员台账：发起、刷新持久化、平台核对持久化', async ({ page }) => {
    await login(page, 'counselor01', 'Demo@2026');
    await expect(page).toHaveURL(/\/counselor/);
    await expect(page.getByText('270').first()).toBeVisible();

    await page.getByRole('link', { name: /学籍异动/ }).click();
    await expect(page.getByRole('heading', { name: '学籍异动' })).toBeVisible();
    await page.getByRole('button', { name: /发起异动/ }).click();

    const dialog = page.getByRole('dialog');
    await dialog.getByRole('combobox', { name: /学生/ }).click();
    await page.getByText('SK-2026-000001 · 万* · 信息安全2601').click();
    await dialog.getByRole('textbox', { name: /异动原因/ }).fill('E2E 休学登记');
    await dialog.getByRole('button', { name: /提交（待平台核对）/ }).click();

    const row = page.getByRole('row', { name: /YD-LOCAL-/ });
    await expect(row).toContainText('E2E 休学登记');
    await page.reload();
    await expect(page.getByRole('row', { name: /YD-LOCAL-/ })).toContainText('E2E 休学登记');

    await page.getByRole('row', { name: /YD-LOCAL-/ }).getByRole('button', { name: '平台核对' }).click();
    await expect(page.getByRole('row', { name: /YD-LOCAL-/ })).toContainText('已核对');
    await page.reload();
    await expect(page.getByRole('row', { name: /YD-LOCAL-/ })).toContainText('已核对');
  });

  test('辅导员通过 CSV 导入异动并持久化', async ({ page }) => {
    await login(page, 'counselor01', 'Demo@2026');
    await page.goto('/changes');
    await page.locator('input[type=file]').setInputFiles({
      name: 'e2e-import.csv',
      mimeType: 'text/csv',
      buffer: Buffer.from(
        '\uFEFFUID,异动编号,异动类型,异动日期,异动原因,异动后去向,正式审批状态\n'
          + 'SK-2026-000002,UI-IMP-E2E,复学,2026.10.5,E2E 导入测试,—\n',
        'utf8',
      ),
    });

    const row = page.getByRole('row', { name: /UI-IMP-E2E/ });
    await expect(row).toContainText('E2E 导入测试');
    await page.reload();
    await expect(page.getByRole('row', { name: /UI-IMP-E2E/ })).toContainText('E2E 导入测试');
  });

  test('辅导员可导出本班名单', async ({ page }) => {
    await login(page, 'counselor01', 'Demo@2026');
    await expect(page.getByRole('heading', { name: '辅导员工作台' })).toBeVisible();
    const downloadPromise = page.waitForEvent('download');
    await page.getByRole('button', { name: /导出本班名单/ }).click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toMatch(/带班名单_.*\.csv$/);
  });

  test('辅导员无权下载全校四件套', async ({ page }) => {
    await login(page, 'counselor01', 'Demo@2026');
    const status = await page.evaluate(async () => {
      const token = window.localStorage.getItem('campus.gateway.token');
      const response = await fetch('/demo-api/four-sheet', {
        headers: { Authorization: `Bearer ${token}` },
      });
      return response.status;
    });
    expect(status).toBe(403);
  });

  test('学工处可见全校数据，但无管理员专属页面', async ({ page }) => {
    await login(page, 'xgb01', 'Demo@2026');
    await expect(page).toHaveURL(/\/workbench/);
    await expect(page.getByRole('heading', { name: '数据工作台' })).toBeVisible();
    await expect(page.getByText('5,581').first()).toBeVisible();
    await expect(page.locator('a.app-nav-item', { hasText: 'AI 问数' })).toHaveCount(0);
    await expect(page.locator('a.app-nav-item', { hasText: '学生信息' })).toHaveCount(0);
    await expect(page.locator('a.app-nav-item', { hasText: '数据导入' })).toHaveCount(0);

    await page.goto('/assistant');
    await expect(page).toHaveURL(/\/workbench/);
    await page.goto('/students');
    await expect(page).toHaveURL(/\/workbench/);

    await page.getByRole('button', { name: '打开 AI 助手' }).click();
    const dialog = page.getByRole('dialog', { name: 'AI 助手' });
    await expect(dialog.getByText(/当前页面 · 数据工作台/)).toBeVisible();
    await dialog.getByRole('button', { name: '人工智能学院有多少学生？' }).click();
    await expect(dialog.getByText(/名学生/)).toBeVisible({ timeout: 15000 });
    await page.keyboard.press('Escape');

    await page.locator('a.app-nav-item', { hasText: '学籍异动' }).click();
    await expect(page.getByRole('heading', { name: '学籍异动' })).toBeVisible();
  });

  test('管理员导入预检：上传 XLSX 后可校验（不提交）', async ({ page }) => {
    await login(page, 'admin', 'admin123');
    await page.locator('a.app-nav-item', { hasText: '数据导入' }).click();
    await expect(page.getByRole('heading', { name: '数据导入' })).toBeVisible();

    const sheet = XLSX.utils.aoa_to_sheet([
      ['学号', '姓名', '学院', '专业', '班级', '入学年份', '在校状态'],
      ['G2026001', '测试甲', '计算机学院', '软件技术', '软件2601', 2026, '在校'],
      ['G2026002', '测试乙', '电子信息学院', '物联网应用技术', '物联网2601', 2026, '在校'],
    ]);
    const workbook = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(workbook, sheet, 'Sheet1');
    const buffer = XLSX.write(workbook, { type: 'buffer', bookType: 'xlsx' }) as Buffer;

    await page.locator('input[type=file]').setInputFiles({
      name: 'e2e-import.xlsx',
      mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      buffer,
    });
    await expect(page.getByText(/已选择：e2e-import\.xlsx/)).toBeVisible();
    await page.getByRole('button', { name: '上传并识别' }).click();
    await expect(page.getByText('识别结果')).toBeVisible();
    await expect(page.getByText(/识别到/)).toBeVisible();

    const validateResponse = page.waitForResponse(
      (response) => response.url().includes('/imports/') && response.url().includes('/validate'),
    );
    await page.getByRole('button', { name: '开始校验' }).first().click();
    const response = await validateResponse;
    expect(response.status()).toBe(200);
    await expect(page.getByText('03 校验结果')).toBeVisible();
  });

  test('管理员问数页调用服务端接口，且不重复悬浮入口', async ({ page }) => {
    await login(page, 'admin', 'admin123');
    await page.goto('/assistant');
    await expect(page.getByRole('heading', { name: 'AI 问数' })).toBeVisible();
    await expect(page.getByRole('button', { name: '打开 AI 助手' })).toHaveCount(0);

    const reply = page.waitForResponse((response) => response.url().includes('/demo-api/assistant/query'));
    await page.getByRole('button', { name: '人工智能学院有多少学生？' }).click();
    expect((await reply).status()).toBe(200);

    const bubble = page.locator('.ai-message.is-assistant').last();
    await expect(bubble).toContainText('人工智能学院');
    await expect(bubble).toContainText('人数统计');
    await expect(bubble.getByText('全校范围演示数据')).toBeVisible();
  });

  test('管理员可查看全校数据并下载四件套', async ({ page }) => {
    await login(page, 'admin', 'admin123');
    await page.locator('a.app-nav-item', { hasText: '数据工作台' }).click();
    await expect(page.getByRole('heading', { name: '数据工作台' })).toBeVisible();
    await expect(page.getByText('5,581').first()).toBeVisible();

    await page.locator('a.app-nav-item', { hasText: '报表中心' }).click();
    await expect(page.getByRole('heading', { name: '报表中心' })).toBeVisible();
    await expect(page.getByText('5,581').first()).toBeVisible();

    const downloadPromise = page.waitForEvent('download');
    await page.getByRole('button', { name: /下载四件套 Excel/ }).click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toBe('four-sheet.xlsx');
  });

  test('管理员页面无控制台错误或横向溢出', async ({ page }) => {
    const problems: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') problems.push(`console: ${msg.text()}`);
    });
    page.on('pageerror', (err) => problems.push(`pageerror: ${err.message}`));

    await page.setViewportSize({ width: 1366, height: 768 });
    await login(page, 'admin', 'admin123');

    const routes = ['/', '/workbench', '/pipeline', '/reports', '/assistant', '/changes', '/counselor', '/students', '/import'];
    for (const route of routes) {
      await page.goto(route);
      await expect(page.locator('h1, h2').first()).toBeVisible();
      const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
      expect(scrollWidth, `${route} 出现横向溢出`).toBeLessThanOrEqual(1366);
    }
    expect(problems).toEqual([]);
  });

  test('管理员筛选控件具备可访问名称', async ({ page }) => {
    await login(page, 'admin', 'admin123');
    const checks: Array<[string, string, string]> = [
      ['/workbench', 'textbox', '搜索学生'],
      ['/workbench', 'combobox', '学院'],
      ['/workbench', 'combobox', '学籍状态'],
      ['/workbench', 'combobox', '学生类型'],
      ['/reports', 'textbox', '搜索学生'],
      ['/reports', 'combobox', '学院'],
      ['/reports', 'combobox', '学籍状态'],
      ['/reports', 'combobox', '班级'],
      ['/reports', 'combobox', '学生类型'],
      ['/changes', 'textbox', '搜索异动'],
      ['/changes', 'combobox', '异动类型'],
      ['/changes', 'combobox', '正式审批状态'],
      ['/changes', 'combobox', '学院'],
      ['/counselor', 'textbox', '搜索本班学生'],
      ['/counselor', 'combobox', '班级'],
      ['/students', 'textbox', '关键词（学号或姓名）'],
      ['/students', 'combobox', '学院'],
      ['/students', 'combobox', '班级'],
      ['/students', 'combobox', '在校状态'],
      ['/students', 'switch', '显示停用记录'],
      ['/assistant', 'textbox', '输入问题'],
      ['/import', 'spinbutton', '批次号'],
    ];
    for (const [route, role, name] of checks) {
      await page.goto(route);
      await expect(page.getByRole(role as 'textbox', { name, exact: true })).toHaveCount(1);
    }
  });

  test('失效 token 清除会话并回到登录页', async ({ page }) => {
    await login(page, 'SK-2026-000001', 'Demo@2026');
    await expect(page).toHaveURL(/\/my-schedule/);

    await page.evaluate(() => window.localStorage.setItem('campus.gateway.token', 'invalid-token'));
    await page.reload();

    await expect(page).toHaveURL(/\/login/);
    await expect(page.getByRole('alert')).toContainText('登录状态已失效');
    expect(await page.evaluate(() => window.localStorage.getItem('campus.gateway.token'))).toBeNull();
  });

  test('业务请求遇到 401 同样清理会话', async ({ page }) => {
    await login(page, 'admin', 'admin123');
    await page.locator('a.app-nav-item', { hasText: '学生信息' }).click();
    await expect(page.getByRole('heading', { name: '学生信息' })).toBeVisible();

    await page.evaluate(() => window.localStorage.setItem('campus.gateway.token', 'invalid-token'));
    await page.getByRole('button', { name: '刷新' }).click();

    await expect(page).toHaveURL(/\/login/);
    await expect(page.getByRole('alert')).toContainText('登录状态已失效');
    expect(await page.evaluate(() => window.localStorage.getItem('campus.gateway.token'))).toBeNull();
  });
});
