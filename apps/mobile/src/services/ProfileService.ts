/**
 * ProfileService — the Profile page (gateway routers/users.py):
 *   GET   /api/users/me            name, email, level, age, gender
 *   PATCH /api/users/me            change email / level / age / gender
 *   POST  /api/users/me/password   change password (needs the current one)
 *   POST  /api/auth/password-reset-request   forgot password: a support ticket, an admin resets it (no login needed)
 */

import { ApiClient, toApiError } from './ApiClient';

export type Gender = 'male' | 'female' | 'other' | 'prefer_not_to_say';

export const LEVELS: Record<number, string> = { 1: 'Beginner', 2: 'Intermediate', 3: 'Advanced' };
export const GENDERS: { value: Gender; label: string }[] = [
  { value: 'male', label: 'Male' },
  { value: 'female', label: 'Female' },
  { value: 'other', label: 'Other' },
  { value: 'prefer_not_to_say', label: 'Prefer not to say' },
];

export interface MyProfile {
  user_id: string;
  username: string;
  email: string | null;
  /** 1 Beginner · 2 Intermediate · 3 Advanced (also how detailed the AI tutor's answers are) */
  level: number;
  level_name: string;
  language: string;
  age: number | null;
  gender: Gender | null;
  created_at: string | null;
}

export type ProfileChanges = Partial<{ email: string; level: number; age: number | null; gender: Gender | null }>;

async function call<T>(promise: Promise<{ data: T }>): Promise<T> {
  try {
    return (await promise).data;
  } catch (error) {
    throw toApiError(error);
  }
}

export const ProfileService = {
  get(signal?: AbortSignal): Promise<MyProfile> {
    return call(ApiClient.get<MyProfile>('/api/users/me', { signal }));
  },
  update(changes: ProfileChanges): Promise<MyProfile> {
    return call(ApiClient.patch<MyProfile>('/api/users/me', changes));
  },
  changePassword(current_password: string, new_password: string): Promise<{ status: string }> {
    return call(ApiClient.post<{ status: string }>('/api/users/me/password', { current_password, new_password }));
  },
  /** Same answer whether or not the account exists. */
  requestPasswordReset(username_or_email: string, message?: string): Promise<{ status: string; message: string }> {
    return call(
      ApiClient.post<{ status: string; message: string }>('/api/auth/password-reset-request', {
        username_or_email,
        message: message || null,
      }),
    );
  },
};
