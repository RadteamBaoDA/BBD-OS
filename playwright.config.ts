import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: false,
  retries: 0,
  reporter: 'list',
  use: {
    ...devices['Desktop Chrome'],
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? 'http://localhost:3000',
  },
  projects: [
    { name: 'bootstrap', testMatch: 'auth.spec.ts' },
    {
      name: 'system',
      testMatch: '**/*.spec.ts',
      testIgnore: 'auth.spec.ts',
      dependencies: ['bootstrap'],
    },
  ],
  webServer: process.env.PLAYWRIGHT_EXTERNAL_SERVER ? undefined : {
    command: 'npm run dev --workspace apps/web',
    url: 'http://127.0.0.1:3000',
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    env: { API_INTERNAL_URL: 'http://127.0.0.1:8000' },
  },
});
