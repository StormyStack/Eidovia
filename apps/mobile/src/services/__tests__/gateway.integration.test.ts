/**
 * Contract check against a REAL running Gateway (apps/gateway).
 * Skipped unless GATEWAY_E2E_URL is set, e.g.:
 *
 *   $env:GATEWAY_E2E_URL = "http://127.0.0.1:8000"; npx jest gateway.integration
 *
 * Uses axios' xhr adapter (as on the phone) via the xhr2 XMLHttpRequest implementation.
 */

import type { ApiError } from '../ApiClient';

const GATEWAY = process.env.GATEWAY_E2E_URL;
const describeIfGateway = GATEWAY ? describe : describe.skip;

describeIfGateway('mobile services ⇄ real gateway', () => {
  let mod: {
    api: typeof import('../ApiClient');
    auth: typeof import('../AuthService');
    store: typeof import('../../store/authStore');
  };
  const g = globalThis as { XMLHttpRequest?: unknown };
  const previousXhr = g.XMLHttpRequest;
  const username = `rn_e2e_${Date.now().toString(36)}`;
  const password = 'Integration-Test-1';

  beforeAll(() => {
    g.XMLHttpRequest = require('xhr2');
    jest.isolateModules(() => {
      mod = {
        api: require('../ApiClient'),
        auth: require('../AuthService'),
        store: require('../../store/authStore'),
      };
    });
    mod.api.ApiClient.defaults.baseURL = GATEWAY;
  });

  afterAll(() => {
    g.XMLHttpRequest = previousXhr;
  });

  const state = () => mod.store.useAuthStore.getState();

  it('register → auto-login with the contract shape', async () => {
    await state().register({ username, email: `${username}@example.com`, password });
    expect(state()).toMatchObject({ isAuthenticated: true, profile: { detail_level: 1, language: 'en', username } });
    expect(typeof state().token).toBe('string');
  });

  it('duplicate sign-up → USERNAME_TAKEN with a field message', async () => {
    const error = (await mod.auth.AuthService.register({ username: username.toUpperCase(), email: `x_${username}@example.com`, password }).catch((e) => e)) as ApiError;
    expect(error.code).toBe('USERNAME_TAKEN');
    expect(error.status).toBe(409);
    expect(error.fields.username).toBeTruthy();
  });

  it('logout, wrong password → INVALID_CREDENTIALS, then login works', async () => {
    await state().logout();
    await expect(state().login(username, 'Wrong-Password-1')).rejects.toMatchObject({ code: 'INVALID_CREDENTIALS', status: 401 });
    expect(state().isAuthenticated).toBe(false);

    await state().login(username, password);
    expect(state().isAuthenticated).toBe(true);
  });

  it('profile refresh fills the server username/email', async () => {
    await state().refreshProfile();
    expect(state().profile).toMatchObject({ username, email: `${username}@example.com` });
  });

  it('module list and PDF config shape', async () => {
    const modules = await mod.api.Api.getModules();
    expect(modules.map((m) => m.module_id)).toEqual(expect.arrayContaining(['cell-explore', 'cell-quiz']));
    const config = await mod.api.Api.getModuleConfig('cell-quiz');
    expect(Object.keys(config).sort()).toEqual(['cdn_bundle_url', 'config', 'difficulty', 'module_id', 'scene_name']);
    expect(config.scene_name).toBe('GameScene_CellQuiz');
  });

  it('unknown module → MODULE_NOT_FOUND', async () => {
    await expect(mod.api.Api.getModuleConfig('nope')).rejects.toMatchObject({ code: 'MODULE_NOT_FOUND', status: 404 });
  });

  it('a rejected token signs the user out with the server message', async () => {
    mod.store.useAuthStore.setState({ token: 'not-a-real-jwt' });
    await expect(mod.api.Api.getModules()).rejects.toMatchObject({ code: 'TOKEN_INVALID' });
    expect(state()).toMatchObject({ isAuthenticated: false, notice: 'Your session is not valid. Please log in again.' });
    await expect(mod.auth.AuthService.getToken()).resolves.toBeNull();
  });
});
