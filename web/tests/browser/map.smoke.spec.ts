import { expect, test } from '@playwright/test';

test('loads the flood map shell', async ({ page }) => {
	await page.goto('/');

	await expect(page).toHaveTitle(/Flood Map/);
	await expect(page.getByRole('button', { name: '2D' })).toBeVisible();
	await expect(page.getByRole('button', { name: '3D' })).toBeVisible();
	await expect(page.getByRole('heading', { name: '5-year flood hazard' })).toBeVisible();
	await expect(page.getByPlaceholder('Find a barangay...')).toBeVisible();
});

test('selects a barangay when the map is clicked', async ({ page }) => {
	await page.goto('/');

	const map = page.locator('.map');
	await expect(map).toHaveAttribute('data-map-ready', 'true', { timeout: 30_000 });
	await page.mouse.move(280, 350);
	await expect
		.poll(() => map.locator('canvas').evaluate((canvas) => getComputedStyle(canvas).cursor), {
			timeout: 30_000
		})
		.toBe('pointer');
	await page.mouse.click(280, 350);

	const heading = page.locator('#flood-information h2').first();
	await expect(heading).not.toHaveText('Select a barangay');
	await page.mouse.click(280, 350);
	await expect(heading).toHaveText('Select a barangay');
});
