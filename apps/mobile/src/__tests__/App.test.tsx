/**
 * Whole-app navigation flows with the real React Navigation stack (App.tsx).
 * The only fake is the network (mock axios adapter) and device storage (jest.setup.ts).
 */

import { act, fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { Alert } from 'react-native';

import App from '../App';
import { ApiClient } from '../services/ApiClient';
import { STORAGE_KEYS } from '../services/AuthService';
import { useAuthStore } from '../store/authStore';
import { errorBody, installMockAdapter, type MockHandler } from '../test-utils/mockAdapter';
import { asyncStorageData, jwtExpiringIn, resetDeviceStorage, secureStoreData } from '../test-utils/storage';

const USER_ID = '3f8a1c2e-5b7d-4e9f-a1b2-c3d4e5f60718';
const initialState = useAuthStore.getState();
const LEVEL_NAMES = ['The building blocks', 'A nucleotide', 'A single strand', 'Two strands', 'The double helix'];
const ME = { user_id: USER_ID, username: 'Shanto', email: 'shanto@example.com', level: 1, level_name: 'Beginner', language: 'en', age: null, gender: null, created_at: '2026-10-01T00:00:00+00:00' };
const PROGRESS = {
  levels: LEVEL_NAMES.map((name, i) => ({ level: i + 1, name, status: i === 0 ? 'passed' : i === 1 ? 'skipped' : 'not_yet', current: i === 2 })),
  level_count: 5, levels_passed: 1, levels_skipped: 1, current_level: 3, current_level_name: 'A single strand',
  finished: false, times_finished: 0, sessions: 2, play_seconds: 754, parts_discovered: 7,
  wildcards: 4, wildcards_used: 1, power_jumps: 0, back_used: 2, chat_questions: 5, last_played: '2026-10-14T10:00:00+00:00',
};
const PROFILE = { user_id: USER_ID, username: 'Shanto', email: 'shanto@example.com', detail_level: 1, language: 'en', created_at: '2026-10-01T00:00:00+00:00' };

/** A small fake Gateway following docs/api-auth-home.md. */
function gateway(overrides: Partial<Record<string, ReturnType<MockHandler>>> = {}): MockHandler {
  const token = jwtExpiringIn(60, USER_ID);
  return (req) => {
    if (overrides[req.url]) return overrides[req.url]!;
    switch (req.url) {
      case '/api/auth/login': {
        const body = req.body as { username: string; password: string };
        return body.password === 'Correct-Horse-9'
          ? { status: 200, data: { user_id: USER_ID, token, profile: { detail_level: 1, language: 'en' } } }
          : { status: 401, data: errorBody('INVALID_CREDENTIALS', 'Incorrect username or password.') };
      }
      case '/api/auth/register':
        return { status: 201, data: { user_id: USER_ID, token, profile: { detail_level: 1, language: 'en' } } };
      case `/api/users/${USER_ID}/profile`:
        return { status: 200, data: PROFILE };
      case '/api/ar/progress':
        return { status: 200, data: PROGRESS };
      case '/api/users/me':
        return { status: 200, data: ME };
      case '/api/wildcards':
        return { status: 200, data: { total: 5, requests: [], can_request: true, next_request_at: null } };
      case '/api/events':
        return { status: 200, data: {} };
      default:
        return { status: 404, data: errorBody('NOT_FOUND', 'Not found') };
    }
  };
}

function saveSession(token: string) {
  secureStoreData().set(STORAGE_KEYS.token, token);
  asyncStorageData().set(STORAGE_KEYS.userId, USER_ID);
  asyncStorageData().set(STORAGE_KEYS.profile, JSON.stringify({ detail_level: 1, language: 'en', username: 'Shanto' }));
}

async function typeAndLogin(password = 'Correct-Horse-9') {
  await fireEvent.changeText(await screen.findByTestId('login-username'), 'shanto');
  await fireEvent.changeText(screen.getByTestId('login-password'), password);
  await fireEvent.press(screen.getByTestId('login-submit'));
}

beforeEach(() => {
  resetDeviceStorage();
  jest.restoreAllMocks();
  useAuthStore.setState(initialState, true);
});

it('fresh install: splash, then the Login screen', async () => {
  installMockAdapter(ApiClient, gateway());
  await render(<App />);
  expect(await screen.findByTestId('login-screen')).toBeOnTheScreen();
  expect(screen.queryByTestId('splash-screen')).not.toBeOnTheScreen();
});

it('saved login survives a restart: opens straight on Topics', async () => {
  saveSession(jwtExpiringIn(60, USER_ID));
  installMockAdapter(ApiClient, gateway());

  await render(<App />);

  expect(await screen.findByTestId('home-greeting')).toHaveTextContent('Hi, Shanto!');
  expect(screen.getByTestId('topic-dna')).toBeOnTheScreen();
  expect(screen.queryByTestId('login-screen')).not.toBeOnTheScreen();
});

it('expired saved login: back to Login with a notice', async () => {
  saveSession(jwtExpiringIn(-10, USER_ID));
  installMockAdapter(ApiClient, gateway());

  await render(<App />);

  expect(await screen.findByTestId('login-notice')).toHaveTextContent(/Your session has expired/);
  expect(secureStoreData().size).toBe(0);
});

it('login → Topics → DNA page with the progress dashboard → AR game and chat', async () => {
  installMockAdapter(ApiClient, gateway());
  await render(<App />);

  await typeAndLogin();

  expect(await screen.findByTestId('home-greeting')).toBeOnTheScreen();
  await fireEvent.press(screen.getByTestId('topic-dna'));

  // dashboard: only the wildcard total is shown, never how it is made up
  expect(await screen.findByTestId('dna-progress-headline')).toHaveTextContent('Level 3 of 5 · A single strand');
  expect(screen.getByTestId('stat-levels')).toHaveTextContent(/2\/5\s*Levels done/);
  expect(screen.getByTestId('stat-wildcards')).toHaveTextContent(/(^|\D)4\s*Wildcards/);
  expect(screen.getByTestId('stat-time')).toHaveTextContent(/12m\s*Play time/);
  expect(screen.getByTestId('stat-back')).toHaveTextContent(/(^|\D)2\s*Back used/);
  expect(screen.getByTestId('level-1-passed')).toBeOnTheScreen();
  expect(screen.getByTestId('level-2-skipped')).toBeOnTheScreen();
  expect(screen.queryByText(/gift|default/i)).not.toBeOnTheScreen();

  await fireEvent.press(screen.getByTestId('dna-ar-button'));
  expect(await screen.findByTestId('argame-scene-name')).toHaveTextContent('Root_ARPersistent');
  expect(screen.getByTestId('argame-unity-unavailable')).toBeOnTheScreen();
});

it('Profile: shows the wildcard total; ask the teacher with a reason, then see it waiting', async () => {
  saveSession(jwtExpiringIn(60, USER_ID));
  let asked: { amount: number; reason: string } | null = null;
  const item = () => ({ ticket_id: 't1', ...asked!, status: 'open', granted: null, admin_reply: null, created_at: '2026-10-15T00:00:00+00:00', updated_at: null });
  const calls = installMockAdapter(ApiClient, (req) => {
    if (req.url === '/api/wildcards/request') {
      asked = req.body as { amount: number; reason: string };
      return { status: 201, data: item() };
    }
    if (req.url === '/api/wildcards') {
      return {
        status: 200,
        data: asked
          ? { total: 5, requests: [item()], can_request: false, next_request_at: '2026-10-18T00:00:00+00:00' }
          : { total: 5, requests: [], can_request: true, next_request_at: null },
      };
    }
    return gateway()(req);
  });
  await render(<App />);
  await fireEvent.press(await screen.findByTestId('profile-button'));

  expect(await screen.findByTestId('wildcards-total')).toHaveTextContent('5');
  expect(screen.queryByText(/\bgift\b|default/i)).not.toBeOnTheScreen(); // only the total, never the split

  await fireEvent.press(screen.getByTestId('ask-open'));
  await fireEvent.press(screen.getByTestId('ask-send'));
  expect(screen.getByTestId('ask-error')).toHaveTextContent(/at least 5 characters/);

  await fireEvent.press(screen.getByTestId('ask-amount-3'));
  await fireEvent.changeText(screen.getByTestId('ask-reason'), 'Stuck on the double helix');
  await fireEvent.press(screen.getByTestId('ask-send'));

  expect(await screen.findByTestId('ask-status')).toHaveTextContent(/You asked for 3 .*Waiting for your teacher/);
  expect(screen.getByTestId('ask-later')).toHaveTextContent(/You can ask again on/);
  expect(asked).toEqual({ amount: 3, reason: 'Stuck on the double helix' });
  expect(calls.some((c) => c.method === 'POST' && c.url === '/api/wildcards/request')).toBe(true);
});

it('Profile: edit level, age and gender, and change the password', async () => {
  saveSession(jwtExpiringIn(60, USER_ID));
  let me = { ...ME };
  const calls = installMockAdapter(ApiClient, (req) => {
    if (req.url === '/api/users/me' && req.method === 'PATCH') {
      const body = req.body as { level?: number; age?: number; gender?: string };
      me = { ...me, ...body, level_name: 'Intermediate' } as typeof me;
      return { status: 200, data: me };
    }
    if (req.url === '/api/users/me/password') {
      const body = req.body as { current_password: string };
      return body.current_password === 'Correct-Horse-9'
        ? { status: 200, data: { status: 'password_changed' } }
        : { status: 400, data: errorBody('VALIDATION_ERROR', 'Current password is not correct.', { current_password: 'Current password is not correct.' }) };
    }
    return gateway()(req);
  });
  await render(<App />);
  await fireEvent.press(await screen.findByTestId('profile-button'));

  expect(await screen.findByTestId('profile-name')).toHaveTextContent('Shanto');
  expect(screen.getByTestId('profile-email').props.value).toBe('shanto@example.com');

  await fireEvent.press(screen.getByTestId('profile-level-2'));
  await fireEvent.changeText(screen.getByTestId('profile-age'), '21');
  await fireEvent.press(screen.getByTestId('profile-gender-female'));
  await fireEvent.press(screen.getByTestId('profile-save'));
  expect(await screen.findByTestId('profile-save-msg')).toHaveTextContent('Profile saved.');
  const patch = calls.find((c) => c.method === 'PATCH');
  expect(patch?.body).toEqual({ level: 2, age: 21, gender: 'female' });

  await fireEvent.press(screen.getByTestId('password-open'));
  await fireEvent.changeText(screen.getByTestId('password-current'), 'Wrong-Pass-1');
  await fireEvent.changeText(screen.getByTestId('password-new'), 'New-Horse-10');
  await fireEvent.changeText(screen.getByTestId('password-confirm'), 'New-Horse-1');
  await fireEvent.press(screen.getByTestId('password-save'));
  expect(screen.getByText('The passwords do not match.')).toBeOnTheScreen();

  await fireEvent.changeText(screen.getByTestId('password-confirm'), 'New-Horse-10');
  await fireEvent.press(screen.getByTestId('password-save'));
  expect(await screen.findByText('Current password is not correct.')).toBeOnTheScreen();

  await fireEvent.changeText(screen.getByTestId('password-current'), 'Correct-Horse-9');
  await fireEvent.press(screen.getByTestId('password-save'));
  expect(await screen.findByTestId('password-done')).toHaveTextContent('Password changed.');
});

it('the DNA page explains when progress cannot be loaded', async () => {
  saveSession(jwtExpiringIn(60, USER_ID));
  installMockAdapter(ApiClient, gateway({ '/api/ar/progress': 'network-error' }));
  await render(<App />);

  await fireEvent.press(await screen.findByTestId('topic-dna'));
  expect(await screen.findByTestId('dna-progress-error')).toHaveTextContent(/Couldn't load your progress/);
  expect(screen.getByTestId('dna-chat-button')).toBeOnTheScreen();
});

it('forgot password: from Login, the request goes to support (no login needed)', async () => {
  const calls = installMockAdapter(ApiClient, (req) =>
    req.url === '/api/auth/password-reset-request'
      ? { status: 200, data: { status: 'received', message: 'Your request was sent to support.' } }
      : gateway()(req),
  );
  await render(<App />);
  await fireEvent.changeText(await screen.findByTestId('login-username'), 'shanto');
  await fireEvent.press(screen.getByTestId('go-to-forgot'));

  expect(await screen.findByTestId('forgot-username')).toHaveProp('value', 'shanto');
  await fireEvent.changeText(screen.getByTestId('forgot-message'), 'Email me please');
  await fireEvent.press(screen.getByTestId('forgot-send'));

  expect(await screen.findByTestId('forgot-done')).toHaveTextContent(/sent to support/);
  const req = calls.find((c) => c.url === '/api/auth/password-reset-request');
  expect(req?.body).toEqual({ username_or_email: 'shanto', message: 'Email me please' });
  expect(req?.authorization).toBeNull();
});

it('wrong password keeps the user on Login with an error', async () => {
  installMockAdapter(ApiClient, gateway());
  await render(<App />);

  await typeAndLogin('Wrong-Pass-1');

  expect(await screen.findByTestId('login-error')).toHaveTextContent(/Incorrect username or password/);
  expect(screen.queryByTestId('home-greeting')).not.toBeOnTheScreen();
});

it('backend offline shows a network error on Login', async () => {
  installMockAdapter(ApiClient, () => 'network-error');
  await render(<App />);

  await typeAndLogin();

  expect(await screen.findByTestId('login-error')).toHaveTextContent(/Can't reach the server/);
});

it('sign up from Login → auto-login → Topics', async () => {
  installMockAdapter(ApiClient, gateway());
  await render(<App />);

  await fireEvent.press(await screen.findByTestId('go-to-signup'));
  expect(await screen.findByTestId('signup-screen')).toBeOnTheScreen();

  await fireEvent.changeText(screen.getByTestId('signup-username'), 'Shanto');
  await fireEvent.changeText(screen.getByTestId('signup-email'), 'shanto@example.com');
  await fireEvent.changeText(screen.getByTestId('signup-password'), 'Correct-Horse-9');
  await fireEvent.changeText(screen.getByTestId('signup-confirm'), 'Correct-Horse-9');
  await fireEvent.press(screen.getByTestId('signup-submit'));

  expect(await screen.findByTestId('home-greeting')).toHaveTextContent('Hi, Shanto!');
});

it('logout returns to Login and purges stored credentials', async () => {
  saveSession(jwtExpiringIn(60, USER_ID));
  installMockAdapter(ApiClient, gateway());
  const alertSpy = jest.spyOn(Alert, 'alert').mockImplementation(() => undefined);

  await render(<App />);
  await fireEvent.press(await screen.findByTestId('profile-button'));
  await fireEvent.press(await screen.findByTestId('logout-button'));

  // The user taps "Log out" in the confirmation dialog
  const buttons = alertSpy.mock.calls[0][2] ?? [];
  await act(async () => buttons.find((b) => b.text === 'Log out')?.onPress?.());

  expect(await screen.findByTestId('login-screen')).toBeOnTheScreen();
  await waitFor(() => expect(secureStoreData().size).toBe(0));
  expect(asyncStorageData().size).toBe(0);
});

it('a 401 from the server on the DNA page returns to Login with the server message', async () => {
  saveSession(jwtExpiringIn(60, USER_ID));
  installMockAdapter(
    ApiClient,
    gateway({ '/api/ar/progress': { status: 401, data: errorBody('TOKEN_INVALID', 'Your session is not valid. Please log in again.') } }),
  );

  await render(<App />);
  await fireEvent.press(await screen.findByTestId('topic-dna'));

  expect(await screen.findByTestId('login-notice')).toHaveTextContent(/Your session is not valid/);
});
