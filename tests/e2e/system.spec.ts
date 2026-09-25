import { test, expect } from '@playwright/test';

test('owner sees explicit unconfigured integrations', async ({ page }) => {
  await page.goto('/');
  await page.getByLabel('Password', { exact: true }).fill('test-owner-password-42');
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByRole('heading', { name: 'System status' })).toBeVisible();
  await expect(page.locator('.status-item').filter({ hasText: 'Database' })).toContainText('healthy');
  await expect(page.locator('.status-item').filter({ hasText: 'Worker' })).toContainText('healthy');
  await expect(page.getByText('OmniRoute is not configured')).toBeVisible();
  await expect(page.getByText('No sources connected')).toBeVisible();
});
