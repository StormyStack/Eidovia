/**
 * ArService — the AR game's server side (gateway routers/ar.py).
 *
 * Wildcards live on the server, one wallet per learner (not per phone). The learner only sees the total;
 * how it is made up (daily gift + default cards) is for the admin panel.
 *   POST /api/ar/wallet/sync    → { total, added }   added = new cards the game should announce
 *   POST /api/ar/wallet/spend   → { ok, total }      skip = 1 card, jump = 2 cards
 *   POST /api/ar/wallet/earn    → { earned, total }  a level finished on one's own
 *   GET  /api/ar/progress       → the learner's dashboard on the DNA page
 */

import { ApiClient, toApiError } from './ApiClient';

export interface WalletState {
  total: number;
  added: number;
}

export type LevelStatus = 'passed' | 'skipped' | 'not_yet';

export interface ArProgress {
  levels: { level: number; name: string; status: LevelStatus; current: boolean }[];
  level_count: number;
  levels_passed: number;
  levels_skipped: number;
  current_level: number | null;
  current_level_name: string | null;
  finished: boolean;
  times_finished: number;
  sessions: number;
  play_seconds: number;
  parts_discovered: number;
  wildcards: number;
  wildcards_used: number;
  power_jumps: number;
  back_used: number;
  chat_questions: number;
  last_played: string | null;
}

export const ArService = {
  async syncWallet(): Promise<WalletState> {
    const { data } = await ApiClient.post<WalletState>('/api/ar/wallet/sync');
    return data;
  },

  /** Levels are 1-based here (the game sends 0-based stages). */
  async spendWildcard(mode: 'skip' | 'jump', fromLevel: number, toLevel: number, sessionId: string): Promise<number> {
    const { data } = await ApiClient.post<{ ok: boolean; total: number }>('/api/ar/wallet/spend', {
      mode,
      from_level: fromLevel,
      to_level: toLevel,
      session_id: sessionId,
    });
    return data.total;
  },

  async earnWildcard(level: number, sessionId: string): Promise<number> {
    const { data } = await ApiClient.post<{ earned: boolean; total: number }>('/api/ar/wallet/earn', {
      level,
      session_id: sessionId,
    });
    return data.total;
  },

  async getProgress(signal?: AbortSignal): Promise<ArProgress> {
    try {
      const { data } = await ApiClient.get<ArProgress>('/api/ar/progress', { signal });
      return data;
    } catch (error) {
      throw toApiError(error);
    }
  },
};
