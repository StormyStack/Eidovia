/**
 * authStore — global auth state (PDF §1: user_id, token, profile) built with zustand.
 *
 * - isLoading: true until restoreSession() finishes at app start (drives the splash screen).
 *   Login/SignUp screens track their own "submitting" state, so the splash never flashes.
 * - isAuthenticated: decides which navigation stack App.tsx shows.
 * - notice: a one-off message for the Login screen (e.g. "Your session has expired").
 *
 * Also registers ApiClient's auth hooks: the in-memory token for the Bearer header, and
 * handleUnauthorized() for 401s (clear session → App.tsx shows Login).
 */

import { create } from 'zustand';

import { Api, configureApiAuth } from '../services/ApiClient';
import { AuthService, isTokenExpired } from '../services/AuthService';
import type { RegisterInput, StoredProfile } from '../services/types';

export const SESSION_EXPIRED_MESSAGE = 'Your session has expired. Please log in again.';

export interface AuthState {
  user_id: string | null;
  token: string | null;
  profile: StoredProfile | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  notice: string | null;

  /** Load a saved session on app start (PDF Sprint 1: login survives app restart). */
  restoreSession: () => Promise<void>;
  /** Rejects with ApiError (INVALID_CREDENTIALS, NETWORK_ERROR, TIMEOUT, ...). */
  login: (username: string, password: string) => Promise<void>;
  /** Rejects with ApiError (VALIDATION_ERROR, USERNAME_TAKEN, EMAIL_TAKEN, ...). */
  register: (input: RegisterInput) => Promise<void>;
  logout: () => Promise<void>;
  /** Fetch GET /api/users/{id}/profile and cache it (username for the greeting). Never rejects. */
  refreshProfile: () => Promise<void>;
  /** Called by ApiClient on 401 from a protected route. */
  handleUnauthorized: (message?: string) => Promise<void>;
  clearNotice: () => void;
}

const SIGNED_OUT = {
  user_id: null,
  token: null,
  profile: null,
  isAuthenticated: false,
} as const;

let restoreInFlight: Promise<void> | null = null;

export const useAuthStore = create<AuthState>()((set, get) => ({
  ...SIGNED_OUT,
  isLoading: true,
  notice: null,

  restoreSession: () => {
    // De-duplicate (React StrictMode runs effects twice in development)
    if (restoreInFlight) return restoreInFlight;

    restoreInFlight = (async () => {
      set({ isLoading: true });
      try {
        const session = await AuthService.getSession();
        if (!session) {
          set({ ...SIGNED_OUT });
        } else if (isTokenExpired(session.token)) {
          await AuthService.logout();
          set({ ...SIGNED_OUT, notice: SESSION_EXPIRED_MESSAGE });
        } else {
          set({
            user_id: session.userId,
            token: session.token,
            profile: session.profile,
            isAuthenticated: true,
          });
        }
      } catch {
        set({ ...SIGNED_OUT });
      } finally {
        set({ isLoading: false });
        restoreInFlight = null;
      }

      // Revalidate in the background: a revoked/expired token → 401 → back to Login;
      // offline → keep the cached session (the user stays logged in).
      if (get().isAuthenticated) void get().refreshProfile();
    })();

    return restoreInFlight;
  },

  login: async (username, password) => {
    const data = await AuthService.login(username, password);
    set({
      user_id: data.user_id,
      token: data.token,
      profile: { ...data.profile, username: username.trim() },
      isAuthenticated: true,
      notice: null,
    });
    void get().refreshProfile();
  },

  register: async (input) => {
    const data = await AuthService.register(input);
    set({
      user_id: data.user_id,
      token: data.token,
      profile: { ...data.profile, username: input.username.trim(), email: input.email.trim().toLowerCase() },
      isAuthenticated: true,
      notice: null,
    });
  },

  logout: async () => {
    await AuthService.logout();
    set({ ...SIGNED_OUT, notice: null });
  },

  refreshProfile: async () => {
    const { user_id, token } = get();
    if (!user_id || !token) return;
    try {
      const details = await Api.getUserProfile(user_id);
      if (get().token !== token) return; // the session changed while we were waiting
      const profile: StoredProfile = {
        detail_level: details.detail_level,
        language: details.language,
        username: details.username,
        email: details.email,
      };
      set({ profile });
      await AuthService.saveProfile(profile);
    } catch {
      // 401s are already handled by ApiClient → handleUnauthorized. Anything else
      // (offline, timeout, odd response) keeps the cached profile. Fire-and-forget
      // callers rely on this never rejecting.
    }
  },

  handleUnauthorized: async (message) => {
    if (!get().isAuthenticated) return;
    await AuthService.logout();
    set({ ...SIGNED_OUT, notice: message || SESSION_EXPIRED_MESSAGE });
  },

  clearNotice: () => set({ notice: null }),
}));

configureApiAuth({
  getToken: () => useAuthStore.getState().token,
  onUnauthorized: (error) => useAuthStore.getState().handleUnauthorized(error.message),
});
