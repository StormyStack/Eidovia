/**
 * ApiClient — Axios REST client for all non-realtime Gateway calls (PDF §1).
 *
 * - Base URL from EXPO_PUBLIC_API_URL (src/config.ts); 5 s timeout (PDF API testing SLA).
 * - Request interceptor adds `Authorization: Bearer <token>` for protected routes.
 * - Response interceptor turns every failure into one ApiError shape for the UI and,
 *   on 401 from a protected route, calls the registered unauthorized handler
 *   (authStore clears the session → navigation returns to Login).
 *
 * No auth imports here: authStore registers its hooks via configureApiAuth(),
 * which keeps ApiClient ↔ AuthService free of circular dependencies.
 */

import axios, { AxiosError, AxiosHeaders, type InternalAxiosRequestConfig } from 'axios';

import { API_TIMEOUT_MS, API_URL, CONFIG_ERROR } from '../config';
import type { ModuleConfig, ModuleSummary, UserProfileDetails } from './types';

// ============================================================
// ERRORS
// ============================================================

/** Server codes from docs/api-auth-home.md plus client-side codes. */
export type ApiErrorCode =
  | 'VALIDATION_ERROR'
  | 'INVALID_CREDENTIALS'
  | 'TOKEN_MISSING'
  | 'TOKEN_INVALID'
  | 'TOKEN_EXPIRED'
  | 'FORBIDDEN'
  | 'MODULE_NOT_FOUND'
  | 'NOT_FOUND'
  | 'USERNAME_TAKEN'
  | 'EMAIL_TAKEN'
  | 'INTERNAL_ERROR'
  // client-side
  | 'NETWORK_ERROR'
  | 'TIMEOUT'
  | 'CANCELLED'
  | 'CONFIG_ERROR'
  | 'STORAGE_ERROR'
  | 'UNKNOWN_ERROR';

export const ERROR_MESSAGES = {
  NETWORK_ERROR: "Can't reach the server. Check your internet connection and try again.",
  TIMEOUT: 'The server took too long to respond. Please try again.',
  CANCELLED: 'The request was cancelled.',
  INTERNAL_ERROR: 'The server had a problem. Please try again in a moment.',
  UNKNOWN_ERROR: 'Something went wrong. Please try again.',
  UNEXPECTED_RESPONSE: 'The server sent an unexpected response. Please try again.',
} as const;

/** The single error type every service call rejects with. */
export class ApiError extends Error {
  readonly code: ApiErrorCode | string;
  readonly status: number | null;
  readonly fields: Record<string, string>;

  constructor(code: ApiErrorCode | string, message: string, status: number | null = null, fields: Record<string, string> = {}) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.status = status;
    this.fields = fields;
    Object.setPrototypeOf(this, ApiError.prototype);
  }

  /** True for problems where retrying later may help (offline, slow, server down). */
  get isRetryable(): boolean {
    return this.code === 'NETWORK_ERROR' || this.code === 'TIMEOUT' || this.code === 'INTERNAL_ERROR';
  }
}

function sanitizeFields(fields: unknown): Record<string, string> {
  if (!fields || typeof fields !== 'object') return {};
  const result: Record<string, string> = {};
  for (const [key, value] of Object.entries(fields as Record<string, unknown>)) {
    if (typeof value === 'string') result[key] = value;
  }
  return result;
}

/** Normalise anything thrown by axios (or our own code) into an ApiError. */
export function toApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error;
  if (axios.isCancel(error)) return new ApiError('CANCELLED', ERROR_MESSAGES.CANCELLED);

  if (axios.isAxiosError(error)) {
    const response = error.response;
    if (response) {
      const detail = (response.data as { detail?: unknown } | undefined)?.detail as
        | { code?: unknown; message?: unknown; fields?: unknown }
        | undefined;
      if (detail && typeof detail === 'object' && typeof detail.code === 'string') {
        const message = typeof detail.message === 'string' ? detail.message : ERROR_MESSAGES.UNKNOWN_ERROR;
        return new ApiError(detail.code, message, response.status, sanitizeFields(detail.fields));
      }
      if (response.status >= 500) {
        return new ApiError('INTERNAL_ERROR', ERROR_MESSAGES.INTERNAL_ERROR, response.status);
      }
      return new ApiError('UNKNOWN_ERROR', ERROR_MESSAGES.UNKNOWN_ERROR, response.status);
    }
    // clarifyTimeoutError makes timeouts ETIMEDOUT; everything else without a response is a network failure
    if (error.code === AxiosError.ETIMEDOUT) return new ApiError('TIMEOUT', ERROR_MESSAGES.TIMEOUT);
    return new ApiError('NETWORK_ERROR', ERROR_MESSAGES.NETWORK_ERROR);
  }

  return new ApiError('UNKNOWN_ERROR', ERROR_MESSAGES.UNKNOWN_ERROR);
}

// ============================================================
// AUTH HOOKS (registered by authStore)
// ============================================================

type TokenGetter = () => string | null;
type UnauthorizedHandler = (error: ApiError) => void | Promise<void>;

let getAuthToken: TokenGetter = () => null;
let handleUnauthorized: UnauthorizedHandler | null = null;

/** Called once by authStore: where to read the current token, and what to do on 401. */
export function configureApiAuth(options: { getToken: TokenGetter; onUnauthorized: UnauthorizedHandler }): void {
  getAuthToken = options.getToken;
  handleUnauthorized = options.onUnauthorized;
}

/** Login/register must never carry an old token, and their 401s are form errors, not logouts. */
const PUBLIC_AUTH_ROUTES = ['/api/auth/login', '/api/auth/register'];

function isPublicAuthRoute(url: string | undefined): boolean {
  if (!url) return false;
  const path = url.replace(/^https?:\/\/[^/]+/, '').split('?')[0];
  return PUBLIC_AUTH_ROUTES.includes(path);
}

function bearerOf(config: InternalAxiosRequestConfig | undefined): string | null {
  const value = config?.headers ? AxiosHeaders.from(config.headers).get('Authorization') : null;
  return typeof value === 'string' ? value : null;
}

// ============================================================
// AXIOS INSTANCE
// ============================================================

export const ApiClient = axios.create({
  baseURL: API_URL || undefined,
  timeout: API_TIMEOUT_MS,
  headers: { Accept: 'application/json' },
  transitional: { clarifyTimeoutError: true },
});

ApiClient.interceptors.request.use((config) => {
  if (CONFIG_ERROR) {
    throw new ApiError('CONFIG_ERROR', CONFIG_ERROR);
  }
  const token = getAuthToken();
  if (token && !isPublicAuthRoute(config.url)) {
    config.headers.set('Authorization', `Bearer ${token}`);
  }
  return config;
});

ApiClient.interceptors.response.use(
  (response) => response,
  async (error: unknown) => {
    const apiError = toApiError(error);

    if (apiError.status === 401 && handleUnauthorized) {
      const config = axios.isAxiosError(error) ? error.config : undefined;
      const sentBearer = bearerOf(config);
      const currentToken = getAuthToken();
      // Only end the session whose token was actually rejected: a late 401 for an
      // older token must not log out a user who has signed in again since.
      if (!isPublicAuthRoute(config?.url) && currentToken && sentBearer === `Bearer ${currentToken}`) {
        try {
          await handleUnauthorized(apiError);
        } catch {
          // Logout problems must never surface as an unhandled rejection
        }
      }
    }

    return Promise.reject(apiError);
  },
);

// ============================================================
// TYPED ENDPOINTS (docs/api-auth-home.md)
// ============================================================

function ensureShape<T>(condition: boolean, data: unknown): T {
  if (!condition) throw new ApiError('UNKNOWN_ERROR', ERROR_MESSAGES.UNEXPECTED_RESPONSE);
  return data as T;
}

const isObject = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

export const Api = {
  /** GET /api/users/{id}/profile */
  async getUserProfile(userId: string, signal?: AbortSignal): Promise<UserProfileDetails> {
    const { data } = await ApiClient.get(`/api/users/${encodeURIComponent(userId)}/profile`, { signal });
    return ensureShape<UserProfileDetails>(isObject(data) && typeof data.username === 'string', data);
  },

  /** GET /api/modules */
  async getModules(signal?: AbortSignal): Promise<ModuleSummary[]> {
    const { data } = await ApiClient.get('/api/modules', { signal });
    return ensureShape<ModuleSummary[]>(
      Array.isArray(data) && data.every((m) => isObject(m) && typeof m.module_id === 'string'),
      data,
    );
  },

  /** GET /api/modules/{id}/config (PDF contract) */
  async getModuleConfig(moduleId: string, signal?: AbortSignal): Promise<ModuleConfig> {
    const { data } = await ApiClient.get(`/api/modules/${encodeURIComponent(moduleId)}/config`, { signal });
    return ensureShape<ModuleConfig>(isObject(data) && typeof data.scene_name === 'string', data);
  },
};
