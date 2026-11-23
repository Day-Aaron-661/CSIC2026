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
  // The mentor's own attempt failed, so the notice does not claim who approved it.
  await expect(page.getByText(/Question #5 is no longer pending\. It may have been approved by you/)).toBeVisible();
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

// --- Review follow-up for #11: stalled approvals, concurrent approvals, notice wording ---

// clock.install() keeps time running, so a poll would fire within an expect timeout and hide a bug.
// Pausing a little ahead of now (no timer is due yet) stops polling for the rest of the test.
async function stopPolling(page) {
  await page.clock.pauseAt(Date.now() + 1_000);
}

function reviewId(request) {
  return Number(new URL(request.url()).pathname.match(/questions\/(\d+)\/review/)[1]);
}

test('a stalled approval does not freeze the queue', async ({ page }) => {
  await page.clock.install();
  const hang = gate();
  let pending = [question(50)];
  await mockApi(page, async route => {
    if (route.request().method() === 'POST') {
      const body = route.request().postDataJSON();
      await hang.promise; // the server takes the request but does not answer yet
      const item = pending.find(existing => existing.id === 50);
      pending = pending.filter(existing => existing.id !== 50);
      await reply(route, approved(item, body));
    } else await reply(route, pending);
  });
  await openMentor(page);
  const stalled = card(page, 'Project question 50');
  await stalled.getByLabel('Mentor verified answer').fill('Answer still in flight');
  await stalled.getByRole('button', { name: 'Approve answer' }).click();
  await expect(stalled.getByRole('button', { name: /Approving/ })).toBeDisabled();

  pending = [question(51), ...pending];
  await page.clock.fastForward(5_100);
  await expect(card(page, 'Project question 51')).toBeVisible();

  pending = [question(52), ...pending];
  await page.getByRole('button', { name: 'Refresh queue' }).click();
  await expect(card(page, 'Project question 52')).toBeVisible();
  // The stalled card keeps its state while the rest of the queue updates.
  await expect(stalled.getByRole('button', { name: /Approving/ })).toBeDisabled();
  await expect(stalled.getByLabel('Mentor verified answer')).toHaveValue('Answer still in flight');

  hang.release();
  await expect(stalled).toHaveCount(0);
  await expect(page.getByText('Question #50 approved. Newcomers now see your reviewed answer.')).toBeVisible();
});

test('an older list that arrives after an approval does not bring the question back', async ({ page }) => {
  await page.clock.install();
  let pending = [question(53)];
  let holdNextRead = false;
  const held = gate();
  await mockApi(page, async route => {
    if (route.request().method() === 'POST') {
      const item = pending[0];
      pending = [];
      await reply(route, approved(item, route.request().postDataJSON()));
      return;
    }
    if (holdNextRead) {
      holdNextRead = false;
      // Snapshot taken before the approval, plus a new question so we can see it was applied.
      const stale = [question(54), ...pending];
      await held.promise;
      await reply(route, stale);
      return;
    }
    await reply(route, pending);
  });
  await openMentor(page);
  const review = card(page, 'Project question 53');
  await expect(review).toBeVisible();
  await stopPolling(page);

  holdNextRead = true;
  await page.getByRole('button', { name: 'Refresh queue' }).click();
  await review.getByRole('button', { name: 'Approve answer' }).click();
  await expect(review).toHaveCount(0);

  held.release();
  await expect(card(page, 'Project question 54')).toBeVisible();
  await expect(review).toHaveCount(0);
});

test('a 409 on one card is explained at once while another approval is still pending', async ({ page }) => {
  await page.clock.install();
  const slow = gate();
  let pending = [question(55), question(56)];
  await mockApi(page, async route => {
    if (route.request().method() === 'POST') {
      if (reviewId(route.request()) === 55) {
        const body = route.request().postDataJSON();
        await slow.promise;
        const item = pending.find(existing => existing.id === 55);
        pending = pending.filter(existing => existing.id !== 55);
        await reply(route, approved(item, body));
      } else {
        pending = pending.filter(existing => existing.id !== 56);
        await reply(route, { detail: 'Already reviewed' }, 409);
      }
    } else await reply(route, pending);
  });
  await openMentor(page);
  const first = card(page, 'Project question 55');
  const second = card(page, 'Project question 56');
  await expect(second).toBeVisible();
  await stopPolling(page); // no poll can rescue the notice in this test
  await first.getByRole('button', { name: 'Approve answer' }).click();
  await expect(first.getByRole('button', { name: /Approving/ })).toBeDisabled();
  await second.getByRole('button', { name: 'Approve answer' }).click();

  await expect(second).toHaveCount(0);
  await expect(page.getByText(/Question #56 is no longer pending/)).toBeVisible();
  await expect(first.getByRole('button', { name: /Approving/ })).toBeDisabled();
  slow.release();
  await expect(first).toHaveCount(0);
});

test('a re-read asked for while another read is running is not dropped', async ({ page }) => {
  await page.clock.install();
  let pending = [question(57)];
  let holdNextRead = false;
  const held = gate();
  await mockApi(page, async route => {
    if (route.request().method() === 'POST') {
      pending = [];
      await reply(route, { detail: 'Already reviewed' }, 409);
      return;
    }
    if (holdNextRead) {
      holdNextRead = false;
      const stale = [...pending]; // taken before the 409, still lists question 57
      await held.promise;
      await reply(route, stale);
      return;
    }
    await reply(route, pending);
  });
  await openMentor(page);
  const review = card(page, 'Project question 57');
  await expect(review).toBeVisible();
  await stopPolling(page);

  holdNextRead = true;
  await page.getByRole('button', { name: 'Refresh queue' }).click();
  await review.getByRole('button', { name: 'Approve answer' }).click();
  await expect(review.getByRole('alert')).toContainText('Approval was not confirmed (Already reviewed)');

  held.release(); // the stale list still has 57; the queued re-read must follow it
  await expect(review).toHaveCount(0);
  await expect(page.getByText(/Question #57 is no longer pending/)).toBeVisible();
});

test('a lost reply that was actually saved gets a neutral notice', async ({ page }) => {
  let pending = [question(58)];
  await mockApi(page, async route => {
    if (route.request().method() === 'POST') {
      pending = []; // saved on the server, but the reply fails
      await reply(route, { detail: 'Gateway timeout' }, 504);
    } else await reply(route, pending);
  });
  await openMentor(page);
  const review = card(page, 'Project question 58');
  await review.getByRole('button', { name: 'Approve answer' }).click();
  await expect(review).toHaveCount(0);
  await expect(page.getByText(
    'Question #58 is no longer pending. It may have been approved by you (if a reply was lost) or by another mentor. Check the Newcomer history.'
  )).toBeVisible();
  await expect(page.getByText(/reviewed elsewhere/)).toHaveCount(0);
});

test('a failed approval suggests trying again without promising that a retry is safe', async ({ page }) => {
  await mockApi(page, async route => {
    if (route.request().method() === 'POST') await reply(route, { detail: 'Question not found' }, 404);
    else await reply(route, [question(59)]);
  });
  await openMentor(page);
  const review = card(page, 'Project question 59');
  await review.getByRole('button', { name: 'Approve answer' }).click();
  const alert = review.getByRole('alert');
  await expect(alert).toContainText('Approval was not confirmed (Question not found). Your answer is still here. Try again; if it keeps failing, refresh the queue.');
  await expect(alert).not.toContainText('Retrying is safe');
});
