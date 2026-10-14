import { Ionicons } from '@expo/vector-icons';
import { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, PermissionsAndroid, Pressable, StyleSheet, Text, View } from 'react-native';

import { isUnityAvailable, UnityBridge, UnityView, type UnityMessage } from '../../modules/eidovia-unity';
import { Banner } from '../components/Banner';
import { ScreenContainer } from '../components/ScreenContainer';
import type { ScreenProps } from '../navigation/types';
import { WildcardService } from '../services/WildcardService';
import { startArSession, type ArSession } from '../services/ArTelemetry';
import type { ModuleConfig } from '../services/types';
import { difficultyLabel, palette, radius, shadow, spacing, typography } from '../theme';

/**
 * Sprint 2: the DNA AR Unity game, full-screen (PDF Flowchart A, step 4).
 * Once Unity signals "ready" the screen sends it the module config; the game reports its progress
 * back through onMessage. The game itself makes no network calls; the screen reports the session to the
 * gateway (services/ArTelemetry) for the admin panel.
 * Wildcards come from the app-wide server wallet (services/WildcardService): synced when the game is ready and every 30 s
 * (so an admin's gift or the daily gift shows up), and every use / earned card is paid on the server.
 * Unity runs only in an Android build that contains it (modules/eidovia-unity); in Expo Go and tests
 * the screen explains how to get that build instead.
 */
/** The built-in DNA AR experience (the Unity game), opened by the "Explore DNA in AR" button on the DNA page. */
export const DNA_AR: { title: string; config: ModuleConfig } = {
  title: 'DNA in AR',
  config: { module_id: 'dna_ar', scene_name: 'Root_ARPersistent', cdn_bundle_url: '', difficulty: 1, config: {} },
};

export function ARGameScreen({ route }: ScreenProps<'ARGame'>) {
  const { config, title } = route.params;
  if (!isUnityAvailable) return <UnityUnavailable title={title} config={config} />;
  return <CameraGate config={config} />;
}

type Camera = 'asking' | 'granted' | 'denied';

const WALLET_SYNC_MS = 30_000;

/** AR needs the camera; ask before Unity starts (the host activity, not Unity, owns permission results). */
function CameraGate({ config }: { config: ScreenProps<'ARGame'>['route']['params']['config'] }) {
  const [camera, setCamera] = useState<Camera>('asking');

  const ask = useCallback(() => {
    setCamera('asking');
    PermissionsAndroid.request(PermissionsAndroid.PERMISSIONS.CAMERA)
      .then((result) => setCamera(result === PermissionsAndroid.RESULTS.GRANTED ? 'granted' : 'denied'))
      .catch(() => setCamera('denied'));
  }, []);

  useEffect(ask, [ask]);

  if (camera === 'granted') return <UnityGame config={config} />;
  return (
    <View style={[styles.game, styles.loading]} testID="argame-camera">
      {camera === 'asking' ? (
        <ActivityIndicator size="large" color={palette.surface} />
      ) : (
        <>
          <Text style={styles.loadingText}>The AR game needs the camera.</Text>
          <Pressable onPress={ask} style={styles.retry} accessibilityRole="button">
            <Text style={styles.retryText}>Allow camera</Text>
          </Pressable>
        </>
      )}
    </View>
  );
}

function UnityGame({ config }: { config: ScreenProps<'ARGame'>['route']['params']['config'] }) {
  const [ready, setReady] = useState(UnityBridge.isRunning());
  const [progress, setProgress] = useState<Extract<UnityMessage, { type: 'progress' }> | null>(null);
  const [noArNote, setNoArNote] = useState(false);
  const session = useRef<ArSession | null>(null);

  // one AR session per visit of this screen (admin panel: AR Game)
  useEffect(() => {
    const current = startArSession(config.module_id);
    session.current = current;
    return () => {
      current.end();
      if (session.current === current) session.current = null;
    };
  }, [config.module_id]);

  const sendInit = useCallback(() => {
    UnityBridge.send({
      type: 'init',
      moduleId: config.module_id,
      sceneName: config.scene_name,
    });
  }, [config.module_id, config.scene_name]);

  // queued natively until Unity is ready; also covers re-opening the screen while Unity keeps running
  useEffect(() => {
    sendInit();
  }, [sendInit]);

  // wildcards: the server wallet is the truth; the game only shows the total
  const sendWallet = useCallback((total: number, added = 0) => {
    UnityBridge.send({ type: 'wallet', total, added });
  }, []);
  useEffect(() => {
    if (!ready) return;
    const sync = () => {
      WildcardService.sync()
        .then((w) => sendWallet(w.total, w.added))
        .catch(() => undefined); // offline: the game keeps its last count, the next sync fixes it
    };
    sync();
    const timer = setInterval(sync, WALLET_SYNC_MS);
    return () => clearInterval(timer);
  }, [ready, sendWallet]);

  const onMessage = useCallback(
    (message: UnityMessage) => {
      session.current?.onMessage(message);
      switch (message.type) {
        case 'ready':
          setReady(true);
          sendInit();
          break;
        case 'progress':
          setProgress(message);
          break;
        case 'mode':
          setNoArNote(!message.ar);
          break;
        case 'wildcard_used':
          WildcardService.spend('ar', message.mode, {
            from_level: message.from + 1,
            to_level: message.to + 1,
            session_id: session.current?.sessionId,
          })
            .then((total) => sendWallet(total))
            .catch(() => undefined);
          break;
        case 'wildcard_earned':
          WildcardService.earn('ar', 'level_passed', { level: message.stage + 1, session_id: session.current?.sessionId })
            .then((total) => sendWallet(total))
            .catch(() => undefined);
          break;
        default:
          break;
      }
    },
    [sendInit, sendWallet]
  );

  return (
    <View style={styles.game} testID="argame-unity">
      <UnityView style={StyleSheet.absoluteFill} onMessage={onMessage} />
      {!ready && (
        <View style={styles.loading} pointerEvents="none" testID="argame-loading">
          <ActivityIndicator size="large" color={palette.surface} />
          <Text style={styles.loadingText}>Starting AR…</Text>
        </View>
      )}
      {ready && noArNote && (
        <Pressable style={styles.noAr} onPress={() => setNoArNote(false)} accessibilityRole="button" testID="argame-no-ar">
          <Text style={styles.noArText}>3D mode · this phone doesn't support AR, so the DNA is shown on screen. Tap to hide.</Text>
        </Pressable>
      )}
      {ready && progress && (
        <View style={styles.progress} pointerEvents="none" accessibilityLabel="Game progress">
          <Text style={styles.progressText}>
            Stage {progress.stage + 1}/{progress.stageCount} · {progress.found}/{progress.required}
          </Text>
        </View>
      )}
    </View>
  );
}

function UnityUnavailable({
  title,
  config,
}: {
  title: string;
  config: ScreenProps<'ARGame'>['route']['params']['config'];
}) {
  return (
    <ScreenContainer edges={['bottom']} testID="argame-screen">
      <View style={styles.hero}>
        <View style={styles.heroIcon}>
          <Ionicons name="cube-outline" size={40} color={palette.primary} />
        </View>
        <Text style={styles.title}>{title}</Text>
        <Text style={styles.caption}>Unity scene</Text>
        <Text style={styles.scene} testID="argame-scene-name" selectable>
          {config.scene_name}
        </Text>
      </View>

      <Banner
        tone="info"
        title="The AR game needs the Eidovia app build"
        message="The DNA AR game runs inside the Android build of Eidovia (npx expo run:android). Expo Go cannot load it."
        testID="argame-unity-unavailable"
      />

      <View style={styles.details}>
        <Detail label="Module ID" value={config.module_id} />
        <Detail label="Difficulty" value={`${difficultyLabel(config.difficulty)} (${config.difficulty})`} />
        <Detail label="Asset bundle" value={config.cdn_bundle_url} last />
      </View>
    </ScreenContainer>
  );
}

function Detail({ label, value, last = false }: { label: string; value: string; last?: boolean }) {
  return (
    <View style={[styles.detailRow, !last && styles.detailDivider]}>
      <Text style={styles.detailLabel}>{label}</Text>
      <Text style={styles.detailValue} selectable numberOfLines={2}>
        {value}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  game: { flex: 1, backgroundColor: '#000' },
  loading: {
    ...StyleSheet.absoluteFill,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#000',
  },
  loadingText: { ...typography.body, color: palette.surface, marginTop: spacing.md },
  retry: {
    marginTop: spacing.lg,
    backgroundColor: palette.primary,
    borderRadius: radius.lg,
    paddingHorizontal: spacing.xl,
    paddingVertical: spacing.md,
  },
  retryText: { ...typography.body, color: palette.surface, fontWeight: '600' },
  progress: {
    position: 'absolute',
    bottom: spacing.lg,
    alignSelf: 'center',
    backgroundColor: 'rgba(15, 23, 42, 0.7)',
    borderRadius: radius.lg,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.xs,
  },
  progressText: { ...typography.caption, color: palette.surface },
  noAr: {
    position: 'absolute',
    top: spacing.lg,
    left: spacing.lg,
    right: spacing.lg,
    backgroundColor: 'rgba(15, 23, 42, 0.8)',
    borderRadius: radius.lg,
    padding: spacing.md,
  },
  noArText: { ...typography.caption, color: palette.surface, textAlign: 'center' },
  hero: {
    alignItems: 'center',
    backgroundColor: palette.surface,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: palette.border,
    paddingVertical: spacing.xxl,
    paddingHorizontal: spacing.xl,
    marginBottom: spacing.lg,
    ...shadow.card,
  },
  heroIcon: {
    width: 80,
    height: 80,
    borderRadius: 40,
    backgroundColor: palette.primarySoft,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: spacing.lg,
  },
  title: { ...typography.title, textAlign: 'center' },
  caption: { ...typography.caption, marginTop: spacing.md, textTransform: 'uppercase', letterSpacing: 0.6 },
  scene: { ...typography.subtitle, color: palette.primary, marginTop: spacing.xxs, textAlign: 'center' },
  details: {
    backgroundColor: palette.surface,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: palette.border,
    paddingHorizontal: spacing.lg,
  },
  detailRow: { paddingVertical: spacing.md },
  detailDivider: { borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: palette.border },
  detailLabel: { ...typography.caption },
  detailValue: { ...typography.body, marginTop: spacing.xxs },
});
