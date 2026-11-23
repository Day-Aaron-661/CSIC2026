import { test as base, expect } from '@playwright/test';

const API = 'http://localhost:8000/api/questions';
const CORS = {
  'access-control-allow-origin': 'http://localhost:5173',
  'access-control-allow-headers': 'Content-Type',
  'access-control-allow-methods': 'GET, POST, OPTIONS',
};

// In particular, catch JSX runtime errors that a successful Vite build misses.
const test = base.extend({
  runtimeErrors: [async ({ page }, use) => {
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await use(errors);
    expect(errors, 'browser JavaScript errors').toEqual([]);
  }, { auto: true }],
});

function question(id, overrides = {}) {
  return {
    id,
    question: `Project question ${id}`,
    ai_answer: '[DEMO PLACEHOLDER — NOT AI GENERATED] Awaiting a mentor answer.',
    status: 'pending',
    reviewed_answer: null,
    reviewer: null,
    created_at: '2026-11-19T01:00:00+00:00',
    reviewed_at: null,
    ...overrides,
  };
}

function gate() {
  let release;
  const promise = new Promise(resolve => { release = resolve; });
  return { promise, release };
}

async function reply(route, data, status = 200) {
  await route.fulfill({ status, headers: CORS, contentType: 'application/json', body: JSON.stringify(data) });
}

async function mockApi(page, handler) {
  await page.route(`${API}*`, async route => {
    if (route.request().method() === 'OPTIONS') {
      await route.fulfill({ status: 204, headers: CORS });
      return;
    }
    await handler(route);
  });
}

function card(page, text) {
  return page.getByRole('article').filter({ has: page.getByRole('heading', { name: text, exact: true }) });
}

test('a second browser can review a question and the newcomer updates automatically', async ({ page, browser }, testInfo) => {
  const mentorContext = await browser.newContext();
  const mentor = await mentorContext.newPage();
  const mentorErrors = [];
  mentor.on('pageerror', error => mentorErrors.push(error.message));
  const prompt = `Where do I start? Browser check ${Date.now()}`;
  try {
    await page.goto('/');
    await page.getByLabel('Project question', { exact: true }).fill(prompt);
    await page.getByRole('button', { name: 'Submit question', exact: true }).click();
    const answer = card(page, prompt);
    await expect(answer.getByText('Awaiting mentor review', { exact: true })).toBeVisible();

    await mentor.goto('http://localhost:5173');
    await mentor.getByRole('button', { name: 'Mentor', exact: true }).click();
    await mentor.getByLabel('Reviewer (demo display name)').fill('Browser test mentor');
    const review = card(mentor, prompt);
    await review.getByLabel('Mentor verified answer').fill('Start with README.md, then run both local servers.');
    await review.getByRole('button', { name: 'Approve answer' }).click();
    await expect(review).toHaveCount(0);

    await page.bringToFront();
    await expect(answer.getByRole('heading', { name: 'Mentor-reviewed answer' })).toBeVisible({ timeout: 12_000 });
    await expect(answer.getByText('Start with README.md, then run both local servers.')).toBeVisible();
    await answer.getByText('Original draft', { exact: true }).click();
    await expect(answer.getByText(/DEMO PLACEHOLDER/)).toBeVisible();
    await page.screenshot({ path: testInfo.outputPath('newcomer-reviewed-desktop.png'), fullPage: true });
    expect(mentorErrors).toEqual([]);
  } finally {
    await mentorContext.close();
  }
});

test('shows loading before an honest empty history', async ({ page }) => {
  const response = gate();
  await mockApi(page, async route => { await response.promise; await reply(route, []); });
  await page.goto('/');
  await expect(page.getByText(/Loading questions/)).toBeVisible();
  await expect(page.getByText(/No questions yet/)).toHaveCount(0);
  response.release();
  await expect(page.getByText(/No questions yet/)).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Shared question history' })).toBeVisible();
});

test('rejects blank input and permits only one submission while the request is pending', async ({ page }) => {
  const response = gate();
  let posts = 0;
  await mockApi(page, async route => {
    if (route.request().method() === 'POST') {
      posts += 1;
      await response.promise;
      await reply(route, question(10, route.request().postDataJSON()), 201);
    } else await reply(route, []);
  });
  await page.goto('/');
  const input = page.getByLabel('Project question', { exact: true });
  const submit = page.getByRole('button', { name: 'Submit question', exact: true });
  await input.fill('   ');
  await expect(submit).toBeDisabled();
  await expect(input).toHaveAttribute('maxlength', '2000');
  await input.fill('  How do I run the project?  ');
  await submit.dblclick();
  await expect.poll(() => posts).toBe(1);
  await expect(input).toBeDisabled();
  await expect(page.getByRole('button', { name: /Submitting/ })).toBeDisabled();
  response.release();
  await expect(card(page, 'How do I run the project?')).toBeVisible();
  await expect(input).toHaveValue('');
  expect(posts).toBe(1);
});

test('keeps a failed submission draft and lets the user retry explicitly', async ({ page }) => {
  let fail = true;
  let posts = 0;
  await mockApi(page, async route => {
    if (route.request().method() === 'POST') {
      posts += 1;
      await reply(route, fail ? { detail: 'Temporarily unavailable' } : question(20, route.request().postDataJSON()), fail ? 503 : 201);
    } else await reply(route, []);
  });
  await page.goto('/');
  const input = page.getByLabel('Project question', { exact: true });
  await input.fill('Where are the project docs?');
  await page.getByRole('button', { name: 'Submit question', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Your draft is still here');
  await expect(input).toHaveValue('Where are the project docs?');
  expect(posts).toBe(1);
  fail = false;
  await page.getByRole('button', { name: 'Submit question', exact: true }).click();
  await expect(card(page, 'Where are the project docs?')).toBeVisible();
  await expect(input).toHaveValue('');
  expect(posts).toBe(2);
});

test('a saved question remains visible when the subsequent history refresh fails', async ({ page }) => {
  let saved = false;
  let posts = 0;
  await mockApi(page, async route => {
    if (route.request().method() === 'POST') {
      posts += 1;
      saved = true;
      await reply(route, question(30, route.request().postDataJSON()), 201);
    } else await reply(route, saved ? { detail: 'Temporary read failure' } : [], saved ? 503 : 200);
  });
  await page.goto('/');
  await expect(page.getByText(/No questions yet/)).toBeVisible();
  await page.getByLabel('Project question', { exact: true }).fill('Saved despite a later read failure');
  await page.getByRole('button', { name: 'Submit question', exact: true }).click();
  await expect(card(page, 'Saved despite a later read failure')).toBeVisible();
  await page.getByRole('button', { name: /^Reviewed \(/ }).click();
  await expect(card(page, 'Saved despite a later read failure')).toHaveCount(0);
  await page.getByRole('link', { name: 'View question' }).click();
  await expect(card(page, 'Saved despite a later read failure')).toBeVisible();
  await page.getByRole('button', { name: 'Refresh answers', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Could not refresh questions');
  await expect(card(page, 'Saved despite a later read failure')).toBeVisible();
  expect(posts).toBe(1);
});

test('recovers from an initial read failure and preserves the last good history during later failures', async ({ page }) => {
  let fail = true;
  await mockApi(page, route => reply(route, fail ? { detail: 'Unavailable' } : [question(40)], fail ? 503 : 200));
  await page.goto('/');
  await expect(page.getByRole('alert')).toContainText('Could not load questions');
  await expect(page.getByText(/No questions yet/)).toHaveCount(0);
  fail = false;
  await page.getByRole('button', { name: 'Refresh answers', exact: true }).click();
  await expect(card(page, 'Project question 40')).toBeVisible();
  fail = true;
  await page.getByRole('button', { name: 'Refresh answers', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Could not refresh questions');
  await expect(card(page, 'Project question 40')).toBeVisible();
  fail = false;
  await page.getByRole('button', { name: 'Refresh answers', exact: true }).click();
  await expect(page.getByRole('alert')).toHaveCount(0);
});

test('a stale list response cannot remove a question just submitted', async ({ page }) => {
  const oldRead = gate();
  const oldReadSettled = gate();
  let holdRead = false;
  let pendingRead = false;
  await mockApi(page, async route => {
    if (route.request().method() === 'POST') {
      await reply(route, question(50, route.request().postDataJSON()), 201);
    } else {
      if (holdRead) {
        pendingRead = true;
        await oldRead.promise;
        try { await reply(route, []); }
        finally { oldReadSettled.release(); }
      } else await reply(route, []);
    }
  });
  await page.goto('/');
  await expect(page.getByText(/No questions yet/)).toBeVisible();
  holdRead = true;
  await page.getByRole('button', { name: 'Refresh answers', exact: true }).click();
  await expect.poll(() => pendingRead).toBe(true);
  await page.getByLabel('Project question', { exact: true }).fill('Keep this newly saved question');
  await page.getByRole('button', { name: 'Submit question', exact: true }).click();
  await expect(card(page, 'Keep this newly saved question')).toBeVisible();
  oldRead.release();
  await oldReadSettled.promise;
  // Let a late response reach React and commit before checking the visible result.
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  await expect(card(page, 'Keep this newly saved question')).toBeVisible();
});

test('filters review states and keeps the original draft separate from the reviewed answer', async ({ page }) => {
  const approved = question(62, {
    status: 'approved',
    ai_answer: 'Unreviewed original draft',
    reviewed_answer: 'The mentor checked this answer against the README.',
    reviewer: 'Test mentor',
    reviewed_at: '2026-11-19T01:05:00+00:00',
  });
  await mockApi(page, route => reply(route, [approved, question(61)]));
  await page.goto('/');
  await page.getByRole('button', { name: /^Reviewed \(/ }).click();
  await expect(card(page, 'Project question 61')).toHaveCount(0);
  const reviewed = card(page, 'Project question 62');
  await expect(reviewed.getByText('The mentor checked this answer against the README.')).toBeVisible();
  await expect(reviewed.getByText('Unreviewed original draft')).not.toBeVisible();
  await reviewed.getByText('Original draft', { exact: true }).click();
  await expect(reviewed.getByText('Unreviewed original draft')).toBeVisible();
  await page.getByRole('button', { name: /^Awaiting review \(/ }).click();
  await expect(card(page, 'Project question 62')).toHaveCount(0);
  await expect(card(page, 'Project question 61').getByRole('heading', { name: 'Draft answer · not reviewed' })).toBeVisible();
  await expect(page.getByRole('button', { name: /^Awaiting review \(/ })).toHaveAttribute('aria-pressed', 'true');
});

test('pauses hidden-page polling, resumes when visible, and stops after leaving the newcomer view', async ({ page }) => {
  await page.clock.install();
  let newcomerReads = 0;
  await mockApi(page, async route => {
    if (!new URL(route.request().url()).searchParams.has('status')) newcomerReads += 1;
    await reply(route, [question(70)]);
  });
  await page.goto('/');
  await expect(card(page, 'Project question 70')).toBeVisible();
  await page.evaluate(() => {
    Object.defineProperty(document, 'hidden', { configurable: true, get: () => true });
    document.dispatchEvent(new Event('visibilitychange'));
  });
  const hiddenReads = newcomerReads;
  await page.clock.fastForward(16_000);
  expect(newcomerReads).toBe(hiddenReads);
  await page.evaluate(() => {
    Object.defineProperty(document, 'hidden', { configurable: true, get: () => false });
    document.dispatchEvent(new Event('visibilitychange'));
  });
  await expect.poll(() => newcomerReads).toBeGreaterThan(hiddenReads);
  await page.getByRole('button', { name: 'Mentor', exact: true }).click();
  await expect(page.getByRole('heading', { name: /Mentor — Review queue/ })).toBeVisible();
  const unmountedReads = newcomerReads;
  await page.clock.fastForward(16_000);
  expect(newcomerReads).toBe(unmountedReads);
});

test('long questions and literal markup fit a mobile viewport without executing HTML', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 375, height: 812 });
  const literal = '<img src=x onerror="window.unexpectedHtml = true">';
  const longText = `How should I read ${'a'.repeat(180)}?`;
  await mockApi(page, route => reply(route, [question(80, { question: longText, ai_answer: literal })]));
  await page.goto('/');
  await expect(card(page, longText).getByText(literal, { exact: true })).toBeVisible();
  expect(await page.evaluate(() => window.unexpectedHtml)).toBeUndefined();
  const width = await page.evaluate(() => ({ content: document.documentElement.scrollWidth, viewport: window.innerWidth }));
  expect(width.content).toBeLessThanOrEqual(width.viewport);
  await page.screenshot({ path: testInfo.outputPath('newcomer-mobile.png'), fullPage: true });
});


test('shows draft citations without claiming mentor verification, including excerpts and locators', async ({ page }) => {
  const answer = question(90, {
    ai_status: 'ok',
    ai_answer: 'Run the backend using the documented command. [1]',
    citations: [
      { source: 'README.md', snippet: 'Run uvicorn from the project root.', locator: 'Getting started' },
      { source: 'docs/setup.md', snippet: null, locator: null },
    ],
  });
  await mockApi(page, route => reply(route, [answer]));
  await page.goto('/');
  const result = card(page, 'Project question 90');
  await expect(result.getByRole('heading', { name: 'Sources for AI draft · not independently verified' })).toBeVisible();
  await expect(result.getByText('README.md', { exact: true })).toBeVisible();
  await expect(result.getByText('docs/setup.md', { exact: true })).toBeVisible();
  await expect(result.getByText('Getting started', { exact: false })).toBeVisible();
  await result.getByText('Show source excerpt').click();
  await expect(result.getByText('Run uvicorn from the project root.')).toBeVisible();
  await expect(result.getByText('Mentor reviewed', { exact: true })).toHaveCount(0);
});

test('shows failed AI status honestly and tolerates missing or empty citations', async ({ page }) => {
  const failed = question(91, { ai_status: 'failed', ai_answer: '[AI DRAFT UNAVAILABLE] Try later.', citations: [] });
  const placeholder = question(92, { ai_status: 'placeholder', citations: [] });
  const legacy = question(93);
  await mockApi(page, route => reply(route, [failed, placeholder, legacy]));
  await page.goto('/');
  await expect(card(page, 'Project question 91').getByRole('heading', { name: 'AI draft unavailable' })).toBeVisible();
  await expect(card(page, 'Project question 91').getByText(/still waiting for mentor review/)).toBeVisible();
  await expect(card(page, 'Project question 91').getByRole('heading', { name: /Sources for AI draft/ })).toHaveCount(0);
  await expect(card(page, 'Project question 92').getByRole('heading', { name: 'Demo placeholder · not AI generated' })).toBeVisible();
  await expect(card(page, 'Project question 92').getByText('No document citations were provided for this AI draft.')).toBeVisible();
  await expect(card(page, 'Project question 93').getByText('Sources are not available with this backend yet.')).toBeVisible();
});

test('retries a lost submission with the same request id and changes it for new question text', async ({ page }) => {
  const requests = [];
  let fail = true;
  await mockApi(page, async route => {
    if (route.request().method() !== 'POST') return reply(route, []);
    const body = route.request().postDataJSON();
    requests.push(body);
    await reply(route, fail ? { detail: 'Transient server problem' } : question(requests.length + 100, body), fail ? 503 : 200);
  });
  await page.goto('/');
  const input = page.getByLabel('Project question', { exact: true });
  const submit = page.getByRole('button', { name: 'Submit question', exact: true });
  await input.fill('How do I start locally?');
  await submit.click();
  await expect(page.getByRole('alert')).toContainText('Your draft is still here');
  expect(requests).toHaveLength(1);
  expect(requests[0].client_request_id).toMatch(/^[a-f0-9-]{36}$/i);
  await submit.click();
  await expect.poll(() => requests.length).toBe(2);
  expect(requests[1].client_request_id).toBe(requests[0].client_request_id);

  await input.fill('Where is the project README?');
  fail = false;
  await submit.click();
  await expect(card(page, 'Where is the project README?')).toBeVisible();
  expect(requests).toHaveLength(3);
  expect(requests[2].client_request_id).not.toBe(requests[0].client_request_id);

  await input.fill('Another new question');
  await submit.click();
  await expect(card(page, 'Another new question')).toBeVisible();
  expect(requests[3].client_request_id).not.toBe(requests[2].client_request_id);
});
