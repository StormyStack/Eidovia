/**
 * Types for the Gateway REST contract (docs/api-auth-home.md).
 * Field names match the API exactly (snake_case), as in the PDF.
 */

/** profile block returned by login/register (PDF contract). */
export interface AuthProfileSummary {
  detail_level: number;
  language: string;
}

/**
 * POST /api/auth/login and /api/auth/register response.
 * Named `UserProfile` in the PDF's AuthService; kept for compatibility.
 */
export interface UserProfile {
  user_id: string;
  token: string;
  profile: AuthProfileSummary;
}

export type AuthResponse = UserProfile;

export interface RegisterInput {
  username: string;
  email: string;
  password: string;
  language?: string;
}

/** GET /api/users/{id}/profile */
export interface UserProfileDetails {
  user_id: string;
  username: string;
  email: string | null;
  detail_level: number;
  language: string;
  created_at: string;
}

/** One item of GET /api/modules */
export interface ModuleSummary {
  module_id: string;
  title: string;
  description: string;
  difficulty: number;
  thumbnail_url: string | null;
}

/** GET /api/modules/{id}/config (PDF contract). Passed to ARGameScreen, and to Unity in Sprint 2. */
export interface ModuleConfig {
  module_id: string;
  scene_name: string;
  cdn_bundle_url: string;
  difficulty: number;
  config: Record<string, unknown>;
}

/** What the app keeps about the signed-in user (token excluded). */
export interface StoredProfile extends AuthProfileSummary {
  username?: string;
  email?: string | null;
}
