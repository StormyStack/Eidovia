/**
 * authStore — restoreSession on app start, login/register/logout state,
 * and 401 from any protected call → signed out with a notice.
 */

import { Api, ApiClient } from '../../services/ApiClient';
import { AuthService, STORAGE_KEYS } from '../../services/AuthService';
import { errorBody, installMockAdapter, type MockHandler } from '../../test-utils/mockAdapter';
import { asyncStorageData, jwtExpiringIn, resetDeviceStorage, secureStoreData } from '../../test-utils/storage';
import { SESSION_EXPIRED_MESSAGE, useAuthStore } from '../authStore';

const USER_ID = '3f8a1c2e-5b7d-4e9f-a1b2-c3d4e5f60718';
const PROFILE_RESPONSE = {
  user_id: USER_ID,
  username: 'Shanto',
  email: 'shanto@example.com',
  detail_level: 2,
  language: 'en',
  created_at: '2026-10-01T00:00:00+00:00',
};
const initialState = useAuthStore.getState();

const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

function server(handler: MockHandler) {
  return installMockAdapter(ApiClient, handler);
}

function storeSession(token: string) {
  secureStoreData().set(STORAGE_KEYS.token, token);
  asyncStorageData().set(STORAGE_KEYS.userId, USER_ID);
  asyncStorageData().set(STORAGE_KEYS.profile, JSON.stringify({ detail_level: 1, language: 'en', username: 'cached' }));
}

beforeEach(() => {
  resetDeviceStorage();
  useAuthStore.setState(initialState, true);
  jest.restoreAllMocks();
});

describe('initial state', () => {
  it('starts loading and signed out', () => {
    const s = useAuthStore.getState();
    expect(s.isLoading).toBe(true);
    expect(s.isAuthenticated).toBe(false);
    expect(s).toMatchObject({ user_id: null, token: null, profile: null, notice: null });
  });
});

// ============================================================
// RESTORE SESSION (app start)
// ============================================================

describe('restoreSession', () => {
  it('fresh install → signed out, loading finished', async () => {
    await useAuthStore.getState().restoreSession();
    expect(useAuthStore.getState()).toMatchObject({ isLoading: false, isAuthenticated: false });
  });

  it('saved valid session → signed in from storage, then refreshes the profile in the background', async () => {
    const token = jwtExpiringIn(60, USER_ID);
    storeSession(token);
    const calls = server(() => ({ status: 200, data: PROFILE_RESPONSE }));

    await useAuthStore.getState().restoreSession();

    expect(useAuthStore.getState()).toMatchObject({
      isLoading: false,
      isAuthenticated: true,
      user_id: USER_ID,
      token,
      profile: { username: 'cached' },
    });

    await flush();
    expect(calls[0]).toMatchObject({ url: `/api/users/${USER_ID}/profile`, authorization: `Bearer ${token}` });
    expect(useAuthStore.getState().profile).toEqual({ detail_level: 2, language: 'en', username: 'Shanto', email: 'shanto@example.com' });
    expect(JSON.parse(asyncStorageData().get(STORAGE_KEYS.profile)!).username).toBe('Shanto');
  });

  it('saved but expired token → signed out with a notice, storage purged, no network call', async () => {
    storeSession(jwtExpiringIn(-5, USER_ID));
    const calls = server(() => ({ status: 200, data: PROFILE_RESPONSE }));

    await useAuthStore.getState().restoreSession();

    expect(useAuthStore.getState()).toMatchObject({ isLoading: false, isAuthenticated: false, notice: SESSION_EXPIRED_MESSAGE });
    expect(secureStoreData().size).toBe(0);
    expect(calls).toHaveLength(0);
  });

  it('offline at start → stays signed in with the cached profile (login survives restart)', async () => {
    storeSession(jwtExpiringIn(60, USER_ID));
    server(() => 'network-error');

    await useAuthStore.getState().restoreSession();
    await flush();

    expect(useAuthStore.getState()).toMatchObject({ isAuthenticated: true, profile: { username: 'cached' } });
  });

  it('token revoked on the server → background check gets 401 → signed out with the server message', async () => {
    storeSession(jwtExpiringIn(60, USER_ID));
    server(() => ({ status: 401, data: errorBody('TOKEN_INVALID', 'Your session is not valid. Please log in again.') }));

    await useAuthStore.getState().restoreSession();
    await flush();
    await flush();

    expect(useAuthStore.getState()).toMatchObject({
      isAuthenticated: false,
      notice: 'Your session is not valid. Please log in again.',
    });
    expect(secureStoreData().size).toBe(0);
  });

  it('runs only once when called twice at the same time (StrictMode)', async () => {
    const spy = jest.spyOn(AuthService, 'getSession');
    await Promise.all([useAuthStore.getState().restoreSession(), useAuthStore.getState().restoreSession()]);
    expect(spy).toHaveBeenCalledTimes(1);
  });

  it('a storage failure during restore ends signed out (never stuck on the splash)', async () => {
    jest.spyOn(AuthService, 'getSession').mockRejectedValueOnce(new Error('storage broken'));
    await useAuthStore.getState().restoreSession();
    expect(useAuthStore.getState()).toMatchObject({ isLoading: false, isAuthenticated: false });
  });
});

// ============================================================
// LOGIN / REGISTER / LOGOUT
// ============================================================

describe('login, register, logout', () => {
  it('login → signed in, typed username shown immediately, server username after refresh', async () => {
    const token = jwtExpiringIn(60, USER_ID);
    server((req) =>
      req.url === '/api/auth/login'
        ? { status: 200, data: { user_id: USER_ID, token, profile: { detail_level: 2, language: 'en' } } }
        : { status: 200, data: PROFILE_RESPONSE },
    );
    useAuthStore.setState({ notice: 'old notice', isLoading: false });

    await useAuthStore.getState().login('shanto', 'pw');

    expect(useAuthStore.getState()).toMatchObject({
      isAuthenticated: true,
      user_id: USER_ID,
      token,
      notice: null,
      profile: { detail_level: 2, language: 'en', username: 'shanto' },
    });
    await flush();
    expect(useAuthStore.getState().profile?.username).toBe('Shanto');
  });

  it('failed login → rejects with ApiError and the state stays signed out', async () => {
    server(() => ({ status: 401, data: errorBody('INVALID_CREDENTIALS', 'Incorrect username or password.') }));
    useAuthStore.setState({ isLoading: false });

    await expect(useAuthStore.getState().login('shanto', 'bad')).rejects.toMatchObject({ code: 'INVALID_CREDENTIALS' });
    expect(useAuthStore.getState()).toMatchObject({ isAuthenticated: false, token: null });
  });

  it('register → signed in (auto-login) with username and email', async () => {
    const token = jwtExpiringIn(60, USER_ID);
    server(() => ({ status: 201, data: { user_id: USER_ID, token, profile: { detail_level: 1, language: 'en' } } }));

    await useAuthStore.getState().register({ username: 'shanto', email: 'Shanto@Example.com', password: 'Correct-Horse-9' });

    expect(useAuthStore.getState()).toMatchObject({
      isAuthenticated: true,
      profile: { username: 'shanto', email: 'shanto@example.com' },
    });
  });

  it('logout → state and storage cleared', async () => {
    storeSession(jwtExpiringIn(60, USER_ID));
    server(() => ({ status: 200, data: PROFILE_RESPONSE }));
    await useAuthStore.getState().restoreSession();

    await useAuthStore.getState().logout();

    expect(useAuthStore.getState()).toMatchObject({ isAuthenticated: false, token: null, user_id: null, profile: null });
    expect(secureStoreData().size).toBe(0);
    expect(asyncStorageData().size).toBe(0);
  });
});

// ============================================================
// 401 FROM ANY PROTECTED CALL
// ============================================================

describe('401 handling end-to-end (ApiClient → authStore)', () => {
  it('a 401 on GET /api/modules signs the user out with the server message', async () => {
    const token = jwtExpiringIn(60, USER_ID);
    storeSession(token);
    server((req) =>
      req.url === '/api/modules'
        ? { status: 401, data: errorBody('TOKEN_EXPIRED', 'Your session has expired. Please log in again.') }
        : { status: 200, data: PROFILE_RESPONSE },
    );
    await useAuthStore.getState().restoreSession();
    await flush();

    await expect(Api.getModules()).rejects.toMatchObject({ code: 'TOKEN_EXPIRED' });

    expect(useAuthStore.getState()).toMatchObject({ isAuthenticated: false, notice: 'Your session has expired. Please log in again.' });
    expect(secureStoreData().size).toBe(0);
  });

  it('handleUnauthorized is a no-op when already signed out', async () => {
    await useAuthStore.getState().handleUnauthorized('x');
    expect(useAuthStore.getState().notice).toBeNull();
  });

  it('clearNotice removes the message', () => {
    useAuthStore.setState({ notice: 'hello' });
    useAuthStore.getState().clearNotice();
    expect(useAuthStore.getState().notice).toBeNull();
  });

  it('refreshProfile ignores a response for a session that has since changed', async () => {
    const tokenA = jwtExpiringIn(60, USER_ID);
    let release: () => void = () => undefined;
    server(
      () =>
        new Promise((resolve) => {
          release = () => resolve({ status: 200, data: PROFILE_RESPONSE });
        }),
    );
    useAuthStore.setState({ user_id: USER_ID, token: tokenA, isAuthenticated: true, profile: { detail_level: 1, language: 'en', username: 'A' } });

    const pending = useAuthStore.getState().refreshProfile();
    await flush(); // let the request reach the fake server
    useAuthStore.setState({ token: 'another-session' }); // user switched session meanwhile
    release();
    await pending;

    expect(useAuthStore.getState().profile?.username).toBe('A');
  });
});
