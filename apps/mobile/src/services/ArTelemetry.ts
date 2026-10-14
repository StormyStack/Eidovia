/**
 * ArTelemetry — turns the Unity game's messages into learner events for the admin panel.
 *
 * One AR session = one visit to the AR screen. Events go to POST /api/events (fire-and-forget, like the
 * chat events); the gateway stores ar_* events in audit_logs and the admin "AR Game" tab reads them.
 *
 *   ar_session_start                                  screen opened
 *   ar_part_discovered   level, part                  a new part was tapped
 *   ar_stage_completed   level, skipped, duration_s   a level was passed (skipped = used a wildcard)
 *   ar_journey_completed duration_s                   all levels done
 *   ar_session_end       duration_s, level, found…    screen closed (ar = false: 3D mode, phone without AR)
 *   ar_previous_used     from_level, to_level          the free Back button
 *
 * Wildcard uses and earned cards are not sent here: they change the server wallet (services/ArService),
 * and the gateway logs them with the wallet breakdown.
 */

import type { UnityMessage } from '../../modules/eidovia-unity';
import { AiService } from './AiService';

/** Level names as shown in the game (Unity LevelManager.StageNames). */
export const AR_LEVEL_NAMES = ['The building blocks', 'A nucleotide', 'A single strand', 'Two strands', 'The double helix'];

type Progress = Extract<UnityMessage, { type: 'progress' }>;

export interface ArSession {
  readonly sessionId: string;
  onMessage(message: UnityMessage): void;
  end(): void;
}

export function startArSession(moduleId: string, now: () => number = Date.now): ArSession {
  const startedAt = now();
  const sessionId = `ar-${startedAt.toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
  let stageStartedAt = startedAt;
  let last: Progress | null = null;
  let ended = false;
  let arMode: boolean | null = null;

  const seconds = (from: number) => Math.round((now() - from) / 1000);
  const send = (eventType: string, payload: Record<string, unknown>) => {
    void AiService.logEvent({
      session_id: sessionId,
      event_type: eventType,
      payload: { module_id: moduleId, ...payload },
      client_timestamp: new Date(now()).toISOString(),
    });
  };
  const level = (stage: number) => ({ level: stage + 1, level_name: AR_LEVEL_NAMES[stage] ?? `Level ${stage + 1}` });

  send('ar_session_start', {});

  return {
    sessionId,
    onMessage(message) {
      if (ended) return;
      switch (message.type) {
        case 'progress':
          if (last && last.stage !== message.stage) stageStartedAt = now(); // a new level started
          last = message;
          break;
        case 'part_discovered':
          send('ar_part_discovered', { ...level(message.stage), part: message.part });
          break;
        case 'stage_completed':
          send('ar_stage_completed', {
            ...level(message.stage),
            skipped: message.skipped,
            duration_s: seconds(stageStartedAt),
            parts_found: last?.found ?? null,
            parts_required: last?.required ?? null,
          });
          break;
        case 'mode':
          arMode = message.ar;
          break;
        case 'previous_used': {
          const from = level(message.from), to = level(message.to);
          send('ar_previous_used', {
            from_level: from.level, from_name: from.level_name, to_level: to.level, to_name: to.level_name,
          });
          break;
        }
        case 'journey_completed':
          send('ar_journey_completed', { duration_s: seconds(startedAt) });
          break;
        default:
          break;
      }
    },
    end() {
      if (ended) return;
      ended = true;
      send('ar_session_end', {
        duration_s: seconds(startedAt),
        ...(last ? level(last.stage) : { level: null, level_name: null }),
        parts_found: last?.found ?? null,
        parts_required: last?.required ?? null,
        wildcards_left: last?.wildcards ?? null,
        ar: arMode,
      });
    },
  };
}
