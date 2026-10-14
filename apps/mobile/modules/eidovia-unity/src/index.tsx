/**
 * eidovia-unity — the DNA AR Unity game inside the Expo app ("Unity as a Library", Android).
 *
 *   <UnityView style={{ flex: 1 }} onMessage={(m) => ...} />
 *   UnityBridge.send({ type: 'init', moduleId, sceneName })
 *
 * Message protocol (JSON both ways) is documented in ../README.md and in Unity's MobileBridge.cs.
 * Outside a development build (Expo Go, Jest, iOS for now) `isUnityAvailable` is false and
 * <UnityView/> renders an empty View, so screens can show a fallback instead of crashing.
 */

import { requireNativeViewManager, requireOptionalNativeModule } from 'expo-modules-core';
import type { ComponentType } from 'react';
import { Platform, View, type NativeSyntheticEvent, type ViewProps } from 'react-native';

/** Unity -> app */
export type UnityMessage =
  | { type: 'ready' }
  | { type: 'progress'; stage: number; stageCount: number; found: number; required: number; wildcards: number }
  | { type: 'part_discovered'; part: string; stage: number }
  | { type: 'stage_completed'; stage: number; skipped: boolean }
  | { type: 'journey_completed' }
  | { type: 'mode'; ar: boolean }
  /** a wildcard was used: skip = next level (1 card), jump = any level (2 cards); stages are 0-based */
  | { type: 'wildcard_used'; mode: 'skip' | 'jump'; from: number; to: number; cost: number; left: number }
  /** the free Back button (once per 30 s) */
  | { type: 'previous_used'; from: number; to: number }
  /** a level finished on one's own earned a card */
  | { type: 'wildcard_earned'; stage: number };

/** app -> Unity */
export type HostMessage =
  | { type: 'init'; moduleId?: string; sceneName?: string }
  | { type: 'restart' }
  /** wildcards from the server wallet; added > 0 plays the gift animation */
  | { type: 'wallet'; total: number; added: number };

/** GameObject in the Unity scene that receives messages (MobileBridge lives on it). */
export const UNITY_GAME_OBJECT = 'XR Origin';
const UNITY_METHOD = 'OnHostMessage';

interface EidoviaUnityNative {
  postMessage(gameObject: string, methodName: string, message: string): void;
  isRunning(): boolean;
}

type NativeEvent = NativeSyntheticEvent<{ message: string }>;
type NativeViewProps = ViewProps & { onUnityMessage?: (event: NativeEvent) => void };

const native: EidoviaUnityNative | null =
  Platform.OS === 'android' ? requireOptionalNativeModule<EidoviaUnityNative>('EidoviaUnity') : null;

/** True only in an Android development/production build that contains the Unity library. */
export const isUnityAvailable = native != null;

const NativeUnityView: ComponentType<NativeViewProps> | null = native
  ? requireNativeViewManager<NativeViewProps>('EidoviaUnity')
  : null;

export const UnityBridge = {
  /** Send a message to the game; queued natively until Unity reports "ready". */
  send(message: HostMessage): void {
    native?.postMessage(UNITY_GAME_OBJECT, UNITY_METHOD, JSON.stringify(message));
  },

  /** Parse a raw JSON message from Unity (null if it is not valid). */
  parse(raw: string): UnityMessage | null {
    try {
      const value = JSON.parse(raw) as { type?: unknown };
      return value && typeof value.type === 'string' ? (value as UnityMessage) : null;
    } catch {
      return null;
    }
  },

  isRunning(): boolean {
    return native?.isRunning() ?? false;
  },
};

export type UnityViewProps = ViewProps & {
  /** Every message the game sends (already parsed). */
  onMessage?: (message: UnityMessage) => void;
};

/** Full Unity game view. Only one can be on screen at a time (Unity runs once per app). */
export function UnityView({ onMessage, ...rest }: UnityViewProps) {
  if (!NativeUnityView) return <View {...rest} />;
  return (
    <NativeUnityView
      {...rest}
      onUnityMessage={(event) => {
        const message = UnityBridge.parse(event.nativeEvent.message);
        if (message) onMessage?.(message);
      }}
    />
  );
}
