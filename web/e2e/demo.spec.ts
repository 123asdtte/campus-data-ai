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
    await expect(reopened.getByText(/只回答你自己的课表和本人学籍信息/)).toBeVisible({ timeout: 15000 });
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

  test('学生问本人学籍信息时按档案回答，不再被课表空数据吞掉', async ({ page }) => {
    await login(page, 'SK-2026-000001', 'Demo@2026');
    await page.goto('/my-schedule');
    await page.getByRole('button', { name: '打开 AI 助手' }).click();
    const panel = page.getByRole('dialog', { name: 'AI 助手' });
    await panel.getByRole('textbox', { name: '向 AI 助手提问' }).fill('我的学籍状态是什么？');
    await panel.getByRole('button', { name: '发送问题' }).click();
    const bubble = panel.locator('.fa-message.is-assistant').last();
    await expect(bubble).toContainText('学籍状态：', { timeout: 15000 });
    // 这条账号的演示课表是空的：修好后不能再拿“没有课”去回答档案问题
    await expect(bubble).not.toContainText('没有课');
    await expect(bubble.locator('.fa-note')).toContainText('学号、证件号');
    await expect(bubble.locator('.fa-scope')).toContainText('仅本人档案');
    await panel.getByRole('textbox', { name: '向 AI 助手提问' }).fill('我的学号是多少？');
    await panel.getByRole('button', { name: '发送问题' }).click();
    await expect(panel.locator('.fa-message.is-assistant').last()).toContainText('只回答你自己的课表和本人学籍信息');
    await page.keyboard.press('Escape');
  });

  test('悬浮面板把服务端的截止时间与追问一起交给用户，不再只显示数据范围', async ({ page }) => {
    await login(page, 'SK-2026-000001', 'Demo@2026');
    await page.goto('/my-schedule');
    await page.getByRole('button', { name: '打开 AI 助手' }).click();
    const panel = page.getByRole('dialog', { name: 'AI 助手' });
    await panel.getByRole('textbox', { name: '向 AI 助手提问' }).fill('明天有什么课');
    const responseReady = page.waitForResponse((res) => res.url().includes('/demo-api/assistant/query'));
    await panel.getByRole('button', { name: '发送问题' }).click();
    // 断言的期望值直接从这次响应里取，不写死演示数据：账号有没有排课都能跑，
    // 而「面板丢掉了 as_of / suggestions」这个缺陷一旦被重新引入就必然变红。
    const reply = await (await responseReady).json();
    const bubble = panel.locator('.fa-message.is-assistant').last();
    await expect(bubble).toContainText(String(reply.answer).slice(0, 8), { timeout: 15000 });
    const asOf = String(reply.as_of).slice(0, 16).replace('T', ' ');
    await expect(bubble.locator('.fa-scope')).toContainText(`截至 ${asOf}`);
    const chips = panel.locator('.fa-suggestions button');
    const firstChip = reply.suggestions?.length ? reply.suggestions[0] : '明天下午有什么课？';
    await expect(chips.first()).toHaveText(String(firstChip), { timeout: 15000 });
    await page.keyboard.press('Escape');
  });

  test('跨周课程定位：当前周不可见时明说未定位，可见时真正高亮', async ({ page }) => {
    await login(page, 'SK-2026-000001', 'Demo@2026');
    await page.goto('/my-schedule');
    await page.getByRole('button', { name: '打开 AI 助手' }).click();
    const panel = page.getByRole('dialog', { name: 'AI 助手' });
    await panel.getByRole('textbox', { name: '向 AI 助手提问' }).fill('下周有哪些课程安排？');
    const responseReady = page.waitForResponse((res) => res.url().includes('/demo-api/assistant/query'));
    await panel.getByRole('button', { name: '发送问题' }).click();
    const reply = await (await responseReady).json();
    expect(reply.courses?.length ?? 0, '演示数据下周应有排课：锚点漂移时先查 demo-data.json 的 current_week').toBeGreaterThan(0);
    const bubble = panel.locator('.fa-message.is-assistant').last();

    // 演示数据第 8 周课表里没有「周三 5-6节 高等数学(一)」：点击后必须明说未定位，不能假装已定位
    await bubble.locator('.fa-course').filter({ hasText: '高等数学(一)' }).filter({ hasText: '周三' }).click();
    await expect(page.getByText('不在当前第 8 周的周三 5-6节，页面未做定位')).toBeVisible({ timeout: 15000 });

    // 对照：同一门课当前周可见的格子（周二 1-2节）要真的高亮，且不再弹提示
    await page.getByRole('button', { name: '打开 AI 助手' }).click();
    await bubble.locator('.fa-course').filter({ hasText: '高等数学(一)' }).filter({ hasText: '周二' }).click();
    await expect(page.getByText('不在当前第')).toHaveCount(0);
    await expect(page.locator('td[data-weekday="周二"][data-period="1-2节"]')).toHaveClass(/is-focus/);
    await page.keyboard.press('Escape');
  });

  test('辅导员问全院人数时，助手说明数据范围而不是给出口径错误的数字', async ({ page }) => {
    await login(page, 'counselor01', 'Demo@2026');
    await page.getByRole('button', { name: '打开 AI 助手' }).click();
    const panel = page.getByRole('dialog', { name: 'AI 助手' });
    await panel.getByRole('textbox', { name: '向 AI 助手提问' }).fill('人工智能学院有多少学生？');
    await panel.getByRole('button', { name: '发送问题' }).click();
    await expect(panel.getByText(/不在你的数据范围/)).toBeVisible({ timeout: 15000 });
    await expect(panel.locator('.fa-scope').last()).toContainText('本班范围');
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
    await expect(bubble.locator('.fa-scope')).toContainText('全校范围');
    await expect(bubble.locator('.fa-action')).toContainText('打开学籍异动');
    await expect(bubble.locator('.fa-note')).toContainText('不返回身份证');
    await page.keyboard.press('Escape');
  });

  test('悬浮助手把“休学退学有多少人”答成人数，不是异动条数', async ({ page }) => {
    await login(page, 'admin', 'admin123');
    await page.goto('/students');
    await page.getByRole('button', { name: '打开 AI 助手' }).click();
    const panel = page.getByRole('dialog', { name: 'AI 助手' });
    // 走推荐问题按钮：这就是管理员真实会点的那条路径
    await panel.locator('.fa-suggestions').getByRole('button', { name: '全校休学和退学各有多少人？' }).click();
    const bubble = panel.locator('.fa-message.is-assistant').last();
    await expect(bubble).toContainText(/休学 \d+ 人/, { timeout: 15000 });
    await expect(bubble).toContainText(/退学 \d+ 人/);
    await expect(bubble).toContainText('不是异动条数');
    await expect(bubble).not.toContainText('学籍异动记录');
    await page.keyboard.press('Escape');
  });

  test('悬浮助手的页面上下文与推荐问题会跟着业务页面切换', async ({ page }) => {
    await login(page, 'admin', 'admin123');
    const panel = page.getByRole('dialog', { name: 'AI 助手' });
    const chips = panel.locator('.fa-suggestions').getByRole('button');

    await page.goto('/changes');
    await page.getByRole('button', { name: '打开 AI 助手' }).click();
    await expect(panel.locator('.fa-head')).toContainText('当前页面 · 学籍异动');
    await expect(chips.first()).toHaveText('还有哪些异动没核对？');
    await expect(chips.nth(2)).toHaveText('异动台账里休学和退学各有多少条？');

    // SPA 内跳转：面板不被关闭、历史不丢，但页面上下文与推荐问题必须换成本页口径
    await page.getByRole('link', { name: '报表中心' }).click();
    await expect(page).toHaveURL(/\/reports/);
    await expect(panel.locator('.fa-head')).toContainText('当前页面 · 报表中心');
    await expect(chips.first()).toHaveText('有哪些报表可以下载？');
    await chips.first().click();
    const bubble = panel.locator('.fa-message.is-assistant').last();
    await expect(bubble).toContainText('报表中心', { timeout: 15000 });
    await expect(bubble.locator('.fa-scope')).toBeVisible();
    await expect(bubble.locator('.fa-action')).toBeVisible();
    // 前一轮问答还在：说明换页不会把用户已经问出来的结果清空
    await expect(panel.locator('.fa-message.is-assistant')).toHaveCount(2);
  });

  test('悬浮助手能听懂“今天数据有什么问题”这类自然问法', async ({ page }) => {
    await login(page, 'admin', 'admin123');
    await page.goto('/pipeline');
    await page.getByRole('button', { name: '打开 AI 助手' }).click();
    const panel = page.getByRole('dialog', { name: 'AI 助手' });
    // 不点推荐 chip、直接打字：这条问法里没有“数据质量”四个字，以前会被落回“我只能回答……”
    await panel.getByRole('textbox', { name: '向 AI 助手提问' }).fill('今天数据有什么问题？');
    await panel.getByRole('button', { name: '发送问题' }).click();
    const bubble = panel.locator('.fa-message.is-assistant').last();
    await expect(bubble).toContainText('重复学号', { timeout: 15000 });
    await expect(bubble.locator('.fa-scope')).toContainText('全校范围');
    await expect(bubble.locator('.fa-action')).toContainText('查看数据工作台');
    await page.keyboard.press('Escape');
  });

  test('学生检索：唯一 UID 打开档案，并可按上下文定位异动', async ({ page }) => {
    await login(page, 'counselor01', 'Demo@2026');
    await page.goto('/counselor');
    await expect(page.getByRole('heading', { name: '辅导员工作台' })).toBeVisible();

    await page.getByRole('button', { name: '打开 AI 助手' }).click();
    const panel = page.getByRole('dialog', { name: 'AI 助手' });
    await panel.getByRole('textbox', { name: '向 AI 助手提问' }).fill('帮我找 SK-2026-000004');
    await panel.getByRole('button', { name: '发送问题' }).click();
    const bubble = panel.locator('.fa-message.is-assistant').last();
    await expect(bubble).toContainText('找到 余*', { timeout: 15000 });
    await expect(bubble.locator('.fa-student')).toContainText('SK-2026-000004');
    await bubble.getByRole('button', { name: /打开学生档案/ }).click();

    await expect(page).toHaveURL(/\/counselor\?student=SK-2026-000004/);
    await expect(page.locator('.ant-drawer-title')).toContainText('SK-2026-000004');
    await expect(page.locator('.ant-drawer-body')).toContainText('跟读生转正式');

    await page.getByRole('button', { name: '在异动台账中定位' }).click();
    await expect(page).toHaveURL(/\/changes\?student=SK-2026-000004/);
    await expect(page.getByText(/已按学生 SK-2026-000004 筛选/)).toBeVisible();
    await expect(page.locator('.ant-table-row.is-focused').first()).toBeVisible();

    // 页面上下文里的“他”应来自 URL 中的学生 UID，而不是模型猜测
    await page.getByRole('button', { name: '打开 AI 助手' }).click();
    const contextPanel = page.getByRole('dialog', { name: 'AI 助手' });
    await expect(contextPanel.locator('.fa-head')).toContainText('当前页面 · 学生档案');
    await contextPanel.getByRole('textbox', { name: '向 AI 助手提问' }).fill('他的异动记录有哪些？');
    await contextPanel.getByRole('button', { name: '发送问题' }).click();
    const contextBubble = contextPanel.locator('.fa-message.is-assistant').last();
    await expect(contextBubble).toContainText('找到 余*', { timeout: 15000 });
    await expect(contextBubble.locator('.fa-action')).toContainText('在异动台账中定位');
    await page.keyboard.press('Escape');
  });

  test('学生检索：同名歧义只给候选，不自动打开档案', async ({ page }) => {
    await login(page, 'xgb01', 'Demo@2026');
    await page.goto('/workbench');

    await page.getByRole('button', { name: '打开 AI 助手' }).click();
    const panel = page.getByRole('dialog', { name: 'AI 助手' });
    await panel.getByRole('textbox', { name: '向 AI 助手提问' }).fill('找一下李**');
    await panel.getByRole('button', { name: '发送问题' }).click();
    const bubble = panel.locator('.fa-message.is-assistant').last();
    await expect(bubble).toContainText('无法确定是哪一位', { timeout: 15000 });
    await expect(bubble.locator('.fa-student')).toHaveCount(5);
    await expect(bubble.locator('.fa-action')).toHaveCount(0);
    await expect(page).toHaveURL(/\/workbench$/);

    const first = bubble.locator('.fa-student').first();
    const uid = (await first.locator('.fa-student-id').textContent())?.trim() ?? '';
    expect(uid).toMatch(/^SK-\d{4}-\d{6}$/);
    await first.click();
    await expect(page).toHaveURL(new RegExp(`/workbench\\?student=${uid}$`));
    await expect(page.locator('.ant-drawer-title')).toContainText(uid);
  });

  test('学生检索：辅导员范围外 UID 不打开档案', async ({ page }) => {
    await login(page, 'counselor01', 'Demo@2026');
    await page.goto('/counselor');
    await page.getByRole('button', { name: '打开 AI 助手' }).click();
    const panel = page.getByRole('dialog', { name: 'AI 助手' });
    await panel.getByRole('textbox', { name: '向 AI 助手提问' }).fill('帮我找 SK-2026-000046');
    await panel.getByRole('button', { name: '发送问题' }).click();
    const bubble = panel.locator('.fa-message.is-assistant').last();
    await expect(bubble).toContainText('本班范围没有找到', { timeout: 15000 });
    await expect(bubble.locator('.fa-student')).toHaveCount(0);
    await expect(bubble.locator('.fa-action')).toHaveCount(0);
    await expect(page).toHaveURL(/\/counselor$/);
    await expect(page.locator('.ant-drawer-title')).toHaveCount(0);
  });

  test('悬浮助手异动卡片：待核对记录可直接定位并核对状态', async ({ page }) => {
    await login(page, 'xgb01', 'Demo@2026');
    await page.goto('/changes');
    await page.getByRole('button', { name: '打开 AI 助手' }).click();
    const panel = page.getByRole('dialog', { name: 'AI 助手' });
    await panel.getByRole('textbox', { name: '向 AI 助手提问' }).fill('还有哪些异动没核对？');
    await panel.getByRole('button', { name: '发送问题' }).click();
    const bubble = panel.locator('.fa-message.is-assistant').last();
    await expect(bubble).toContainText('平台未核对', { timeout: 15000 });
    await expect(bubble.locator('.fa-change').first()).toBeVisible();

    const first = bubble.locator('.fa-change').first();
    const changeNo = (await first.locator('.fa-change-no').textContent())?.trim() ?? '';
    expect(changeNo).toMatch(/^YD/);
    await first.click();
    await expect(page).toHaveURL(new RegExp(`/changes\\?change=${changeNo}$`));
    await expect(page.getByText(new RegExp(`已定位到异动 ${changeNo}`))).toBeVisible();
    await expect(page.locator('.ant-table-row.is-focused').first()).toBeVisible();

    await page.getByRole('button', { name: '打开 AI 助手' }).click();
    const contextPanel = page.getByRole('dialog', { name: 'AI 助手' });
    await expect(contextPanel.locator('.fa-head')).toContainText('当前页面 · 异动记录');
    await contextPanel.getByRole('textbox', { name: '向 AI 助手提问' }).fill('核对了吗？');
    await contextPanel.getByRole('button', { name: '发送问题' }).click();
    const contextBubble = contextPanel.locator('.fa-message.is-assistant').last();
    await expect(contextBubble).toContainText(changeNo, { timeout: 15000 });
    await expect(contextBubble).toContainText('平台');
    await expect(contextBubble.locator('.fa-action')).toContainText('在异动台账中定位');
    await page.keyboard.press('Escape');
  });

  test('管理员独立 AI 页渲染异动卡片并定位', async ({ page }) => {
    await login(page, 'admin', 'admin123');
    await page.goto('/assistant');
    await page.getByRole('textbox', { name: '输入问题' }).fill('还有哪些异动没核对？');
    await page.getByRole('button', { name: '发送' }).click();
    const bubble = page.locator('.ai-message.is-assistant').last();
    await expect(bubble).toContainText('平台未核对', { timeout: 15000 });
    await expect(bubble.locator('.ai-change')).toHaveCount(5);

    const first = bubble.locator('.ai-change').first();
    const changeNo = (await first.locator('.ai-change-no').textContent())?.trim() ?? '';
    expect(changeNo).toMatch(/^YD/);
    await first.click();
    await expect(page).toHaveURL(new RegExp(`/changes\\?change=${changeNo}$`));
    await expect(page.getByText(new RegExp(`已定位到异动 ${changeNo}`))).toBeVisible();
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

  test('管理员独立 AI 页渲染学生候选并跳转档案', async ({ page }) => {
    await login(page, 'admin', 'admin123');
    await page.goto('/assistant');
    await page.getByRole('textbox', { name: '输入问题' }).fill('找一下李**');
    await page.getByRole('button', { name: '发送' }).click();

    const bubble = page.locator('.ai-message.is-assistant').last();
    await expect(bubble).toContainText('无法确定是哪一位', { timeout: 15000 });
    await expect(bubble.locator('.ai-student')).toHaveCount(5);

    const first = bubble.locator('.ai-student').first();
    const uid = (await first.locator('.ai-student-id').textContent())?.trim() ?? '';
    expect(uid).toMatch(/^SK-\d{4}-\d{6}$/);
    await first.click();
    await expect(page).toHaveURL(new RegExp(`/workbench\\?student=${uid}$`));
    await expect(page.locator('.ant-drawer-title')).toContainText(uid);
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

  test('悬浮助手连续追问后会把最新回答滚进可视区', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 560 });
    await login(page, 'admin', 'admin123');
    await page.goto('/students');
    await page.getByRole('button', { name: '打开 AI 助手' }).click();
    const panel = page.getByRole('dialog', { name: 'AI 助手' });
    const box = panel.locator('.fa-messages');
    const bubbles = panel.locator('.fa-message.is-assistant');
    const questions = ['数据质量怎么样？', '最近的学籍异动情况'];
    for (const [index, question] of questions.entries()) {
      await panel.getByRole('textbox', { name: '向 AI 助手提问' }).fill(question);
      await panel.getByRole('button', { name: '发送问题' }).click();
      // 第 0 条是欢迎语，所以第 index 个回答落在 nth(index + 1)
      await bubbles.nth(index + 1).waitFor({ timeout: 15000 });
    }

    const state = await box.evaluate((el) => {
      const chips = el.querySelectorAll('.fa-scope');
      const last = chips[chips.length - 1] as HTMLElement;
      return {
        chipCount: chips.length,
        overflow: el.scrollHeight - el.clientHeight,
        chipBelowFold: Math.round(last.getBoundingClientRect().bottom - el.getBoundingClientRect().bottom),
        gapToBottom: Math.round(el.scrollHeight - el.scrollTop - el.clientHeight),
      };
    });
    expect(state.chipCount).toBe(questions.length);
    // 先证明对话确实溢出面板，否则“滚到可视区”这条断言不成立
    expect(state.overflow).toBeGreaterThan(40);
    expect(state.chipBelowFold).toBeLessThanOrEqual(1);
    expect(state.gapToBottom).toBeLessThanOrEqual(1);
  });
  test('台账降级时全站提示数据可能不完整', async ({ page }) => {
    // CI 的台账在容器命名卷里，宿主机改不动，所以这里拦截 /demo-api/data 的响应，
    // 只验证「服务端一旦下发 ledger_warning，页面就一定说清楚」这条前后端契约。
    const warning = '学籍异动台账文件不是合法 JSON，本次仅展示基础演示数据，台账里的异动记录未计入';
    await login(page, 'admin', 'admin123');
    await page.route('**/demo-api/data', async (route) => {
      const response = await route.fetch();
      const body = await response.json();
      await route.fulfill({
        response,
        body: JSON.stringify({ ...body, meta: { ...body.meta, ledger_warning: warning } }),
      });
    });

    await page.goto('/workbench');
    const alert = page.getByRole('alert');
    await expect(alert).toContainText('数据可能不完整');
    await expect(alert).toContainText('台账里的异动记录未计入');

    // 台账正常时不该出现这条提示，否则等于用一个永久警告掩盖真实状态。
    await page.unroute('**/demo-api/data');
    await page.goto('/workbench');
    await expect(page.getByRole('alert')).toHaveCount(0);
  });


  test('总览与工作台各自标明数据源，两套条数不一致不再被读成同步失败', async ({ page }) => {
    // 侧栏导航里也有「学籍异动」链接，所以必须按卡片结构取数，不能按裸文本找。
    // 工作台用 toLocaleString 渲染（5,581），千分位要剥掉，否则数字解析成 NaN。
    const kpiNumber = async (section: string, item: string, value: string, label: string) => {
      const cell = page.locator(`.${section} .${item}`, { hasText: label }).locator(`.${value}`);
      await expect(cell).toHaveCount(1);
      return Number((await cell.innerText()).replace(/[^\d.-]/g, ''));
    };

    await login(page, 'admin', 'admin123');
    await page.goto('/');
    await expect(page.getByText('两套数据彼此独立')).toBeVisible();
    const overview = {
      changes: await kpiNumber('hv-metrics', 'hv-metric', 'hv-metric-value', '学籍异动'),
      students: await kpiNumber('hv-metrics', 'hv-metric', 'hv-metric-value', '在校学生'),
    };

    await page.goto('/workbench');
    const workbench = {
      changes: await kpiNumber('wb-kpis', 'wb-kpi', 'wb-kpi-value', '学籍异动'),
      students: await kpiNumber('wb-kpis', 'wb-kpi', 'wb-kpi-value', '学生总数'),
    };

    // 两边都是真实数字，不是 '—' 占位
    for (const value of [...Object.values(overview), ...Object.values(workbench)]) {
      expect(value).toBeGreaterThan(0);
    }
    // 两条链路读的是不同数据集；一旦将来统一数据源这两组会相等并让本用例变红，
    // 那时才该删掉总览的口径说明，而不是现在假装它们是同一套数。
    expect(overview.changes).not.toBe(workbench.changes);
    expect(overview.students).not.toBe(workbench.students);
  });
});
