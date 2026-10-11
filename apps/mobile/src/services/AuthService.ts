/**
 * AuthService — login/register, JWT storage and session persistence.
 *
 * Public API from the PDF (§3): login, getToken, getUserId, logout. Added: register.
 *
 * DEVIATION FROM PDF (see apps/mobile/README.md): the JWT is stored in expo-secure-store
 * (Android Keystore / iOS Keychain) instead of AsyncStorage, which is unencrypted.
 * Non-sensitive data (user_id, cached profile) stays in AsyncStorage, under the PDF's key names.
 */

import AsyncStorage from '@react-native-async-storage/async-storage';
import * as SecureStore from 'expo-secure-store';

import { ApiClient, ApiError, ERROR_MESSAGES } from './ApiClient';
import type { RegisterInput, StoredProfile, UserProfile } from './types';

export type { UserProfile } from './types';

export const STORAGE_KEYS = {
  token: 'auth_token', // SecureStore (PDF key name)
  userId: 'user_id', // AsyncStorage (PDF key name)
  profile: 'auth_profile', // AsyncStorage: { detail_level, language, username?, email? }
} as const;

export interface StoredSession {
  token: string;
  userId: string;
  profile: StoredProfile | null;
}

// ============================================================
// HELPERS
// ============================================================

function assertAuthResponse(data: unknown): UserProfile {
  const value = data as Partial<UserProfile> | null;
  const ok =
    !!value &&
    typeof value.user_id === 'string' &&
    typeof value.token === 'string' &&
    !!value.profile &&
    typeof value.profile.detail_level === 'number' &&
    typeof value.profile.language === 'string';
  if (!ok) throw new ApiError('UNKNOWN_ERROR', ERROR_MESSAGES.UNEXPECTED_RESPONSE);
  return value as UserProfile;
}

async function clearStoredSession(): Promise<void> {
  // allSettled: one failing store must not stop the other from being purged
  await Promise.allSettled([
    SecureStore.deleteItemAsync(STORAGE_KEYS.token),
    AsyncStorage.multiRemove([STORAGE_KEYS.userId, STORAGE_KEYS.profile]),
  ]);
}

async function persistSession(data: UserProfile, extra: Partial<StoredProfile>): Promise<void> {
  const profile: StoredProfile = { ...data.profile, ...extra };
  try {
    await SecureStore.setItemAsync(STORAGE_KEYS.token, data.token);
    await AsyncStorage.multiSet([
      [STORAGE_KEYS.userId, data.user_id],
      [STORAGE_KEYS.profile, JSON.stringify(profile)],
    ]);
  } catch {
    await clearStoredSession(); // never leave half a session behind
    throw new ApiError('STORAGE_ERROR', 'Could not save your login on this device. Please try again.');
  }
}

function parseProfile(raw: string | null): StoredProfile | null {
  if (!raw) return null;
  try {
    const value = JSON.parse(raw) as StoredProfile;
    return typeof value?.detail_level === 'number' && typeof value?.language === 'string' ? value : null;
  } catch {
    return null;
  }
}

/** Read `exp` (seconds since epoch) from a JWT without verifying it (the server verifies). */
export function getTokenExpiry(token: string): number | null {
  const payload = token.split('.')[1];
  if (!payload) return null;
  try {
    const base64 = payload.replace(/-/g, '+').replace(/_/g, '/');
    const padded = base64.padEnd(Math.ceil(base64.length / 4) * 4, '=');
    const claims = JSON.parse(globalThis.atob(padded)) as { exp?: unknown };
    return typeof claims.exp === 'number' ? claims.exp : null;
  } catch {
    return null;
  }
}

/** True if the token's exp has passed (with a small clock-skew margin). Unknown exp → not expired. */
export function isTokenExpired(token: string, nowMs: number = Date.now(), skewSeconds = 30): boolean {
  const exp = getTokenExpiry(token);
  return exp !== null && exp * 1000 <= nowMs + skewSeconds * 1000;
}

// ============================================================
// SERVICE
// ============================================================

export const AuthService = {
  /** POST /api/auth/login → stores the session; rejects with ApiError (e.g. INVALID_CREDENTIALS). */
  async login(username: string, password: string): Promise<UserProfile> {
    const res = await ApiClient.post('/api/auth/login', { username, password });
    const data = assertAuthResponse(res.data);
    await persistSession(data, { username: username.trim() });
    return data;
  },

  /** POST /api/auth/register → auto-login (same response shape as login). */
  async register(input: RegisterInput): Promise<UserProfile> {
    const body: RegisterInput = {
      username: input.username,
      email: input.email,
      password: input.password,
      ...(input.language ? { language: input.language } : {}),
    };
    const res = await ApiClient.post('/api/auth/register', body);
    const data = assertAuthResponse(res.data);
    await persistSession(data, { username: input.username.trim(), email: input.email.trim().toLowerCase() });
    return data;
  },

  async getToken(): Promise<string | null> {
    try {
      return await SecureStore.getItemAsync(STORAGE_KEYS.token);
    } catch {
      return null;
    }
  },

  async getUserId(): Promise<string | null> {
    try {
      return await AsyncStorage.getItem(STORAGE_KEYS.userId);
    } catch {
      return null;
    }
  },

  async getProfile(): Promise<StoredProfile | null> {
    try {
      return parseProfile(await AsyncStorage.getItem(STORAGE_KEYS.profile));
    } catch {
      return null;
    }
  },

  /** Cache non-sensitive profile data (e.g. username for the Home greeting). */
  async saveProfile(profile: StoredProfile): Promise<void> {
    try {
      await AsyncStorage.setItem(STORAGE_KEYS.profile, JSON.stringify(profile));
    } catch {
      // Cache only: losing it just means a generic greeting until the next refresh
    }
  },

  /** The stored session, or null. Half-stored sessions are purged. */
  async getSession(): Promise<StoredSession | null> {
    const [token, userId, profile] = await Promise.all([
      AuthService.getToken(),
      AuthService.getUserId(),
      AuthService.getProfile(),
    ]);
    if (!token || !userId) {
      if (token || userId) await clearStoredSession();
      return null;
    }
    return { token, userId, profile };
  },

  /** Purge every stored credential (token, user_id, cached profile) and notify the server. */
  async logout(): Promise<void> {
    try {
      await ApiClient.post('/api/auth/logout', {});
    } catch (e) {
      // Ignore network errors; always clear the local session so the user isn't trapped
    }
    await clearStoredSession();
  },
};
