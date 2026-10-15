/**
 * DNA quiz flows through the real app (App.tsx → Topics → DNA → Quiz) against a small fake quiz server.
 * The fake follows the gateway contract (routers/quiz.py): the server owns the answer key and the score.
 */

import { fireEvent, render, screen } from '@testing-library/react-native';
import { Alert } from 'react-native';

import App from '../App';
import { ApiClient } from '../services/ApiClient';
import { STORAGE_KEYS } from '../services/AuthService';
import { useAuthStore } from '../store/authStore';
import { errorBody, installMockAdapter, type MockReply, type RecordedRequest } from '../test-utils/mockAdapter';
import { asyncStorageData, jwtExpiringIn, resetDeviceStorage, secureStoreData } from '../test-utils/storage';

const USER_ID = '3f8a1c2e-5b7d-4e9f-a1b2-c3d4e5f60718';
const initialState = useAuthStore.getState();
const KEY = 'BABBCBBBCBBBCDCBABBB'; // the server's answer key (never sent before submit)
const QUESTIONS = Array.from({ length: 20 }, (_, i) => ({
  id: String(i + 1),
  level: i < 6 ? 'easy' : i < 14 ? 'medium' : 'hard',
  text: `Question number ${i + 1}?`,
  options: (['A', 'B', 'C', 'D'] as const).map((k) => ({ key: k, text: `Choice ${k}${i + 1}` })),
}));
const LEVEL_NAMES = ['The building blocks', 'A nucleotide', 'A single strand', 'Two strands', 'The double helix'];
const PROGRESS = {
  levels: LEVEL_NAMES.map((name, i) => ({ level: i + 1, name, status: 'not_yet', current: i === 0 })),
  level_count: 5, levels_passed: 0, levels_skipped: 0, current_level: 1, current_level_name: LEVEL_NAMES[0],
  finished: false, times_finished: 0, sessions: 0, play_seconds: 0, parts_discovered: 0,
  wildcards: 5, wildcards_used: 0, power_jumps: 0, back_used: 0, chat_questions: 0, last_played: null,
};
const NOW = () => new Date().toISOString();
const inHours = (h: number) => new Date(Date.now() + h * 3600_000).toISOString();

interface Attempt {
  attempt_id: string; status: string; attempt_type: string; quiz_version: number; started_at: string; ended_at: string | null;
  expires_at: string; duration_s: number | null; wildcards_spent: number; score: number | null; total: number | null;
  correct: number | null; incorrect: number | null; percent: number | null; key: string;
}
interface Req {
  request_id: string; status: string; reason: string | null; created_at: string; decided_at: string | null; decided_by: string | null;
  decision_reason: string | null; window_start: string | null; window_end: string | null; cooldown_hours: number | null;
  used_at: string | null; used_attempt_id: string | null;
}

/** Stateful fake of the gateway quiz rules (enough for the screens; the real rules are tested in the gateway). */
function quizServer(init: { cooldown?: number; wildcards?: number; attempts?: Attempt[]; requests?: Req[]; failStartOnce?: 'network-error' } = {}) {
  const st = {
    cooldown: init.cooldown ?? 0, // seconds left
    wildcards: init.wildcards ?? 5,
    attempts: init.attempts ?? ([] as Attempt[]),
    requests: init.requests ?? ([] as Req[]),
    failStartOnce: init.failStartOnce as MockReply | undefined,
  };
  const active = () => st.attempts.find((a) => a.status === 'in_progress') ?? null;
  const pub = ({ key: _k, ...a }: Attempt) => a;
  const done = () => st.attempts.filter((a) => a.status === 'completed');
  const summary = () => {
    const d = done();
    const ended = st.attempts.filter((a) => a.status !== 'in_progress');
    const best = d.reduce<Attempt | null>((b, a) => (!b || a.percent! > b.percent! ? a : b), null);
    return {
      total_attempts: st.attempts.length, completed_attempts: d.length, incomplete_attempts: ended.length - d.length,
      completion_rate: ended.length ? Math.round((1000 * d.length) / ended.length) / 10 : null,
      latest: d[0] ? { score: d[0].score, total: d[0].total, percent: d[0].percent, ended_at: d[0].ended_at } : null,
      best: best ? { score: best.score, total: best.total, percent: best.percent } : null,
      average_percent: d.length ? d.reduce((s, a) => s + a.percent!, 0) / d.length : null,
      average_score: null, trend: null,
      forced_attempts: st.attempts.filter((a) => a.attempt_type === 'forced').length,
      wildcards_spent: st.attempts.reduce((s, a) => s + a.wildcards_spent, 0),
      last_completed_at: d[0]?.ended_at ?? null, ever_completed: d.length > 0,
    };
  };
  const status = () => {
    const approved = st.requests.find((r) => r.status === 'approved') ?? null;
    const pending = st.requests.find((r) => r.status === 'pending') ?? null;
    const a = active();
    return {
      server_time: NOW(),
      quiz: { quiz_id: 'dna', version: 1, title: 'DNA Multiple-Choice Quiz', question_count: 20, time_limit_s: 1800, cooldown_hours: 12 },
      eligible: st.cooldown === 0 && !a,
      next_eligible_at: st.cooldown ? new Date(Date.now() + st.cooldown * 1000).toISOString() : null,
      cooldown_remaining_s: st.cooldown,
      active_attempt: a ? { attempt_id: a.attempt_id, attempt_type: a.attempt_type, started_at: a.started_at, expires_at: a.expires_at } : null,
      force_cost: 3, wildcards: st.wildcards, can_force: !a && st.cooldown > 0 && st.wildcards >= 3,
      authorization: approved ? { ...approved, usable_now: Date.parse(approved.window_start!) <= Date.now() } : null,
      pending_request: pending, can_request: !pending && !approved, requests: st.requests,
    };
  };
  const byKey = new Map<string, Attempt>();

  const handler = (req: RecordedRequest): MockReply => {
    const url = req.url;
    if (url === '/api/quiz/status') return { status: 200, data: status() };
    if (url === '/api/quiz/history') return { status: 200, data: { summary: summary(), attempts: st.attempts.map(pub) } };
    if (url === '/api/quiz/attempts' && req.method === 'POST') {
      const body = req.body as { mode: string; idempotency_key: string };
      if (st.failStartOnce) {
        const reply = st.failStartOnce;
        st.failStartOnce = undefined;
        // the server DID start (and charge) before the connection dropped: the retry must get the same attempt
        startAttempt(body);
        return reply;
      }
      const again = byKey.get(body.idempotency_key);
      if (again) return { status: 201, data: started(again, true) };
      if (active()) return { status: 409, data: errorBody('ATTEMPT_IN_PROGRESS', 'You already have a quiz in progress.') };
      if (body.mode === 'normal' && st.cooldown) return { status: 429, data: errorBody('COOLDOWN', 'You can take the quiz again after the cooldown.') };
      if (body.mode === 'forced' && st.wildcards < 3) {
        return { status: 402, data: errorBody('NOT_ENOUGH_WILDCARDS', `A forced attempt costs 3 wildcards. You have ${st.wildcards}.`) };
      }
      return { status: 201, data: started(startAttempt(body), false) };
    }
    const m = url.match(/^\/api\/quiz\/attempts\/([^/]+)(?:\/(submit|abandon))?$/);
    if (m) {
      const a = st.attempts.find((x) => x.attempt_id === m[1]);
      if (!a) return { status: 404, data: errorBody('ATTEMPT_NOT_FOUND', 'Quiz attempt not found.') };
      if (m[2] === 'abandon') {
        a.status = 'abandoned';
        a.ended_at = NOW();
        return { status: 200, data: pub(a) };
      }
      if (m[2] === 'submit') {
        const answers = (req.body as { answers: Record<string, string> }).answers;
        if (a.status === 'completed') return { status: 200, data: { ...result(a, answers), duplicate: true } };
        const missing = QUESTIONS.filter((q) => !answers[q.id]).length;
        if (missing) return { status: 400, data: errorBody('INCOMPLETE', `Answer every question before submitting (${missing} left).`) };
        const score = QUESTIONS.filter((q, i) => answers[q.id] === KEY[i]).length;
        Object.assign(a, { status: 'completed', ended_at: NOW(), duration_s: 252, score, total: 20, correct: score, incorrect: 20 - score, percent: score * 5 });
        return { status: 200, data: { ...result(a, answers), duplicate: false } };
      }
      return { status: 200, data: { ...pub(a), ...(a.status === 'in_progress' ? { questions: QUESTIONS } : {}) } };
    }
    if (url === '/api/quiz/access-requests' && req.method === 'POST') {
      if (st.requests.some((r) => r.status === 'pending' || r.status === 'approved')) {
        return { status: 409, data: errorBody('REQUEST_EXISTS', 'You already have a request waiting for an admin.') };
      }
      const r: Req = {
        request_id: `r${st.requests.length + 1}`, status: 'pending', reason: (req.body as { reason: string | null }).reason, created_at: NOW(),
        decided_at: null, decided_by: null, decision_reason: null, window_start: null, window_end: null, cooldown_hours: null, used_at: null, used_attempt_id: null,
      };
      st.requests.unshift(r);
      return { status: 201, data: r };
    }
    return { status: 404, data: errorBody('NOT_FOUND', 'Not found') };
  };

  function startAttempt(body: { mode: string; idempotency_key: string }): Attempt {
    const a: Attempt = {
      attempt_id: `a${st.attempts.length + 1}`, status: 'in_progress', attempt_type: body.mode, quiz_version: 1, started_at: NOW(), ended_at: null,
      expires_at: new Date(Date.now() + 1800_000).toISOString(), duration_s: null, wildcards_spent: body.mode === 'forced' ? 3 : 0,
      score: null, total: null, correct: null, incorrect: null, percent: null, key: body.idempotency_key,
    };
    if (body.mode === 'forced') st.wildcards -= 3;
    if (body.mode === 'authorized') {
      const r = st.requests.find((x) => x.status === 'approved')!;
      Object.assign(r, { status: 'used', used_at: NOW(), used_attempt_id: a.attempt_id });
    }
    st.cooldown = 12 * 3600;
    st.attempts.unshift(a);
    byKey.set(body.idempotency_key, a);
    return a;
  }
  function started(a: Attempt, replayed: boolean) {
    return { ...pub(a), wildcards: st.wildcards, replayed, questions: QUESTIONS };
  }
  function result(a: Attempt, answers: Record<string, string>) {
    return {
      ...pub(a),
      review: QUESTIONS.map((q, i) => ({ ...q, your_answer: answers[q.id], correct_answer: KEY[i], correct: answers[q.id] === KEY[i], explanation: `Because ${KEY[i]}.` })),
    };
  }
  return { st, handler };
}

function app(server: ReturnType<typeof quizServer>) {
  return installMockAdapter(ApiClient, (req) => {
    if (req.url.startsWith('/api/quiz')) return server.handler(req);
    switch (req.url) {
      case '/api/ar/progress': return { status: 200, data: PROGRESS };
      case '/api/users/me': return { status: 200, data: { user_id: USER_ID, username: 'Shanto', email: 's@example.com', level: 1, level_name: 'Beginner', language: 'en', age: null, gender: null, created_at: NOW() } };
      case '/api/wildcards': return { status: 200, data: { total: server.st.wildcards, requests: [], can_request: true, next_request_at: null } };
      case '/api/events': return { status: 200, data: {} };
      default: return { status: 404, data: errorBody('NOT_FOUND', 'Not found') };
    }
  });
}

async function openQuiz() {
  await render(<App />);
  await fireEvent.press(await screen.findByTestId('topic-dna'));
  await fireEvent.press(await screen.findByTestId('dna-quiz-button'));
}

async function answerAll(choice: (i: number) => string) {
  for (let i = 0; i < 20; i += 1) {
    expect(screen.getByTestId('quiz-progress')).toHaveTextContent(new RegExp(`^Question ${i + 1} of 20 ·`));
    await fireEvent.press(screen.getByTestId(`quiz-option-${choice(i)}`));
    if (i < 19) await fireEvent.press(screen.getByTestId('quiz-next'));
  }
}

const completed = (id: string, score: number, hoursAgo: number, type = 'normal', spent = 0): Attempt => ({
  attempt_id: id, status: 'completed', attempt_type: type, quiz_version: 1, started_at: inHours(-hoursAgo - 0.1), ended_at: inHours(-hoursAgo),
  expires_at: inHours(-hoursAgo + 0.4), duration_s: 300, wildcards_spent: spent, score, total: 20, correct: score, incorrect: 20 - score,
  percent: score * 5, key: `k-${id}`,
});

beforeEach(() => {
  resetDeviceStorage();
  jest.restoreAllMocks();
  useAuthStore.setState(initialState, true);
  secureStoreData().set(STORAGE_KEYS.token, jwtExpiringIn(60, USER_ID));
  asyncStorageData().set(STORAGE_KEYS.userId, USER_ID);
  asyncStorageData().set(STORAGE_KEYS.profile, JSON.stringify({ detail_level: 1, language: 'en', username: 'Shanto' }));
});

it('DNA dashboard: latest, best, average, attempts, cooldown, request status, wildcards and Force spending', async () => {
  const server = quizServer({
    cooldown: 3 * 3600, wildcards: 4,
    attempts: [
      { ...completed('a3', 12, 1, 'forced', 3) },
      { ...completed('a2', 0, 20), status: 'abandoned', score: null, total: null, correct: null, incorrect: null, percent: null, ended_at: inHours(-20) },
      completed('a1', 16, 30),
    ],
    requests: [{ request_id: 'r1', status: 'pending', reason: 'exam', created_at: inHours(-0.5), decided_at: null, decided_by: null, decision_reason: null,
      window_start: null, window_end: null, cooldown_hours: null, used_at: null, used_attempt_id: null }],
  });
  app(server);
  await render(<App />);
  await fireEvent.press(await screen.findByTestId('topic-dna'));

  expect(await screen.findByTestId('quiz-latest')).toHaveTextContent('Latest score 12/20 (60%)');
  expect(screen.getByTestId('quiz-completion')).toHaveTextContent('Completed · 2 completed of 3 attempts');
  expect(screen.getByTestId('quiz-best')).toHaveTextContent(/16\/20\s*Best score/);
  expect(screen.getByTestId('quiz-average')).toHaveTextContent(/70%\s*Average/); // (60 + 80) / 2: the abandoned one is not a result
  expect(screen.getByTestId('quiz-attempts')).toHaveTextContent(/2\/3/);
  expect(screen.getByTestId('quiz-rate')).toHaveTextContent(/67%/);
  expect(screen.getByTestId('quiz-next')).toHaveTextContent(/Next attempt: .*\(in (2h 59m|3h 0m)\)/);
  expect(screen.getByTestId('quiz-request-status')).toHaveTextContent(/Waiting for an admin/);
  expect(screen.getByTestId('quiz-wildcards')).toHaveTextContent(/(^|\D)4\s*Wildcards/);
  expect(screen.getByTestId('quiz-force-spent')).toHaveTextContent(/3\s*Spent on Force \(1×\)/);
  expect(screen.getByTestId('quiz-history-a3')).toHaveTextContent(/Force Attempt.*12\/20 · 60%/);
  expect(screen.getByTestId('quiz-history-a2')).toHaveTextContent(/abandoned/);
});

it('normal attempt: answer one question at a time, server score, result with review; the dashboard updates', async () => {
  const server = quizServer();
  const calls = app(server);
  await openQuiz();

  await fireEvent.press(await screen.findByTestId('quiz-start'));
  expect(await screen.findByTestId('quiz-play')).toBeOnTheScreen();
  const startCall = calls.find((c) => c.method === 'POST' && c.url === '/api/quiz/attempts')!;
  expect(startCall.body).toEqual({ mode: 'normal', idempotency_key: expect.stringMatching(/^[A-Za-z0-9_.:-]{8,80}$/) });

  await answerAll(() => 'B');
  await fireEvent.press(screen.getByTestId('quiz-submit'));

  expect(await screen.findByTestId('quiz-result-score')).toHaveTextContent('13/20');
  expect(screen.getByTestId('quiz-result-percent')).toHaveTextContent('65%');
  expect(screen.getByTestId('quiz-result-correct')).toHaveTextContent(/13\s*Correct/);
  expect(screen.getByTestId('quiz-result-incorrect')).toHaveTextContent(/7\s*Incorrect/);
  expect(screen.getByTestId('quiz-result-status')).toHaveTextContent(/Completed/);
  expect(screen.getByTestId('quiz-result-time')).toHaveTextContent(/4m\s*Time taken/);
  expect(screen.getByTestId('quiz-review-2')).toHaveTextContent(/Your answer: B.*Correct: A/);
  const submit = calls.find((c) => c.url === '/api/quiz/attempts/a1/submit')!;
  expect(Object.keys((submit.body as { answers: object }).answers)).toHaveLength(20);

  await fireEvent.press(screen.getByTestId('quiz-done'));
  expect(await screen.findByTestId('quiz-latest')).toHaveTextContent('Latest score 13/20 (65%)');
  expect(screen.getByTestId('quiz-next')).toHaveTextContent(/Next attempt: .*\(in (11h 59m|12h 0m)\)/);
});

it('an incomplete quiz is not sent: it jumps to the first unanswered question', async () => {
  const server = quizServer();
  const calls = app(server);
  await openQuiz();
  await fireEvent.press(await screen.findByTestId('quiz-start'));
  await fireEvent.press(await screen.findByTestId('quiz-option-A'));
  await fireEvent.press(screen.getByTestId('quiz-jump-20'));
  await fireEvent.press(screen.getByTestId('quiz-submit'));

  expect(screen.getByTestId('quiz-notice')).toHaveTextContent(/Answer every question first \(19 left\)/);
  expect(screen.getByTestId('quiz-progress')).toHaveTextContent(/^Question 2 of 20 ·/);
  expect(calls.some((c) => c.url.endsWith('/submit'))).toBe(false);
});

it('cooldown: Force Attempt is disabled without 3 wildcards and the server message is shown', async () => {
  const server = quizServer({ cooldown: 5 * 3600, wildcards: 2, attempts: [completed('a1', 10, 7)] });
  app(server);
  await openQuiz();

  expect(await screen.findByTestId('quiz-cooldown')).toHaveTextContent(/Next attempt in (4h 59m|5h 0m)/);
  expect(screen.queryByTestId('quiz-start')).not.toBeOnTheScreen();
  expect(screen.getByTestId('quiz-force')).toBeDisabled();
  expect(screen.getByTestId('quiz-force-short')).toHaveTextContent('You need 1 more wildcard.');
});

it('Force Attempt: a retry after a lost response reuses the idempotency key, so only 3 wildcards are taken', async () => {
  const server = quizServer({ cooldown: 5 * 3600, wildcards: 7, attempts: [completed('a1', 10, 7)], failStartOnce: 'network-error' });
  const calls = app(server);
  await openQuiz();

  await fireEvent.press(await screen.findByTestId('quiz-force'));
  expect(await screen.findByTestId('quiz-notice')).toHaveTextContent(/Can't reach the server/);
  await fireEvent.press(screen.getByTestId('quiz-force'));
  expect(await screen.findByTestId('quiz-play')).toBeOnTheScreen();

  const starts = calls.filter((c) => c.method === 'POST' && c.url === '/api/quiz/attempts').map((c) => c.body as { mode: string; idempotency_key: string });
  expect(starts).toHaveLength(2);
  expect(starts[0].mode).toBe('forced');
  expect(starts[1].idempotency_key).toBe(starts[0].idempotency_key);
  expect(server.st.wildcards).toBe(4); // 7 - 3, once
  expect(server.st.attempts.filter((a) => a.attempt_type === 'forced')).toHaveLength(1);
});

it('early-attempt request: send it, then see it waiting (no second request button)', async () => {
  const server = quizServer({ cooldown: 3600, wildcards: 0, attempts: [completed('a1', 10, 11)] });
  const calls = app(server);
  await openQuiz();

  await fireEvent.press(await screen.findByTestId('quiz-request-open'));
  await fireEvent.changeText(screen.getByTestId('quiz-request-reason'), 'Exam tomorrow');
  await fireEvent.press(screen.getByTestId('quiz-request-send'));

  expect(await screen.findByTestId('quiz-request-pending')).toHaveTextContent(/waiting for an admin/);
  expect(screen.queryByTestId('quiz-request-open')).not.toBeOnTheScreen();
  expect(screen.getByTestId('quiz-request-r1-status')).toHaveTextContent('Waiting for an admin');
  expect(calls.find((c) => c.method === 'POST' && c.url === '/api/quiz/access-requests')!.body).toEqual({ reason: 'Exam tomorrow' });
});

it('an approved request starts ONE authorized attempt, then shows as used', async () => {
  const server = quizServer({
    cooldown: 6 * 3600, wildcards: 0, attempts: [completed('a1', 10, 6)],
    requests: [{ request_id: 'r1', status: 'approved', reason: 'exam', created_at: inHours(-2), decided_at: inHours(-1), decided_by: 'admin',
      decision_reason: 'ok', window_start: inHours(-1), window_end: inHours(23), cooldown_hours: 12, used_at: null, used_attempt_id: null }],
  });
  const calls = app(server);
  await openQuiz();

  expect(await screen.findByTestId('quiz-auth-ready')).toBeOnTheScreen();
  expect(screen.getByTestId('quiz-request-blocked')).toBeOnTheScreen();
  await fireEvent.press(screen.getByTestId('quiz-start-authorized'));
  expect(await screen.findByTestId('quiz-play')).toBeOnTheScreen();
  expect(calls.find((c) => c.method === 'POST' && c.url === '/api/quiz/attempts')!.body).toMatchObject({ mode: 'authorized' });
  expect(server.st.requests[0].status).toBe('used');
});

function withActive(server: ReturnType<typeof quizServer>) {
  server.st.attempts.unshift({ ...completed('a9', 0, 0), status: 'in_progress', ended_at: null, score: null, total: null, correct: null,
    incorrect: null, percent: null, started_at: inHours(-0.1), expires_at: inHours(0.4) });
}

it('a quiz left in progress can be continued with the server time limit', async () => {
  const server = quizServer({ cooldown: 12 * 3600 });
  withActive(server);
  app(server);
  await openQuiz();

  expect(await screen.findByTestId('quiz-active')).toBeOnTheScreen();
  await fireEvent.press(screen.getByTestId('quiz-resume'));
  expect(await screen.findByTestId('quiz-play')).toBeOnTheScreen();
  expect(screen.getByTestId('quiz-timer')).toHaveTextContent(/^2[34]m/); // 30 min limit, started 6 min ago
});

it('a quiz left in progress can be abandoned after a warning: it counts as an attempt, no score', async () => {
  const server = quizServer({ cooldown: 12 * 3600 });
  withActive(server);
  const calls = app(server);
  const alert = jest.spyOn(Alert, 'alert').mockImplementation((_t, _m, buttons) => buttons?.find((b) => b.style === 'destructive')?.onPress?.());
  await openQuiz();

  await fireEvent.press(await screen.findByTestId('quiz-abandon-active'));
  expect(alert).toHaveBeenCalledWith('Leave this quiz?', expect.stringMatching(/not be scored/), expect.any(Array));
  expect(await screen.findByTestId('quiz-cooldown')).toBeOnTheScreen();
  expect(calls.some((c) => c.method === 'POST' && c.url === '/api/quiz/attempts/a9/abandon')).toBe(true);
  expect(server.st.attempts[0].status).toBe('abandoned');
});
