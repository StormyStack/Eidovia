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
const MODULES = [
  { module_id: 'cell-explore', title: 'Explore the Cell', description: 'Tap organelles.', difficulty: 1, thumbnail_url: null },
  { module_id: 'cell-quiz', title: 'Cell Quiz', description: 'Test yourself.', difficulty: 3, thumbnail_url: null },
];
const CONFIG = { module_id: 'cell-quiz', scene_name: 'GameScene_CellQuiz', cdn_bundle_url: 'https://cdn.example.com/bundles/cell-quiz', difficulty: 3, config: {} };
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
      case '/api/modules':
        return { status: 200, data: MODULES };
      case '/api/modules/cell-quiz/config':
        return { status: 200, data: CONFIG };
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

it('saved login survives a restart: opens straight on Home', async () => {
  saveSession(jwtExpiringIn(60, USER_ID));
  installMockAdapter(ApiClient, gateway());

  await render(<App />);

  expect(await screen.findByTestId('home-greeting')).toHaveTextContent('Hi, Shanto!');
  expect(await screen.findByText('Explore the Cell')).toBeOnTheScreen();
  expect(screen.queryByTestId('login-screen')).not.toBeOnTheScreen();
});

it('expired saved login: back to Login with a notice', async () => {
  saveSession(jwtExpiringIn(-10, USER_ID));
  installMockAdapter(ApiClient, gateway());

  await render(<App />);

  expect(await screen.findByTestId('login-notice')).toHaveTextContent(/Your session has expired/);
  expect(secureStoreData().size).toBe(0);
});

it('login → Home → open a module → ARGame shows its scene', async () => {
  installMockAdapter(ApiClient, gateway());
  await render(<App />);

  await typeAndLogin();

  expect(await screen.findByTestId('home-greeting')).toBeOnTheScreen();
  await fireEvent.press(await screen.findByTestId('module-cell-quiz'));

  expect(await screen.findByTestId('argame-scene-name')).toHaveTextContent('GameScene_CellQuiz');
  expect(screen.getByTestId('argame-unity-unavailable')).toBeOnTheScreen();
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

it('sign up from Login → auto-login → Home', async () => {
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
  await fireEvent.press(await screen.findByTestId('logout-button'));

  // The user taps "Log out" in the confirmation dialog
  const buttons = alertSpy.mock.calls[0][2] ?? [];
  await act(async () => buttons.find((b) => b.text === 'Log out')?.onPress?.());

  expect(await screen.findByTestId('login-screen')).toBeOnTheScreen();
  await waitFor(() => expect(secureStoreData().size).toBe(0));
  expect(asyncStorageData().size).toBe(0);
});

it('a 401 from the server on Home returns to Login with the server message', async () => {
  saveSession(jwtExpiringIn(60, USER_ID));
  installMockAdapter(
    ApiClient,
    gateway({ '/api/modules': { status: 401, data: errorBody('TOKEN_INVALID', 'Your session is not valid. Please log in again.') } }),
  );

  await render(<App />);

  expect(await screen.findByTestId('login-notice')).toHaveTextContent(/Your session is not valid/);
});
