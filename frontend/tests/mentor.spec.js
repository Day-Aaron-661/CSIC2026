import { test as base, expect } from '@playwright/test';

// Matches both the list (/api/questions?status=pending) and review (/api/questions/{id}/review) URLs.
const API = /\/api\/questions/;
const CORS = {
  'access-control-allow-origin': 'http://localhost:5173',
  'access-control-allow-headers': 'Content-Type',
  'access-control-allow-methods': 'GET, POST, OPTIONS',
};
const PLACEHOLDER = '[DEMO PLACEHOLDER — NOT AI GENERATED] This question has been submitted for mentor review.';

// Helpers follow frontend/tests/newcomer.spec.js; they are copied rather than shared
// so this PR does not modify C's test file.
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
    ai_answer: PLACEHOLDER,
    status: 'pending',
    reviewed_answer: null,
    reviewer: null,
    created_at: '2026-11-20T01:00:00+00:00',
    reviewed_at: null,
    ...overrides,
  };
}

function approved(item, body) {
  return { ...item, status: 'approved', reviewed_answer: body.answer, reviewer: body.reviewer, reviewed_at: '2026-11-20T01:05:00+00:00' };
}

function gate() {
  let release;
  const promise = new Promise(resolve => { release = resolve; });
  return { promise, release };
}

async function reply(route, data, status = 200) {
  await route.fulfill({ status, headers: CORS, contentType: 'application/json', body: JSON.stringify(data) });
}

function isMentorRead(request) {
  return request.method() === 'GET' && new URL(request.url()).searchParams.get('status') === 'pending';
}

// handler receives only Mentor traffic; Newcomer's initial history read gets an empty list.
async function mockApi(page, handler) {
  await page.route(API, async route => {
    const request = route.request();
    if (request.method() === 'OPTIONS') {
      await route.fulfill({ status: 204, headers: CORS });
      return;
    }
    if (request.method() === 'GET' && !isMentorRead(request)) {
      await reply(route, []);
      return;
    }
    await handler(route);
  });
}

async function openMentor(page) {
  await page.goto('/');
  await page.getByRole('button', { name: 'Mentor', exact: true }).click();
  await expect(page.getByRole('heading', { name: /Mentor — Review queue/ })).toBeVisible();
}

function card(page, text) {
  return page.getByRole('article').filter({ has: page.getByRole('heading', { name: text, exact: true }) });
}

test('pre-fills the AI draft, lets the mentor edit it, and approves exactly what was submitted', async ({ page }) => {
  let pending = [question(1)];
  const bodies = [];
  await mockApi(page, async route => {
    if (route.request().method() === 'POST') {
      const body = route.request().postDataJSON();
      bodies.push(body);
      const item = pending.find(existing => existing.id === 1);
      pending = [];
      await reply(route, approved(item, body));
    } else await reply(route, pending);
  });
  await openMentor(page);
  const review = card(page, 'Project question 1');
  const answer = review.getByLabel('Mentor verified answer');
  await expect(answer).toHaveValue(PLACEHOLDER);
  await expect(review.getByText(/unchanged from AI draft/)).toBeVisible();
  await expect(review.getByRole('button', { name: 'Reset to AI draft' })).toBeDisabled();

  await page.getByLabel('Reviewer (demo display name)').fill('Test mentor');
  await answer.fill('  Start with README.md, then run both servers.  ');
  await expect(review.getByText(/· edited/)).toBeVisible();
  await review.getByRole('button', { name: 'Approve answer' }).click();

  await expect(review).toHaveCount(0);
  await expect(page.getByText('Question #1 approved. Newcomers now see your reviewed answer.')).toBeVisible();
  expect(bodies).toEqual([{ answer: 'Start with README.md, then run both servers.', reviewer: 'Test mentor' }]);
});

test('disables approval for a blank answer or reviewer, and can reset to the AI draft', async ({ page }) => {
  await mockApi(page, route => reply(route, [question(2, { ai_answer: 'Original AI draft' })]));
  await openMentor(page);
  const review = card(page, 'Project question 2');
  const answer = review.getByLabel('Mentor verified answer');
  const approve = review.getByRole('button', { name: 'Approve answer' });
  await expect(approve).toBeEnabled();

  await answer.fill('   ');
  await expect(approve).toBeDisabled();
  await review.getByRole('button', { name: 'Reset to AI draft' }).click();
  await expect(answer).toHaveValue('Original AI draft');
  await expect(approve).toBeEnabled();

  await page.getByLabel('Reviewer (demo display name)').fill('  ');
  await expect(approve).toBeDisabled();
  await expect(page.getByRole('alert')).toContainText('Enter a reviewer name');
  await expect(answer).toHaveAttribute('maxlength', '10000');
});

test('sends one approval for a double click and locks the card while it is pending', async ({ page }) => {
  const response = gate();
  let posts = 0;
  let pending = [question(3)];
  await mockApi(page, async route => {
    if (route.request().method() === 'POST') {
      posts += 1;
      await response.promise;
      const item = pending[0];
      pending = [];
      await reply(route, approved(item, route.request().postDataJSON()));
    } else await reply(route, pending);
  });
  await openMentor(page);
  const review = card(page, 'Project question 3');
  await review.getByLabel('Mentor verified answer').fill('Verified answer');
  await review.getByRole('button', { name: 'Approve answer' }).evaluate(button => { button.click(); button.click(); });
  await expect.poll(() => posts).toBe(1);
  await expect(review.getByRole('button', { name: /Approving/ })).toBeDisabled();
  await expect(review.getByLabel('Mentor verified answer')).toBeDisabled();
  response.release();
  await expect(review).toHaveCount(0);
  expect(posts).toBe(1);
});

test('keeps the typed answer after a failed approval and allows an explicit retry', async ({ page }) => {
  let fail = true;
  let posts = 0;
  let pending = [question(4)];
  await mockApi(page, async route => {
    if (route.request().method() === 'POST') {
      posts += 1;
      if (fail) {
        await reply(route, { detail: 'Temporarily unavailable' }, 503);
        return;
      }
      const item = pending[0];
      pending = [];
      await reply(route, approved(item, route.request().postDataJSON()));
    } else await reply(route, pending);
  });
  await openMentor(page);
  const review = card(page, 'Project question 4');
  const answer = review.getByLabel('Mentor verified answer');
  await answer.fill('Answer worth keeping');
  await review.getByRole('button', { name: 'Approve answer' }).click();
  await expect(review.getByRole('alert')).toContainText('Approval was not confirmed (Temporarily unavailable)');
  await expect(answer).toHaveValue('Answer worth keeping');
  expect(posts).toBe(1);

  fail = false;
  await review.getByRole('button', { name: 'Approve answer' }).click();
  await expect(review).toHaveCount(0);
  expect(posts).toBe(2);
});

test('explains a 409 when another mentor approved the question first', async ({ page }) => {
  let pending = [question(5)];
  await mockApi(page, async route => {
    if (route.request().method() === 'POST') {
      pending = [];
      await reply(route, { detail: 'Already reviewed' }, 409);
    } else await reply(route, pending);
  });
  await openMentor(page);
  const review = card(page, 'Project question 5');
  await review.getByLabel('Mentor verified answer').fill('My late answer');
  await review.getByRole('button', { name: 'Approve answer' }).click();
  await expect(review).toHaveCount(0);
  await expect(page.getByText(/Question #5 was already reviewed elsewhere/)).toBeVisible();
});

test('notifies only about edited questions that were reviewed elsewhere', async ({ page }) => {
  let pending = [question(6), question(7)];
  await mockApi(page, route => reply(route, pending));
  await openMentor(page);
  await card(page, 'Project question 6').getByLabel('Mentor verified answer').fill('Work in progress');
  await expect(card(page, 'Project question 7')).toBeVisible();

  pending = [];
  await page.getByRole('button', { name: 'Refresh queue' }).click();
  await expect(page.getByText('No pending questions')).toBeVisible();
  await expect(page.getByText(/Question #6 was already reviewed elsewhere/)).toBeVisible();
  await expect(page.getByText(/Question #7 was already reviewed elsewhere/)).toHaveCount(0);
  await page.getByRole('button', { name: 'Dismiss' }).click();
  await expect(page.getByText(/Question #6 was already reviewed elsewhere/)).toHaveCount(0);
});

test('polling adds new questions without overwriting a draft in progress', async ({ page }) => {
  await page.clock.install();
  let pending = [question(8)];
  await mockApi(page, route => reply(route, pending));
  await openMentor(page);
  const first = card(page, 'Project question 8').getByLabel('Mentor verified answer');
  await first.fill('Half-written answer');

  pending = [question(9, { ai_answer: 'Draft for question 9' }), question(8)];
  await page.clock.fastForward(5_100);
  await expect(card(page, 'Project question 9')).toBeVisible();
  await expect(card(page, 'Project question 9').getByLabel('Mentor verified answer')).toHaveValue('Draft for question 9');
  await expect(first).toHaveValue('Half-written answer');
});

test('pauses polling while hidden, resumes when visible, and stops after leaving the mentor view', async ({ page }) => {
  await page.clock.install();
  let mentorReads = 0;
  await mockApi(page, async route => {
    mentorReads += 1;
    await reply(route, [question(10)]);
  });
  await openMentor(page);
  await expect(card(page, 'Project question 10')).toBeVisible();

  await page.evaluate(() => {
    Object.defineProperty(document, 'hidden', { configurable: true, get: () => true });
    document.dispatchEvent(new Event('visibilitychange'));
  });
  const hiddenReads = mentorReads;
  await page.clock.fastForward(16_000);
  expect(mentorReads).toBe(hiddenReads);

  await page.evaluate(() => {
    Object.defineProperty(document, 'hidden', { configurable: true, get: () => false });
    document.dispatchEvent(new Event('visibilitychange'));
  });
  await expect.poll(() => mentorReads).toBeGreaterThan(hiddenReads);

  await page.getByRole('button', { name: 'Newcomer', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Shared question history' })).toBeVisible();
  const unmountedReads = mentorReads;
  await page.clock.fastForward(16_000);
  expect(mentorReads).toBe(unmountedReads);
});

test('the demo placeholder can still be approved unchanged (placeholder check is disabled)', async ({ page }) => {
  const bodies = [];
  let pending = [question(11)];
  await mockApi(page, async route => {
    if (route.request().method() === 'POST') {
      bodies.push(route.request().postDataJSON());
      const item = pending[0];
      pending = [];
      await reply(route, approved(item, bodies[0]));
    } else await reply(route, pending);
  });
  await openMentor(page);
  const review = card(page, 'Project question 11');
  await expect(review.getByRole('button', { name: 'Approve answer' })).toBeEnabled();
  await review.getByRole('button', { name: 'Approve answer' }).click();
  await expect(review).toHaveCount(0);
  expect(bodies).toEqual([{ answer: PLACEHOLDER, reviewer: 'Mentor' }]);
});

test('long questions and literal markup fit a mobile viewport without executing HTML', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 375, height: 812 });
  const literal = '<img src=x onerror="window.unexpectedHtml = true">';
  const longText = `How should I review ${'a'.repeat(180)}?`;
  await mockApi(page, route => reply(route, [question(12, { question: longText, ai_answer: literal })]));
  await openMentor(page);
  const review = card(page, longText);
  await expect(review.getByRole('paragraph').filter({ hasText: literal })).toHaveText(literal);
  await expect(review.getByLabel('Mentor verified answer')).toHaveValue(literal);
  expect(await page.evaluate(() => window.unexpectedHtml)).toBeUndefined();
  const width = await page.evaluate(() => ({ content: document.documentElement.scrollWidth, viewport: window.innerWidth }));
  expect(width.content).toBeLessThanOrEqual(width.viewport);
  await page.screenshot({ path: testInfo.outputPath('mentor-mobile.png'), fullPage: true });
});
