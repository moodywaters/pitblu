import {expect, test} from '@playwright/test';

const viewports = [
  {name: 'mobile-390x844', width: 390, height: 844},
  {name: 'tablet-1024x768', width: 1024, height: 768},
  {name: 'desktop-1440x900', width: 1440, height: 900}
];

const system = {
  product: 'Pitblu', version: '0.3.1', activeCook: null, latestCook: null,
  core: {available: true, lastError: null, devices: [{
    deviceId: 'igrill-2', name: 'iGrill 2', friendlyName: 'iGrill 2',
    probes: [
      {probe: 1, available: true, present: true, fresh: true, temperatureC: 24},
      {probe: 2, available: true, present: true, fresh: true, temperatureC: 67},
      {probe: 3, available: true, present: true, fresh: true, temperatureC: 21},
      {probe: 4, available: true, present: false, fresh: true, temperatureC: null}
    ], battery: {available: true, fresh: true, percentage: 82}
  }]}
};

for (const viewport of viewports) {
  test(`Home ${viewport.name}`, async ({page}) => {
    await page.setViewportSize(viewport);
    await page.addInitScript(() => sessionStorage.setItem('pitblu-operator-token', 'visual-test-token'));
    await page.route('**/api/v1/events', route => route.fulfill({status: 200, contentType: 'text/event-stream', body: ''}));
    await page.route('**/api/v1/**', route => {
      const path = new URL(route.request().url()).pathname;
      const body = path === '/api/v1/system' ? system : [];
      return route.fulfill({status: 200, contentType: 'application/json', body: JSON.stringify(body)});
    });
    await page.goto('/');
    await page.addStyleTag({content: 'header time { visibility: hidden !important; }'});
    await expect(page.getByRole('heading', {name: 'Everything’s ready'})).toBeVisible();
    await expect(page).toHaveScreenshot(`home-${viewport.name}.png`, {animations: 'disabled'});
  });
}
