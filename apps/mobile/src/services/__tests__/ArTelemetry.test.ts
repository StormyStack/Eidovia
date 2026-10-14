import { AiService } from '../AiService';
import { startArSession } from '../ArTelemetry';

jest.mock('../AiService', () => ({ AiService: { logEvent: jest.fn().mockResolvedValue(undefined) } }));
const logEvent = AiService.logEvent as jest.Mock;

beforeEach(() => logEvent.mockClear());

const sent = () => logEvent.mock.calls.map(([e]) => [e.event_type, e.payload]);

it('reports a full AR session: parts, passed and skipped levels, journey and session end', () => {
  let t = 1_000_000;
  const session = startArSession('dna_ar', () => t);

  session.onMessage({ type: 'progress', stage: 0, stageCount: 5, found: 0, required: 3, wildcards: 3 });
  t += 5_000;
  session.onMessage({ type: 'part_discovered', part: 'Phosphate', stage: 0 });
  t += 25_000;
  session.onMessage({ type: 'stage_completed', stage: 0, skipped: false });
  session.onMessage({ type: 'progress', stage: 1, stageCount: 5, found: 0, required: 4, wildcards: 3 });
  t += 10_000;
  session.onMessage({ type: 'stage_completed', stage: 1, skipped: true });
  session.onMessage({ type: 'mode', ar: false });
  session.onMessage({ type: 'journey_completed' });
  session.end();
  session.end(); // only once

  expect(sent()).toEqual([
    ['ar_session_start', { module_id: 'dna_ar' }],
    ['ar_part_discovered', { module_id: 'dna_ar', level: 1, level_name: 'The building blocks', part: 'Phosphate' }],
    ['ar_stage_completed', expect.objectContaining({ level: 1, skipped: false, duration_s: 30 })],
    ['ar_stage_completed', expect.objectContaining({ level: 2, level_name: 'A nucleotide', skipped: true, duration_s: 10 })],
    ['ar_journey_completed', { module_id: 'dna_ar', duration_s: 40 }],
    ['ar_session_end', expect.objectContaining({ duration_s: 40, level: 2, parts_required: 4, wildcards_left: 3, ar: false })],
  ]);
  expect(new Set(logEvent.mock.calls.map(([e]) => e.session_id)).size).toBe(1);
});

it('logs the Back button; wildcard uses go to the wallet instead', () => {
  const session = startArSession('dna_ar', () => 0);
  session.onMessage({ type: 'previous_used', from: 2, to: 1 });
  session.onMessage({ type: 'wildcard_used', mode: 'jump', from: 1, to: 4, cost: 2, left: 1 });
  session.onMessage({ type: 'wildcard_earned', stage: 0 });

  expect(sent()).toEqual([
    ['ar_session_start', { module_id: 'dna_ar' }],
    ['ar_previous_used', { module_id: 'dna_ar', from_level: 3, from_name: 'A single strand', to_level: 2, to_name: 'A nucleotide' }],
  ]);
});
