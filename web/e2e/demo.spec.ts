import { test, expect, type Page } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const ledger = path.resolve(here, '../../demo-api/state/ledger.json');

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
    fs.rmSync(ledger, { force: true });
  });

  test.afterAll(() => {
    fs.rmSync(ledger, { force: true });
  });

  test('未登录访问业务页会跳转登录', async ({ page }) => {
    await page.goto('/workbench');
    await expect(page).toHaveURL(/\/login/);
  });

  test('学生只看到本人课表，越权路由被送回', async ({ page }) => {
    await login(page, 'SK-2026-000001', 'Demo@2026');
    await expect(page).toHaveURL(/\/my-schedule/);
    await expect(page.getByRole('heading', { name: '我的课表' })).toBeVisible();
    await expect(page.getByText('SK-2026-000001').first()).toBeVisible();
    await expect(page.getByText('条排课')).toBeVisible();
    await expect(page.getByRole('link', { name: /学生信息/ })).toHaveCount(0);

    await page.goto('/students');
    await expect(page).toHaveURL(/\/my-schedule/);

    await page.getByRole('button', { name: '今天下午有没有课？' }).click();
    await expect(page.getByText(/青果\/教务处/)).toBeVisible();
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

  test('管理员导入预检：上传 CSV 后可校验（不提交）', async ({ page }) => {
    await login(page, 'admin', 'admin123');
    await page.locator('a.app-nav-item', { hasText: '数据导入' }).click();
    await expect(page.getByRole('heading', { name: '数据导入' })).toBeVisible();

    await page.locator('input[type=file]').setInputFiles(
      path.resolve(here, '../../samples/test_acceptance.csv'),
    );
    await expect(page.getByText(/已选择：test_acceptance\.csv/)).toBeVisible();
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
});
