/**
 * "Times used the app" for the admin panel: one app_open event when a logged-in user opens the app
 * (or logs in), and one when they come back to it after at least a minute in the background.
 * The gateway adds the IP and device (X-Client header, set here); the admin panel's user history counts these.
 */

import { useEffect, useRef } from 'react';
import { AppState, Platform } from 'react-native';

import { AiService } from './AiService';
import { setClientDescription } from './ApiClient';

/** "Eidovia/1.0 android 34 (Xiaomi 23124RA7EO)" — sent with every request as X-Client. */
export function clientDescription(): string {
  const c = (Platform.constants ?? {}) as { Manufacturer?: string; Brand?: string; Model?: string };
  const model = [c.Manufacturer ?? c.Brand, c.Model].filter(Boolean).join(' ');
  return `Eidovia/1.0 ${Platform.OS} ${String(Platform.Version)}${model ? ` (${model})` : ''}`;
}
setClientDescription(clientDescription());

const RESUME_AFTER_MS = 60_000;

export function logAppOpen(reason: 'start' | 'resume'): void {
  void AiService.logEvent({
    session_id: 'app',
    event_type: 'app_open',
    payload: { reason },
    client_timestamp: new Date().toISOString(),
  });
}

export function useAppUsageLog(isAuthenticated: boolean): void {
  const backgroundSince = useRef<number | null>(null);

  useEffect(() => {
    if (isAuthenticated) logAppOpen('start');
  }, [isAuthenticated]);

  useEffect(() => {
    const sub = AppState.addEventListener('change', (state) => {
      if (state === 'background') {
        backgroundSince.current = Date.now();
      } else if (state === 'active' && backgroundSince.current !== null) {
        const away = Date.now() - backgroundSince.current;
        backgroundSince.current = null;
        if (isAuthenticated && away >= RESUME_AFTER_MS) logAppOpen('resume');
      }
    });
    return () => sub.remove();
  }, [isAuthenticated]);
}
