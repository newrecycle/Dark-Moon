import { test, expect } from './fixtures';

// Synthetic datasource-list admission, real Grafana app settings save.
test('saves a datasource UID without storing a second API credential', async ({ appConfigPage, page }) => {
  await page.route('**/api/datasources', route => route.fulfill({ json: [
    { uid: 'cleanup-fixture', name: 'Cleanup fixture', type: 'darkmoon-securityposture-datasource' },
  ] }));
  await page.reload();
  await page.getByRole('combobox', { name: 'Default datasource' }).selectOption('cleanup-fixture');
  const request = page.waitForRequest(r => r.method() === 'POST' && r.url().includes('/api/plugins/') && r.url().endsWith('/settings'));
  const response = appConfigPage.waitForSettingsResponse();
  await page.getByRole('button', { name: 'Save datasource selection' }).click();
  expect((await request).postDataJSON().jsonData).toEqual({ datasourceUid: 'cleanup-fixture' });
  await expect(response).toBeOK();
  await expect(page.getByRole('status').filter({ hasText: 'Saved. Reopen the Darkmoon app' })).toBeVisible();
  await expect(page.getByRole('textbox', { name: 'API Key' })).toHaveCount(0);
});
