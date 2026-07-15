import { chromium } from 'playwright';
import assert from 'node:assert/strict';

const baseURL = process.env.BASE_URL || 'http://127.0.0.1:8000';
const browser = await chromium.launch({headless: true});
try {
  const page = await browser.newPage({viewport: {width: 1440, height: 900}});
  await page.goto(baseURL, {waitUntil: 'networkidle'});
  await page.waitForFunction(() => document.querySelector('#model').options.length > 5);
  const viewportFit = await page.evaluate(() => ({
    body: document.body.scrollHeight,
    viewport: innerHeight,
    workspaceBottom: Math.round(document.querySelector('.workspace').getBoundingClientRect().bottom),
  }));
  assert.ok(viewportFit.body <= viewportFit.viewport, JSON.stringify(viewportFit));
  assert.ok(viewportFit.workspaceBottom <= viewportFit.viewport, JSON.stringify(viewportFit));

  await page.click('[data-example="product"]');
  await page.click('#run');
  await page.waitForSelector('#result:not([hidden])');
  assert.match(await page.textContent('#trust-badge'), /精确且已降 Token/);
  assert.ok(Number((await page.textContent('#original-tokens')).replaceAll(',', '')) > Number((await page.textContent('#compressed-tokens')).replaceAll(',', '')));
  await page.click('[data-result-tab="cost"]');
  assert.ok(await page.locator('[data-result-pane="cost"]').isVisible());
  await page.click('[data-result-tab="changes"]');
  assert.ok(await page.locator('#change-list li').count() > 0);
  assert.equal(await page.evaluate(() => document.body.scrollHeight <= innerHeight), true);
  await page.screenshot({path: '/tmp/prompt-workbench-desktop.png'});

  await page.click('#tokenizer-button');
  await page.waitForSelector('.tokenizer-item');
  assert.equal(await page.locator('.tokenizer-state.ready').count(), 8);
  await page.click('[data-close="tokenizer-dialog"]');

  await page.setViewportSize({width: 900, height: 700});
  await page.click('#back-editor');
  assert.ok(await page.locator('.editor-card').isVisible());
  await page.click('#run');
  await page.waitForSelector('body.show-result');
  assert.ok(await page.locator('.result-card').isVisible());
  assert.equal(await page.evaluate(() => document.body.scrollHeight <= innerHeight), true);
  await page.screenshot({path: '/tmp/prompt-workbench-compact.png'});
  console.log('desktop-fit: ok');
  console.log('compact-fit: ok');
  console.log('result-tabs: ok');
  console.log('tokenizers-ready: 8/8');
} finally {
  await browser.close();
}
