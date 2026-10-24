import { defineConfig } from '@playwright/test';

const channel = process.env.PW_CHANNEL ?? 'msedge';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 60_000,
  expect: { timeout: 15_000 },
  reporter: [['list']],
  use: {
    baseURL: process.env.DEMO_BASE_URL ?? 'http://127.0.0.1:8083',
    channel,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
});
