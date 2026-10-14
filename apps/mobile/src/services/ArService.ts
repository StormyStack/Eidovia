/**
 * ArService — the AR game's progress for the DNA page dashboard (gateway routers/ar.py):
 *   GET /api/ar/progress
 * The game's wildcards use the app-wide wallet: services/WildcardService.ts.
 */

import { ApiClient, toApiError } from './ApiClient';

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
  async getProgress(signal?: AbortSignal): Promise<ArProgress> {
    try {
      const { data } = await ApiClient.get<ArProgress>('/api/ar/progress', { signal });
      return data;
    } catch (error) {
      throw toApiError(error);
    }
  },
};
