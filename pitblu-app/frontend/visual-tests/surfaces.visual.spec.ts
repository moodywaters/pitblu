import {expect, type Page, test} from '@playwright/test';

const viewports = [
  {name: 'mobile', width: 390, height: 844},
  {name: 'tablet', width: 1024, height: 768},
  {name: 'desktop', width: 1440, height: 900}
];
const assignments = [1, 2, 3, 4].map(number => ({id: `a${number}`, measurementId: `m${number}`, coreDeviceId: 'igrill-2', probeChannel: number, startedAt: '2026-09-14T09:30:00Z', endedAt: null}));
const cook = {id: 'cook-1', name: 'Weekend BBQ', state: 'active', startedAt: '2026-09-14T09:30:00Z', anticipatedServeAt: '2026-09-14T18:00:00Z', servedAt: null, closedAt: null, activeAlerts: [], assignments, cookers: [{id: 'kettle', name: 'Weber Kettle', profileId: 'p1'}, {id: 'wsm', name: 'WSM 57', profileId: 'p2'}], foodItems: [{id: 'chicken', name: 'Chicken'}, {id: 'pork', name: 'Pork Shoulder'}], measurements: [
  {id: 'm1', cookId: 'cook-1', label: 'Kettle ambient', kind: 'cooker', cookerId: 'kettle', foodItemId: null, targetTemperatureC: null, rangeMinC: 180, rangeMaxC: 200, approachingMarginC: 3, rangePersistenceSeconds: 60, currentTemperatureC: 182, currentObservedAt: '2026-09-14T13:42:00Z', available: true, interpretedState: 'in_range', trendCPerHour: 0},
  {id: 'm2', cookId: 'cook-1', label: 'Chicken', kind: 'food', cookerId: 'kettle', foodItemId: 'chicken', targetTemperatureC: 74, rangeMinC: null, rangeMaxC: null, approachingMarginC: 3, rangePersistenceSeconds: 60, currentTemperatureC: 71, currentObservedAt: '2026-09-14T13:42:00Z', available: true, interpretedState: 'approaching', trendCPerHour: 4},
  {id: 'm3', cookId: 'cook-1', label: 'WSM ambient', kind: 'cooker', cookerId: 'wsm', foodItemId: null, targetTemperatureC: null, rangeMinC: 120, rangeMaxC: 135, approachingMarginC: 3, rangePersistenceSeconds: 60, currentTemperatureC: 126, currentObservedAt: '2026-09-14T13:42:00Z', available: true, interpretedState: 'in_range', trendCPerHour: 0},
  {id: 'm4', cookId: 'cook-1', label: 'Pork shoulder', kind: 'food', cookerId: 'wsm', foodItemId: 'pork', targetTemperatureC: 93, rangeMinC: null, rangeMaxC: null, approachingMarginC: 3, rangePersistenceSeconds: 60, currentTemperatureC: 68, currentObservedAt: '2026-09-14T13:42:00Z', available: true, interpretedState: 'heating', trendCPerHour: 2}
]};
const closedCook = {...cook, id: 'closed-1', name: 'Saturday Brisket', state: 'closed', closedAt: '2026-09-13T20:00:00Z'};
const system = {product: 'Pitblu', version: '0.3.0', activeCook: {id: cook.id, name: cook.name, state: cook.state}, latestCook: {id: cook.id, name: cook.name, state: cook.state}, core: {available: true, lastError: null, devices: [{deviceId: 'igrill-2', friendlyName: 'iGrill 2', probes: [1, 2, 3, 4].map((probe, index) => ({probe, available: true, present: true, fresh: true, temperatureC: [182, 71, 126, 68][index]})), battery: {available: true, fresh: true, percentage: 82}}]}};

async function mock(page: Page, active = true) {
  await page.addInitScript(() => { Date.now = () => new Date('2026-09-14T18:41:00Z').getTime(); });
  await page.addInitScript(() => sessionStorage.setItem('pitblu-operator-token', 'visual-test-token'));
  await page.route('**/api/v1/events', route => route.fulfill({status: 200, contentType: 'text/event-stream', body: ''}));
  await page.route('**/api/v1/**', route => {
    const path = new URL(route.request().url()).pathname;
    let body: unknown = [];
    if (path === '/api/v1/system') body = active ? system : {...system, activeCook: null, latestCook: closedCook};
    else if (path === '/api/v1/cooker-profiles') body = [{id: 'p1', name: 'Weber Kettle', description: 'Charcoal', createdAt: '2026-01-01T00:00:00Z'}, {id: 'p2', name: 'WSM 57', description: 'Low and slow', createdAt: '2026-01-01T00:00:00Z'}];
    else if (path === '/api/v1/cooks') body = [closedCook];
    else if (path === '/api/v1/thermometer') body = {core: {...system.core, state: 'connected', liveEvents: true, lastSuccessfulContact: '2026-09-14T14:40:00Z'}, devices: system.core.devices.map(device => ({...device, model: 'igrill-v202', observedState: 'polling', automaticReconnection: true}))};
    else if (path === '/api/v1/cooks/cook-1') body = cook;
    else if (path.includes('/telemetry')) body = cook.measurements.flatMap((measurement, index) => [0, 1, 2, 3].map(step => ({measurementId: measurement.id, temperatureC: Number(measurement.currentTemperatureC) - (3 - step) * (index + 1), observedAt: `2026-09-14T${10 + step}:00:00Z`, available: true})));
    else if (path.endsWith('/events')) body = [{id: 'e1', cookId: 'cook-1', type: 'added_fuel', note: null, occurredAt: '2026-09-14T12:18:00Z'}, {id: 'e2', cookId: 'cook-1', type: 'wrapped', note: 'Wrapped pork shoulder', occurredAt: '2026-09-14T14:36:00Z'}];
    return route.fulfill({status: 200, contentType: 'application/json', body: JSON.stringify(body)});
  });
}

for (const viewport of viewports) {
  test(`active Cook ${viewport.name}`, async ({page}) => { await page.setViewportSize(viewport); await mock(page); await page.goto('/'); await expect(page.getByRole('heading', {name: 'Weekend BBQ'})).toBeVisible(); await page.addStyleTag({content: 'header time {visibility:hidden!important}'}); await expect(page).toHaveScreenshot(`active-cook-${viewport.name}.png`, {animations: 'disabled', maxDiffPixels: 150}); });
  test(`Start Cook ${viewport.name}`, async ({page}) => { await page.setViewportSize(viewport); await mock(page, false); await page.goto('/'); await page.getByRole('button', {name: /start a cook/i}).click(); await expect(page.getByRole('heading', {name: 'Set up the probes'})).toBeVisible(); await page.addStyleTag({content: 'header time {visibility:hidden!important}'}); await expect(page).toHaveScreenshot(`start-cook-${viewport.name}.png`, {animations: 'disabled'}); });
  test(`Journal ${viewport.name}`, async ({page}) => { await page.setViewportSize(viewport); await mock(page); await page.goto('/?view=history'); await expect(page.getByRole('heading', {name: 'Your cooking journal'})).toBeVisible(); await page.addStyleTag({content: 'header time {visibility:hidden!important}'}); await expect(page).toHaveScreenshot(`journal-${viewport.name}.png`, {animations: 'disabled'}); });
  test(`More ${viewport.name}`, async ({page}) => { await page.setViewportSize(viewport); await mock(page); await page.goto('/?view=more'); await expect(page.getByRole('heading', {name: 'App configuration'})).toBeVisible(); await page.addStyleTag({content: 'header time {visibility:hidden!important}'}); await expect(page).toHaveScreenshot(`more-${viewport.name}.png`, {animations: 'disabled'}); });
  test(`Cook setup ${viewport.name}`, async ({page}) => { await page.setViewportSize(viewport); await mock(page); await page.goto('/'); await page.getByRole('button', {name: 'Edit Weber Kettle'}).click(); await expect(page.getByRole('heading', {name: 'Set up the cook'})).toBeVisible(); await page.addStyleTag({content: 'header time {visibility:hidden!important}'}); await expect(page).toHaveScreenshot(`cook-setup-${viewport.name}.png`, {animations: 'disabled', fullPage: true}); });
  test(`Thermometer ${viewport.name}`, async ({page}) => { await page.setViewportSize(viewport); await mock(page); await page.goto('/?view=thermometer'); await expect(page.getByRole('heading', {name: 'Thermometer'})).toBeVisible(); await page.addStyleTag({content: 'header time {visibility:hidden!important}'}); await expect(page).toHaveScreenshot(`thermometer-${viewport.name}.png`, {animations: 'disabled', fullPage: true}); });
}
