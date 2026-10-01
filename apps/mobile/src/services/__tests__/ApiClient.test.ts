/**
 * ApiClient — PDF "API Testing": HTTP contract, automatic Bearer injection,
 * 5 s timeout handling, 401 → clean logout, 0 unhandled promise rejections.
 */

import http from 'http';
import type { AddressInfo } from 'net';
import axios from 'axios';

import { Api, ApiClient, ApiError, configureApiAuth, ERROR_MESSAGES, toApiError } from '../ApiClient';
import { errorBody, installMockAdapter, type MockHandler } from '../../test-utils/mockAdapter';

const ok = (data: unknown = {}) => ({ status: 200, data });
let currentToken: string | null;
let onUnauthorized: jest.Mock;

function useHandler(handler: MockHandler) {
  return installMockAdapter(ApiClient, handler);
}

beforeEach(() => {
  currentToken = null;
  onUnauthorized = jest.fn();
  configureApiAuth({ getToken: () => currentToken, onUnauthorized });
});

// ============================================================
// CONFIGURATION
// ============================================================

describe('configuration', () => {
  it('uses EXPO_PUBLIC_API_URL as base URL and a 5 s timeout', () => {
    expect(ApiClient.defaults.baseURL).toBe('http://api.test:8000');
    expect(ApiClient.defaults.timeout).toBe(5000);
  });

  it('rejects with CONFIG_ERROR (and sends nothing) when the API URL is not configured', async () => {
    try {
      await jest.isolateModulesAsync(async () => {
        jest.doMock('../../config', () => ({ API_URL: '', API_TIMEOUT_MS: 5000, CONFIG_ERROR: 'EXPO_PUBLIC_API_URL is not set.' }));
        const isolated = require('../ApiClient') as typeof import('../ApiClient');
        const calls = installMockAdapter(isolated.ApiClient, () => ok());

        const error = await isolated.ApiClient.get('/api/modules').catch((e: unknown) => e);

        expect(error).toBeInstanceOf(isolated.ApiError);
        expect((error as ApiError).code).toBe('CONFIG_ERROR');
        expect(calls).toHaveLength(0);
      });
    } finally {
      jest.dontMock('../../config'); // doMock outlives isolateModules; don't leak into later tests
    }
  });
});

// ============================================================
// BEARER INJECTION
// ============================================================

describe('Authorization header', () => {
  it('injects the current token as a Bearer header on protected routes', async () => {
    currentToken = 'token-abc';
    const calls = useHandler(() => ok([]));

    await ApiClient.get('/api/modules');

    expect(calls[0].authorization).toBe('Bearer token-abc');
  });

  it('reads the token at request time (a new login is picked up immediately)', async () => {
    const calls = useHandler(() => ok([]));
    currentToken = 'first';
    await ApiClient.get('/api/modules');
    currentToken = 'second';
    await ApiClient.get('/api/modules');

    expect(calls.map((c) => c.authorization)).toEqual(['Bearer first', 'Bearer second']);
  });

  it('sends no Authorization header when signed out', async () => {
    const calls = useHandler(() => ok([]));
    await ApiClient.get('/api/modules');
    expect(calls[0].authorization).toBeNull();
  });

  it.each(['/api/auth/login', '/api/auth/register', 'http://api.test:8000/api/auth/login?x=1'])(
    'never sends a stored token to the public auth route %s',
    async (url) => {
      currentToken = 'old-token';
      const calls = useHandler(() => ok({}));
      await ApiClient.post(url, {});
      expect(calls[0].authorization).toBeNull();
    },
  );
});

// ============================================================
// 401 HANDLING
// ============================================================

describe('401 handling', () => {
  it('calls the unauthorized handler once and rejects with the server error', async () => {
    currentToken = 'expired-token';
    useHandler(() => ({ status: 401, data: errorBody('TOKEN_EXPIRED', 'Your session has expired. Please log in again.') }));

    const error = await ApiClient.get('/api/modules').catch((e: unknown) => e);

    expect(onUnauthorized).toHaveBeenCalledTimes(1);
    expect(onUnauthorized.mock.calls[0][0]).toMatchObject({ code: 'TOKEN_EXPIRED' });
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).code).toBe('TOKEN_EXPIRED');
  });

  it('treats a 401 from login as a form error, not a logout', async () => {
    currentToken = 'still-valid';
    useHandler(() => ({ status: 401, data: errorBody('INVALID_CREDENTIALS', 'Incorrect username or password.') }));

    const error = (await ApiClient.post('/api/auth/login', { username: 'a', password: 'b' }).catch((e) => e)) as ApiError;

    expect(error.code).toBe('INVALID_CREDENTIALS');
    expect(onUnauthorized).not.toHaveBeenCalled();
  });

  it('ignores a late 401 for a token that is no longer current', async () => {
    currentToken = 'old-session';
    useHandler(() => {
      currentToken = 'new-session'; // user logged in again while the request was in flight
      return { status: 401, data: errorBody('TOKEN_EXPIRED', 'expired') };
    });

    await ApiClient.get('/api/modules').catch(() => undefined);

    expect(onUnauthorized).not.toHaveBeenCalled();
  });

  it('does not call the handler for a 401 when no token was sent', async () => {
    useHandler(() => ({ status: 401, data: errorBody('TOKEN_MISSING', 'log in') }));
    await ApiClient.get('/api/modules').catch(() => undefined);
    expect(onUnauthorized).not.toHaveBeenCalled();
  });

  it('still rejects cleanly if the unauthorized handler itself fails', async () => {
    currentToken = 't';
    onUnauthorized.mockRejectedValue(new Error('storage exploded'));
    useHandler(() => ({ status: 401, data: errorBody('TOKEN_INVALID', 'invalid') }));

    const error = (await ApiClient.get('/api/modules').catch((e) => e)) as ApiError;

    expect(error.code).toBe('TOKEN_INVALID');
  });
});

// ============================================================
// ERROR NORMALISATION
// ============================================================

describe('error object for the UI', () => {
  it('maps the contract error body, including field errors', async () => {
    useHandler(() => ({
      status: 400,
      data: errorBody('VALIDATION_ERROR', 'Please fix the highlighted fields.', { email: 'Enter a valid email address.', bad: 7 as never }),
    }));

    const error = (await ApiClient.post('/api/auth/register', {}).catch((e) => e)) as ApiError;

    expect(error).toMatchObject({
      code: 'VALIDATION_ERROR',
      status: 400,
      message: 'Please fix the highlighted fields.',
      fields: { email: 'Enter a valid email address.' },
    });
  });

  it.each([
    [409, errorBody('USERNAME_TAKEN', 'This username is already taken.'), 'USERNAME_TAKEN'],
    [404, errorBody('MODULE_NOT_FOUND', 'This module could not be found.'), 'MODULE_NOT_FOUND'],
    [502, '<html>Bad gateway</html>', 'INTERNAL_ERROR'],
    [404, '<html>not found</html>', 'UNKNOWN_ERROR'],
    [400, { detail: { code: 'X' } }, 'X'],
  ])('status %i maps to %s', async (status, data, code) => {
    useHandler(() => ({ status, data }));
    const error = (await ApiClient.get('/api/anything').catch((e) => e)) as ApiError;
    expect(error.code).toBe(code);
    expect(error.status).toBe(status);
    expect(typeof error.message).toBe('string');
  });

  it('maps an unreachable server to NETWORK_ERROR (retryable)', async () => {
    useHandler(() => 'network-error');
    const error = (await ApiClient.get('/api/modules').catch((e) => e)) as ApiError;
    expect(error.code).toBe('NETWORK_ERROR');
    expect(error.message).toBe(ERROR_MESSAGES.NETWORK_ERROR);
    expect(error.isRetryable).toBe(true);
    expect(error.status).toBeNull();
  });

  it('maps a timeout to TIMEOUT (retryable)', async () => {
    useHandler(() => 'timeout');
    const error = (await ApiClient.get('/api/modules').catch((e) => e)) as ApiError;
    expect(error.code).toBe('TIMEOUT');
    expect(error.isRetryable).toBe(true);
  });

  it('maps an aborted request to CANCELLED', async () => {
    useHandler(() => 'never');
    const controller = new AbortController();
    const pending = ApiClient.get('/api/modules', { signal: controller.signal }).catch((e) => e);
    controller.abort();
    const error = (await pending) as ApiError;
    expect(error.code).toBe('CANCELLED');
    expect(error.isRetryable).toBe(false);
  });

  it('toApiError passes ApiErrors through and wraps unknown values', () => {
    const original = new ApiError('EMAIL_TAKEN', 'taken', 409);
    expect(toApiError(original)).toBe(original);
    expect(toApiError(new Error('boom')).code).toBe('UNKNOWN_ERROR');
    expect(toApiError('weird').code).toBe('UNKNOWN_ERROR');
    expect(toApiError(new ApiError('X', 'y'))).toBeInstanceOf(ApiError);
  });
});

// ============================================================
// REAL TIMEOUT
// axios' xhr adapter (the one React Native uses on the phone), backed by the xhr2
// XMLHttpRequest implementation, against a local server that never answers.
// jest-expo loads axios' browser build, which decides at load time whether XHR exists,
// so a fresh copy of the modules is loaded after providing XMLHttpRequest.
// ============================================================

describe('real timeout', () => {
  let server: http.Server;
  let baseURL: string;

  beforeAll(async () => {
    server = http.createServer(() => {
      /* never respond */
    });
    await new Promise<void>((resolve) => server.listen(0, '127.0.0.1', resolve));
    baseURL = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
  });

  afterAll(async () => {
    server.closeAllConnections?.();
    await new Promise<void>((resolve) => server.close(() => resolve()));
  });

  it('rejects with TIMEOUT and leaves no unhandled promise rejection', async () => {
    const g = globalThis as { XMLHttpRequest?: unknown };
    const previousXhr = g.XMLHttpRequest;
    g.XMLHttpRequest = require('xhr2');

    const unhandled: unknown[] = [];
    const listener = (reason: unknown) => unhandled.push(reason);
    process.on('unhandledRejection', listener);
    try {
      await jest.isolateModulesAsync(async () => {
        const fresh = require('../ApiClient') as typeof import('../ApiClient');
        const started = Date.now();

        const error = (await fresh.ApiClient.get('/slow', { baseURL, timeout: 300 }).catch((e: unknown) => e)) as ApiError;

        expect(error).toBeInstanceOf(fresh.ApiError);
        expect(error.code).toBe('TIMEOUT');
        expect(error.message).toBe(ERROR_MESSAGES.TIMEOUT);
        expect(Date.now() - started).toBeGreaterThanOrEqual(250);
        expect(fresh.ApiClient.defaults.timeout).toBe(5000); // the app-wide limit stays 5 s
      });
      await new Promise((resolve) => setTimeout(resolve, 50)); // let any stray rejection surface
      expect(unhandled).toEqual([]);
    } finally {
      process.off('unhandledRejection', listener);
      g.XMLHttpRequest = previousXhr;
    }
  });
});

// ============================================================
// TYPED ENDPOINTS
// ============================================================

describe('Api endpoints', () => {
  it('getModules returns the list', async () => {
    const modules = [{ module_id: 'cell-explore', title: 'Explore', description: '', difficulty: 1, thumbnail_url: null }];
    const calls = useHandler(() => ok(modules));
    await expect(Api.getModules()).resolves.toEqual(modules);
    expect(calls[0]).toMatchObject({ method: 'GET', url: '/api/modules' });
  });

  it('getModuleConfig URL-encodes the id and returns the PDF config shape', async () => {
    const config = { module_id: 'a b', scene_name: 'GameScene_CellQuiz', cdn_bundle_url: 'https://cdn/x', difficulty: 3, config: {} };
    const calls = useHandler(() => ok(config));
    await expect(Api.getModuleConfig('a b')).resolves.toEqual(config);
    expect(calls[0].url).toBe('/api/modules/a%20b/config');
  });

  it('getUserProfile calls the PDF profile path', async () => {
    const calls = useHandler(() => ok({ user_id: 'u1', username: 'shanto', email: null, detail_level: 1, language: 'en', created_at: 'x' }));
    await expect(Api.getUserProfile('u1')).resolves.toMatchObject({ username: 'shanto' });
    expect(calls[0].url).toBe('/api/users/u1/profile');
  });

  it.each([
    ['getModules', () => Api.getModules(), '<html>captive portal</html>'],
    ['getModuleConfig', () => Api.getModuleConfig('x'), { module_id: 'x' }],
    ['getUserProfile', () => Api.getUserProfile('u'), []],
  ])('%s rejects an unexpected response shape with UNKNOWN_ERROR', async (_name, call, data) => {
    useHandler(() => ok(data));
    const error = (await call().catch((e: unknown) => e)) as ApiError;
    expect(error).toBeInstanceOf(ApiError);
    expect(error.code).toBe('UNKNOWN_ERROR');
  });

  it('isCancel errors created by axios itself are recognised', () => {
    expect(toApiError(new axios.CanceledError()).code).toBe('CANCELLED');
  });
});
