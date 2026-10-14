/**
 * WildcardService — the learner's wildcards for the whole app (gateway routers/wildcards.py).
 *
 * One wallet per learner on the server. The learner only sees the total; how it is made up
 * (daily gift + default cards) is for the admin panel. Features spend and earn through it:
 * the AR game is feature "ar" (skip = 1 card, jump = 2 cards, a passed level earns 1).
 *
 *   GET  /api/wildcards            → { total, requests, can_request, next_request_at }
 *   POST /api/wildcards/sync       → { total, added }   added = new cards to announce (daily / admin gift)
 *   POST /api/wildcards/spend      → { ok, total }      the server decides the price
 *   POST /api/wildcards/earn       → { earned, total }
 *   POST /api/wildcards/request    ask an admin for wildcards with a reason (once every 3 days)
 */

import { ApiClient, toApiError } from './ApiClient';

export interface WildcardRequestItem {
  ticket_id: string;
  amount: number;
  reason: string;
  /** open | in_progress | resolved */
  status: string;
  /** cards the admin gave (null or 0 = none) */
  granted: number | null;
  admin_reply: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface WildcardSummary {
  total: number;
  requests: WildcardRequestItem[];
  can_request: boolean;
  next_request_at: string | null;
}

async function call<T>(promise: Promise<{ data: T }>): Promise<T> {
  try {
    return (await promise).data;
  } catch (error) {
    throw toApiError(error);
  }
}

export const WildcardService = {
  summary(signal?: AbortSignal): Promise<WildcardSummary> {
    return call(ApiClient.get<WildcardSummary>('/api/wildcards', { signal }));
  },

  sync(): Promise<{ total: number; added: number }> {
    return call(ApiClient.post<{ total: number; added: number }>('/api/wildcards/sync'));
  },

  /** e.g. spend('ar', 'jump', { from_level: 5, to_level: 3, session_id }) — returns the new total. */
  async spend(feature: string, action: string, extra: Record<string, unknown> = {}): Promise<number> {
    const data = await call(ApiClient.post<{ ok: boolean; total: number }>('/api/wildcards/spend', { feature, action, ...extra }));
    return data.total;
  },

  /** e.g. earn('ar', 'level_passed', { level: 2, session_id }) — returns the new total. */
  async earn(feature: string, reason: string, extra: Record<string, unknown> = {}): Promise<number> {
    const data = await call(ApiClient.post<{ earned: boolean; total: number }>('/api/wildcards/earn', { feature, reason, ...extra }));
    return data.total;
  },

  /** Rejects with ApiError: REQUEST_TOO_SOON (429), REQUEST_PENDING (409), VALIDATION_ERROR. */
  request(amount: number, reason: string): Promise<WildcardRequestItem> {
    return call(ApiClient.post<WildcardRequestItem>('/api/wildcards/request', { amount, reason }));
  },
};
