/**
 * QuizService — the DNA multiple-choice quiz (gateway routers/quiz.py, rules in app/quiz_service.py).
 *
 * The server decides everything: eligibility, the 12 h cooldown, the 3-wildcard Force Attempt, admin
 * approvals and the score. The phone never receives the answer key before an attempt is submitted.
 *
 *   GET  /api/quiz/status                       eligibility, cooldown, active attempt, wildcards, requests
 *   POST /api/quiz/attempts                     { mode, idempotency_key } → attempt + questions
 *   GET  /api/quiz/attempts/{id}                resume (questions) or the result
 *   POST /api/quiz/attempts/{id}/submit         { answers: { "1": "B", ... } } → result + review
 *   POST /api/quiz/attempts/{id}/abandon
 *   GET  /api/quiz/history                      attempts + summary (dashboard)
 *   POST /api/quiz/access-requests              { reason } ask an admin for an early attempt
 *   GET  /api/quiz/access-requests
 *
 * Error codes (ApiError.code): COOLDOWN (429), NOT_ENOUGH_WILDCARDS (402), ATTEMPT_IN_PROGRESS (409),
 * FORCE_NOT_NEEDED (409), AUTH_NOT_NEEDED (409), NOT_AUTHORIZED / NOT_YET (403), ATTEMPT_CLOSED (409),
 * INCOMPLETE / VALIDATION_ERROR (400), ATTEMPT_NOT_FOUND (404), REQUEST_EXISTS (409).
 */

import { ApiClient, toApiError } from './ApiClient';

export type QuizMode = 'normal' | 'forced' | 'authorized';
export type AttemptStatus = 'in_progress' | 'completed' | 'abandoned' | 'expired';
export type RequestStatus = 'pending' | 'approved' | 'rejected' | 'used' | 'expired';
export type OptionKey = 'A' | 'B' | 'C' | 'D';

export interface QuizOption {
  key: OptionKey;
  text: string;
}

export interface QuizQuestion {
  id: string;
  level: 'easy' | 'medium' | 'hard';
  text: string;
  options: QuizOption[];
}

export interface QuizAccessRequest {
  request_id: string;
  status: RequestStatus;
  reason: string | null;
  created_at: string | null;
  decided_at: string | null;
  decided_by: string | null;
  decision_reason: string | null;
  window_start: string | null;
  window_end: string | null;
  cooldown_hours: number | null;
  used_at: string | null;
  used_attempt_id: string | null;
}

export interface QuizStatus {
  server_time: string;
  quiz: { quiz_id: string; version: number; title: string; question_count: number; time_limit_s: number; cooldown_hours: number };
  eligible: boolean;
  next_eligible_at: string | null;
  cooldown_remaining_s: number;
  active_attempt: { attempt_id: string; attempt_type: QuizMode; started_at: string; expires_at: string } | null;
  force_cost: number;
  wildcards: number;
  can_force: boolean;
  authorization: (QuizAccessRequest & { usable_now: boolean }) | null;
  pending_request: QuizAccessRequest | null;
  can_request: boolean;
  requests: QuizAccessRequest[];
}

export interface QuizStarted {
  attempt_id: string;
  attempt_type: QuizMode;
  status: AttemptStatus;
  quiz_version: number;
  started_at: string;
  expires_at: string;
  wildcards_spent: number;
  wildcards: number;
  replayed: boolean;
  questions: QuizQuestion[];
}

export interface QuizReviewItem extends QuizQuestion {
  your_answer: OptionKey | null;
  correct_answer: OptionKey;
  correct: boolean;
  explanation: string;
}

export interface QuizAttempt {
  attempt_id: string;
  status: AttemptStatus;
  attempt_type: QuizMode;
  quiz_version: number;
  started_at: string | null;
  ended_at: string | null;
  expires_at: string | null;
  duration_s: number | null;
  wildcards_spent: number;
  score: number | null;
  total: number | null;
  correct: number | null;
  incorrect: number | null;
  percent: number | null;
  /** only for completed attempts */
  review?: QuizReviewItem[];
  /** only while in progress (resume) */
  questions?: QuizQuestion[];
  /** submit only: true when this attempt had already been submitted (stored result returned) */
  duplicate?: boolean;
}

export interface QuizSummary {
  total_attempts: number;
  completed_attempts: number;
  incomplete_attempts: number;
  completion_rate: number | null;
  latest: { score: number; total: number; percent: number; ended_at: string | null } | null;
  best: { score: number; total: number; percent: number } | null;
  average_percent: number | null;
  average_score: number | null;
  trend: 'improving' | 'declining' | 'steady' | null;
  forced_attempts: number;
  wildcards_spent: number;
  last_completed_at: string | null;
  ever_completed: boolean;
}

export interface QuizHistory {
  summary: QuizSummary;
  attempts: QuizAttempt[];
}

async function call<T>(promise: Promise<{ data: T }>): Promise<T> {
  try {
    return (await promise).data;
  } catch (error) {
    throw toApiError(error);
  }
}

/** One key per start tap: a retry of the same tap reuses it, so the server never starts (or charges) twice. */
export function newIdempotencyKey(): string {
  return `q-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

export const QuizService = {
  status(signal?: AbortSignal): Promise<QuizStatus> {
    return call(ApiClient.get<QuizStatus>('/api/quiz/status', { signal }));
  },

  start(mode: QuizMode, idempotencyKey: string): Promise<QuizStarted> {
    return call(ApiClient.post<QuizStarted>('/api/quiz/attempts', { mode, idempotency_key: idempotencyKey }));
  },

  getAttempt(attemptId: string): Promise<QuizAttempt> {
    return call(ApiClient.get<QuizAttempt>(`/api/quiz/attempts/${encodeURIComponent(attemptId)}`));
  },

  submit(attemptId: string, answers: Record<string, OptionKey>): Promise<QuizAttempt> {
    return call(ApiClient.post<QuizAttempt>(`/api/quiz/attempts/${encodeURIComponent(attemptId)}/submit`, { answers }));
  },

  abandon(attemptId: string): Promise<QuizAttempt> {
    return call(ApiClient.post<QuizAttempt>(`/api/quiz/attempts/${encodeURIComponent(attemptId)}/abandon`));
  },

  history(signal?: AbortSignal): Promise<QuizHistory> {
    return call(ApiClient.get<QuizHistory>('/api/quiz/history', { signal }));
  },

  requestAccess(reason: string): Promise<QuizAccessRequest> {
    return call(ApiClient.post<QuizAccessRequest>('/api/quiz/access-requests', { reason: reason.trim() || null }));
  },

  listRequests(): Promise<QuizAccessRequest[]> {
    return call(ApiClient.get<QuizAccessRequest[]>('/api/quiz/access-requests'));
  },
};

// ============================================================
// FORMATTING (shared by the quiz screen and the DNA dashboard)
// ============================================================

export function formatWhen(iso: string | null | undefined): string {
  if (!iso) return '--';
  return new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
}

export function formatCountdown(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  if (h) return `${h}h ${m}m`;
  if (m) return `${m}m ${String(sec).padStart(2, '0')}s`;
  return `${sec}s`;
}

export const REQUEST_LABELS: Record<RequestStatus, string> = {
  pending: 'Waiting for an admin',
  approved: 'Approved',
  rejected: 'Rejected',
  used: 'Used',
  expired: 'Expired',
};
