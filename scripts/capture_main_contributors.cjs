/* Capture a GENUINE GitHub Insights -> Contributors page.
 * A loading spinner is not evidence. Poll the GitHub stats endpoint to warm
 * its cache and save a screenshot ONLY after actual graph data appears.
 */
const { chromium } = require('../tested-main/frontend/node_modules/@playwright/test');
const fs = require('node:fs');
const path = require('node:path');

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

(async () => {
  const out = path.resolve('audit-results');
  fs.mkdirSync(out, { recursive: true });
  const url = 'https://github.com/Day-Aaron-661/CSIC2026/graphs/contributors';
  const statsUrl = 'https://api.github.com/repos/Day-Aaron-661/CSIC2026/stats/contributors';
  let browser;
  const statuses = [];
  let contributors = null;
  try {
    // GitHub computes this graph asynchronously. 202 means "processing", not
    // "empty". We don't turn a loading screenshot into claimed evidence.
    for (let attempt = 0; attempt < 16; attempt++) {
      const headers = {
        'Accept': 'application/vnd.github+json',
        'User-Agent': 'CP2-evidence-check',
        'X-GitHub-Api-Version': '2022-11-28'
      };
      if (process.env.GH_TOKEN) headers.Authorization = 'Bearer ' + process.env.GH_TOKEN;
      const response = await fetch(statsUrl, { headers, signal: AbortSignal.timeout(15000) });
      statuses.push(response.status);
      console.log('GitHub contributor stats:', response.status, 'attempt', attempt + 1);
      if (response.status === 200) {
        contributors = await response.json();
        if (Array.isArray(contributors) && contributors.length) break;
      }
      if (response.status !== 202 && response.status !== 200) break;
      await sleep(6000);
    }
    if (Array.isArray(contributors) && contributors.length) {
      const meta = contributors.map(c => ({ login: c.author?.login || 'unlinked', commits: c.total }));
      fs.writeFileSync(path.join(out, 'github-contributor-statistics.json'),
        JSON.stringify({source: statsUrl, generated_utc: new Date().toISOString(), contributors: meta}, null, 2));
    }
    browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
    const page = await browser.newPage({
      viewport: { width: 1440, height: 900 },
      deviceScaleFactor: 1,
      colorScheme: 'light',
    });
    let response = await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 45000 });
    let text = '';
    for (let attempt = 0; attempt < 5; attempt++) {
      await page.waitForTimeout(6500);
      text = (await page.locator('body').innerText({ timeout: 10000 })).slice(0, 20000);
      if (text.includes('Contributions per week')
        && !text.includes('Crunching the latest data')
        && !text.includes('Hang tight')
        && (text.includes('commits') || text.includes('Commits'))) break;
      if (attempt !== 4) response = await page.reload({ waitUntil: 'domcontentloaded', timeout: 45000 });
    }
    const title = await page.title();
    const valid = response?.status() === 200
      && text.includes('Contributions per week')
      && !text.includes('Crunching the latest data')
      && !text.includes('Hang tight')
      && (text.includes('CSIC2026') || title.includes('CSIC2026'))
      && (text.includes('commits') || text.includes('Commits'));
    if (!valid) {
      console.log('No loaded GitHub graph: HTTP', response?.status(), 'title', title);
      fs.writeFileSync(path.join(out, 'contributor-capture-status.txt'),
        'NO VERIFIED GRAPH SCREENSHOT. GitHub Insights stayed in loading state.\n' +
        'Page=' + url + '\nStats HTTP statuses=' + statuses.join(',') + '\n');
      return;
    }
    await page.screenshot({ path: path.join(out, 'github-contributors-main.png'),
      fullPage: true, animations: 'disabled' });
    fs.writeFileSync(path.join(out, 'contributor-capture-status.txt'),
      'Source=' + url + '\nCaptured UTC=' + new Date().toISOString() +
      '\nStats HTTP=' + statuses.join(',') + '\nActual graph loaded (no spinner).\n');
    console.log('Captured REAL, fully loaded GitHub contributor graph:', url);
  } catch (error) {
    console.log('Contributor screenshot unavailable:', error.name);
    fs.writeFileSync(path.join(out, 'contributor-capture-status.txt'),
      'No verified screenshot; GitHub graph request failed.\n' +
      'Page=' + url + '\nStats HTTP=' + statuses.join(',') + '\n');
  } finally {
    if (browser) await browser.close();
  }
})();
