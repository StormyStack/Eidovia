/**
 * App configuration from environment variables.
 *
 * EXPO_PUBLIC_* values are inlined into the JS bundle when Metro bundles the app, so:
 *  - they must be read with static dot notation (process.env.EXPO_PUBLIC_API_URL);
 *  - they are visible to anyone who has the app: never put secrets here;
 *  - after editing .env, restart Metro with `npx expo start --clear`.
 */

export const API_TIMEOUT_MS = 5000; // PDF: 5 s request timeout

/** Validate and normalise the raw env value (exported for tests). */
export function normaliseApiUrl(raw: string | undefined): { url: string; error: string | null } {
  const value = (raw ?? '').trim();
  if (!value) {
    return {
      url: '',
      error: 'EXPO_PUBLIC_API_URL is not set. Copy apps/mobile/.env.example to .env and set it.',
    };
  }
  if (!/^https?:\/\/[^\s/]+/.test(value)) {
    return {
      url: '',
      error: `EXPO_PUBLIC_API_URL must start with http:// or https:// (got "${value}").`,
    };
  }
  return { url: value.replace(/\/+$/, ''), error: null };
}

const parsed = normaliseApiUrl(process.env.EXPO_PUBLIC_API_URL);

/** Gateway base URL without a trailing slash, e.g. http://192.168.0.105:8000 ('' if misconfigured). */
export const API_URL: string = parsed.url;

/** Human-readable configuration problem, or null when the config is valid. */
export const CONFIG_ERROR: string | null = parsed.error;
