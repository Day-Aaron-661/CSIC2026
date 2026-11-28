/* Capture an actual GitHub Contributors page, not a generated graph.
 * If GitHub denies access or the page isn't ready, leave a failure log only.
 * Never use private credentials. */
const { chromium } = require('../tested-main/frontend/node_modules/@playwright/test');
const fs = require('node:fs');
const path = require('node:path');

(async () => {
  const out = path.resolve('audit-results');
  fs.mkdirSync(out, { recursive: true });
  const url = 'https://github.com/Day-Aaron-661/CSIC2026/graphs/contributors';
  let browser;
  try {
    browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
    const page = await browser.newPage({
      viewport: { width: 1440, height: 900 },
      deviceScaleFactor: 1,
      colorScheme: 'light',
    });
    const response = await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 45000 });
    await page.waitForTimeout(8000);
    const body = (await page.locator('body').innerText({ timeout: 8000 })).slice(0, 12000);
    const title = await page.title();
    const valid = response?.status() === 200
      && body.includes('Contributors')
      && (body.includes('CSIC2026') || title.includes('CSIC2026'))
      && !body.includes('This repository is empty');
    if (!valid) {
      console.log('Contributor graph not verified: HTTP', response?.status(), 'title', title);
      fs.writeFileSync(path.join(out, 'contributor-capture-status.txt'),
        'Not captured: contributor page did not satisfy verification.\n' +
        'HTTP=' + response?.status() + '\nTitle=' + title + '\n');
      return;
    }
    await page.screenshot({ path: path.join(out, 'github-contributors-main.png'), fullPage: true, animations: 'disabled' });
    fs.writeFileSync(path.join(out, 'contributor-capture-status.txt'),
      'Source=' + url + '\nCaptured UTC=' + new Date().toISOString() + '\nHTTP=200\nPage title=' + title + '\n');
    console.log('Captured actual GitHub contributor page:', url);
  } catch (error) {
    console.log('Contributor screenshot unavailable:', error.name);
    fs.writeFileSync(path.join(out, 'contributor-capture-status.txt'),
      'Screenshot unavailable in CI; capture manually from the GitHub Insights page.\n');
  } finally {
    if (browser) await browser.close();
  }
})();
