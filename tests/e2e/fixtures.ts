import { test as base, expect } from '@playwright/test';

export const test = base;
export { expect };

test.use({ storageState: 'playwright/.auth/owner.json' });
