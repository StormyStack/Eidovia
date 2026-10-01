/**
 * AuthService — PDF "Functional Testing / Auth Lifecycle": stores JWT, token survives
 * restart, logout purges stored credentials (zero token leakage after logout).
 */

import * as SecureStore from 'expo-secure-store';

import { ApiClient, ApiError } from '../ApiClient';
import { AuthService, STORAGE_KEYS, getTokenExpiry, isTokenExpired } from '../AuthService';
import { errorBody, installMockAdapter } from '../../test-utils/mockAdapter';
import { asyncStorageData, fakeJwt, jwtExpiringIn, resetDeviceStorage, secureStoreData } from '../../test-utils/storage';

const USER_ID = '3f8a1c2e-5b7d-4e9f-a1b2-c3d4e5f60718';
const TOKEN = jwtExpiringIn(60, USER_ID);
const AUTH_RESPONSE = { user_id: USER_ID, token: TOKEN, profile: { detail_level: 1, language: 'en' } };

beforeEach(() => {
  resetDeviceStorage();
  jest.clearAllMocks();
});

function allAsyncStorageValues(): string {
  return [...asyncStorageData().values()].join('\n');
}

// ============================================================
// LOGIN
// ============================================================

describe('login', () => {
  it('posts exactly { username, password } and returns the PDF response shape', async () => {
    const calls = installMockAdapter(ApiClient, () => ({ status: 200, data: AUTH_RESPONSE }));

    const result = await AuthService.login('shanto', 'Correct-Horse-9');

    expect(calls).toHaveLength(1);
    expect(calls[0]).toMatchObject({ method: 'POST', url: '/api/auth/login' });
    expect(calls[0].body).toEqual({ username: 'shanto', password: 'Correct-Horse-9' });
    expect(result).toEqual(AUTH_RESPONSE);
  });

  it('stores the JWT in SecureStore — never in AsyncStorage', async () => {
    installMockAdapter(ApiClient, () => ({ status: 200, data: AUTH_RESPONSE }));

    await AuthService.login('shanto', 'pw');

    expect(secureStoreData().get(STORAGE_KEYS.token)).toBe(TOKEN);
    expect(allAsyncStorageValues()).not.toContain(TOKEN);
  });

  it('stores user_id and the non-sensitive profile in AsyncStorage (PDF key names)', async () => {
    installMockAdapter(ApiClient, () => ({ status: 200, data: AUTH_RESPONSE }));

    await AuthService.login('  shanto ', 'pw');

    expect(asyncStorageData().get('user_id')).toBe(USER_ID);
    expect(JSON.parse(asyncStorageData().get(STORAGE_KEYS.profile)!)).toEqual({
      detail_level: 1,
      language: 'en',
      username: 'shanto',
    });
    await expect(AuthService.getToken()).resolves.toBe(TOKEN);
    await expect(AuthService.getUserId()).resolves.toBe(USER_ID);
  });

  it.each([
    ['wrong password', () => ({ status: 401, data: errorBody('INVALID_CREDENTIALS', 'Incorrect username or password.') }), 'INVALID_CREDENTIALS'],
    ['server offline', () => 'network-error' as const, 'NETWORK_ERROR'],
    ['slow server', () => 'timeout' as const, 'TIMEOUT'],
    ['garbage response', () => ({ status: 200, data: '<html>portal</html>' }), 'UNKNOWN_ERROR'],
    ['missing token', () => ({ status: 200, data: { user_id: USER_ID, profile: { detail_level: 1, language: 'en' } } }), 'UNKNOWN_ERROR'],
  ])('%s → rejects with %s and stores nothing', async (_label, reply, code) => {
    installMockAdapter(ApiClient, reply as never);

    const error = (await AuthService.login('shanto', 'pw').catch((e) => e)) as ApiError;

    expect(error).toBeInstanceOf(ApiError);
    expect(error.code).toBe(code);
    expect(secureStoreData().size).toBe(0);
    expect(asyncStorageData().size).toBe(0);
  });

  it('cleans up and reports STORAGE_ERROR if the device refuses to save the session', async () => {
    installMockAdapter(ApiClient, () => ({ status: 200, data: AUTH_RESPONSE }));
    (SecureStore.setItemAsync as jest.Mock).mockRejectedValueOnce(new Error('keystore locked'));

    const error = (await AuthService.login('shanto', 'pw').catch((e) => e)) as ApiError;

    expect(error.code).toBe('STORAGE_ERROR');
    expect(secureStoreData().size).toBe(0);
    expect(asyncStorageData().size).toBe(0);
  });
});

// ============================================================
// REGISTER
// ============================================================

describe('register', () => {
  it('posts the sign-up body (no language when omitted) and auto-logs in', async () => {
    const calls = installMockAdapter(ApiClient, () => ({ status: 201, data: AUTH_RESPONSE }));

    const result = await AuthService.register({ username: 'shanto', email: ' Shanto@Example.com ', password: 'Correct-Horse-9' });

    expect(calls[0]).toMatchObject({ method: 'POST', url: '/api/auth/register' });
    expect(calls[0].body).toEqual({ username: 'shanto', email: ' Shanto@Example.com ', password: 'Correct-Horse-9' });
    expect(result).toEqual(AUTH_RESPONSE);
    expect(secureStoreData().get(STORAGE_KEYS.token)).toBe(TOKEN);
    expect(JSON.parse(asyncStorageData().get(STORAGE_KEYS.profile)!)).toMatchObject({
      username: 'shanto',
      email: 'shanto@example.com',
    });
  });

  it('sends language when provided', async () => {
    const calls = installMockAdapter(ApiClient, () => ({ status: 201, data: AUTH_RESPONSE }));
    await AuthService.register({ username: 'u', email: 'u@example.com', password: 'Correct-Horse-9', language: 'bn' });
    expect(calls[0].body).toMatchObject({ language: 'bn' });
  });

  it('surfaces 409 USERNAME_TAKEN with its field message and stores nothing', async () => {
    installMockAdapter(ApiClient, () => ({
      status: 409,
      data: errorBody('USERNAME_TAKEN', 'This username is already taken.', { username: 'This username is already taken.' }),
    }));

    const error = (await AuthService.register({ username: 'taken', email: 't@example.com', password: 'Correct-Horse-9' }).catch((e) => e)) as ApiError;

    expect(error.code).toBe('USERNAME_TAKEN');
    expect(error.fields.username).toBe('This username is already taken.');
    expect(secureStoreData().size).toBe(0);
  });
});

// ============================================================
// RESTART + LOGOUT
// ============================================================

describe('session persistence', () => {
  it('token survives an app restart (fresh modules, same device storage)', async () => {
    installMockAdapter(ApiClient, () => ({ status: 200, data: AUTH_RESPONSE }));
    await AuthService.login('shanto', 'pw');

    let restarted: typeof import('../AuthService');
    jest.isolateModules(() => {
      restarted = require('../AuthService');
    });

    await expect(restarted!.AuthService.getToken()).resolves.toBe(TOKEN);
    await expect(restarted!.AuthService.getUserId()).resolves.toBe(USER_ID);
    await expect(restarted!.AuthService.getSession()).resolves.toEqual({
      token: TOKEN,
      userId: USER_ID,
      profile: { detail_level: 1, language: 'en', username: 'shanto' },
    });
  });

  it('logout purges every stored credential (zero token leakage)', async () => {
    installMockAdapter(ApiClient, () => ({ status: 200, data: AUTH_RESPONSE }));
    await AuthService.login('shanto', 'pw');

    await AuthService.logout();

    expect(secureStoreData().size).toBe(0);
    expect(asyncStorageData().size).toBe(0);
    await expect(AuthService.getToken()).resolves.toBeNull();
    await expect(AuthService.getUserId()).resolves.toBeNull();
    await expect(AuthService.getSession()).resolves.toBeNull();
  });

  it('getSession purges a half-stored session (token without user_id)', async () => {
    secureStoreData().set(STORAGE_KEYS.token, TOKEN);

    await expect(AuthService.getSession()).resolves.toBeNull();
    expect(secureStoreData().size).toBe(0);
  });

  it('getSession returns null on a fresh install', async () => {
    await expect(AuthService.getSession()).resolves.toBeNull();
  });

  it('ignores a corrupt cached profile', async () => {
    asyncStorageData().set(STORAGE_KEYS.profile, '{not json');
    await expect(AuthService.getProfile()).resolves.toBeNull();
    asyncStorageData().set(STORAGE_KEYS.profile, JSON.stringify({ language: 'en' }));
    await expect(AuthService.getProfile()).resolves.toBeNull();
  });

  it('saveProfile caches the profile and never throws', async () => {
    await AuthService.saveProfile({ detail_level: 2, language: 'bn', username: 'x' });
    await expect(AuthService.getProfile()).resolves.toEqual({ detail_level: 2, language: 'bn', username: 'x' });

    const AsyncStorage = require('@react-native-async-storage/async-storage').default;
    (AsyncStorage.setItem as jest.Mock).mockRejectedValueOnce(new Error('disk full'));
    await expect(AuthService.saveProfile({ detail_level: 1, language: 'en' })).resolves.toBeUndefined();
  });

  it('reading storage never throws (returns null instead)', async () => {
    const AsyncStorage = require('@react-native-async-storage/async-storage').default;
    (SecureStore.getItemAsync as jest.Mock).mockRejectedValueOnce(new Error('keystore'));
    (AsyncStorage.getItem as jest.Mock).mockRejectedValueOnce(new Error('io')).mockRejectedValueOnce(new Error('io'));

    await expect(AuthService.getToken()).resolves.toBeNull();
    await expect(AuthService.getUserId()).resolves.toBeNull();
    await expect(AuthService.getProfile()).resolves.toBeNull();
  });
});

// ============================================================
// TOKEN EXPIRY HELPERS
// ============================================================

describe('token expiry', () => {
  it('reads exp from a JWT', () => {
    expect(getTokenExpiry(fakeJwt({ exp: 1_900_000_000 }))).toBe(1_900_000_000);
  });

  it.each(['not-a-jwt', 'a.b', 'a.!!!.c', fakeJwt({ sub: 'x' })])('returns null for %s', (token) => {
    expect(getTokenExpiry(token)).toBeNull();
  });

  it('detects expired and valid tokens (with clock skew)', () => {
    expect(isTokenExpired(jwtExpiringIn(-1))).toBe(true);
    expect(isTokenExpired(jwtExpiringIn(60))).toBe(false);
    expect(isTokenExpired(fakeJwt({ exp: 1000 }), 1000 * 1000 - 10_000)).toBe(true); // within 30 s skew
    expect(isTokenExpired('opaque-token')).toBe(false); // unknown → let the server decide
  });
});
