import { test, expect } from './fixtures';
import pluginJson from '../src/plugin.json';

const VIEWS = pluginJson.includes.filter(item => item.type === 'page' && item.addToNav && item.path.startsWith('/a/')).map(item => ({
  type: item.path.split('/').pop(), label: item.name,
}));

for (const view of VIEWS) {
  test(`${view.label} route renders the current app`, async ({ gotoPage, page }) => {
    await gotoPage(`/${view.type}`);
    await expect(page.getByRole('heading', { name: `Darkmoon · ${view.label}`, exact: true })).toBeVisible();
    await expect(page.getByRole('combobox', { name: 'Datasource', exact: true })).toBeVisible();
  });
}

test('unknown routes return to overview', async ({ gotoPage, page }) => {
  await gotoPage('/unknown-route');
  await expect(page).toHaveURL(/\/overview(?:[?#]|$)/);
  await expect(page.getByRole('heading', { name: 'Darkmoon · Overview', exact: true })).toBeVisible();
});
