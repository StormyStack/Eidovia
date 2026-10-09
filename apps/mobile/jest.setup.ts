/**
 * Jest setup (runs before every test file).
 *
 * Storage mocks keep their data in globalThis Maps, so tests can simulate an app
 * restart with jest.resetModules() and still see what was "on the device".
 */

process.env.EXPO_PUBLIC_API_URL = process.env.EXPO_PUBLIC_API_URL ?? 'http://api.test:8000';

// Official mock: SafeAreaProvider renders immediately with a 320x640 frame and zero insets
jest.mock('react-native-safe-area-context', () => require('react-native-safe-area-context/jest/mock').default);

type Store = Map<string, string>;
const g = globalThis as unknown as { __secureStore?: Store; __asyncStorage?: Store };
g.__secureStore ??= new Map();
g.__asyncStorage ??= new Map();

jest.mock('expo-secure-store', () => {
  const store = (globalThis as unknown as { __secureStore: Map<string, string> }).__secureStore;
  return {
    getItemAsync: jest.fn(async (key: string) => (store.has(key) ? store.get(key)! : null)),
    setItemAsync: jest.fn(async (key: string, value: string) => {
      store.set(key, String(value));
    }),
    deleteItemAsync: jest.fn(async (key: string) => {
      store.delete(key);
    }),
    isAvailableAsync: jest.fn(async () => true),
  };
});

jest.mock('@react-native-async-storage/async-storage', () => {
  const store = (globalThis as unknown as { __asyncStorage: Map<string, string> }).__asyncStorage;
  const api = {
    getItem: jest.fn(async (key: string) => (store.has(key) ? store.get(key)! : null)),
    setItem: jest.fn(async (key: string, value: string) => {
      store.set(key, value);
    }),
    removeItem: jest.fn(async (key: string) => {
      store.delete(key);
    }),
    multiGet: jest.fn(async (keys: string[]) => keys.map((k) => [k, store.has(k) ? store.get(k)! : null])),
    multiSet: jest.fn(async (pairs: [string, string][]) => {
      pairs.forEach(([k, v]) => store.set(k, v));
    }),
    multiRemove: jest.fn(async (keys: string[]) => {
      keys.forEach((k) => store.delete(k));
    }),
    getAllKeys: jest.fn(async () => [...store.keys()]),
    clear: jest.fn(async () => {
      store.clear();
    }),
  };
  return { __esModule: true, default: api, ...api };
});
