/** Access to the in-memory "device storage" used by jest.setup.ts mocks. */

type Store = Map<string, string>;
const g = globalThis as unknown as { __secureStore: Store; __asyncStorage: Store };

export const secureStoreData = (): Store => g.__secureStore;
export const asyncStorageData = (): Store => g.__asyncStorage;

/** Wipe both stores (a fresh install). */
export function resetDeviceStorage(): void {
  g.__secureStore.clear();
  g.__asyncStorage.clear();
}

/** Build an unsigned JWT-shaped token with the given claims (the client never verifies signatures). */
export function fakeJwt(claims: Record<string, unknown>): string {
  const encode = (value: unknown) =>
    globalThis.btoa(JSON.stringify(value)).replace(/=+$/, '').replace(/\+/g, '-').replace(/\//g, '_');
  return `${encode({ alg: 'HS256', typ: 'JWT' })}.${encode(claims)}.signature`;
}

/** A token valid for `minutes` from now (negative = already expired). */
export function jwtExpiringIn(minutes: number, sub = '11111111-1111-4111-8111-111111111111'): string {
  const now = Math.floor(Date.now() / 1000);
  return fakeJwt({ sub, iat: now, exp: now + minutes * 60 });
}
