import { Ionicons } from '@expo/vector-icons';
import { StyleSheet, Text, View } from 'react-native';

import { Banner } from '../components/Banner';
import { ScreenContainer } from '../components/ScreenContainer';
import type { ScreenProps } from '../navigation/types';
import { difficultyLabel, palette, radius, shadow, spacing, typography } from '../theme';

/**
 * Sprint 1 placeholder. In Sprint 2 this screen embeds <UnityView /> full-screen and
 * hands `config` to Unity via UnityBridge.sendModuleConfig() once Unity signals ready
 * (PDF Flowchart A, step 4). Sprint 3 adds POST /api/sessions + the WebSocket.
 */
export function ARGameScreen({ route }: ScreenProps<'ARGame'>) {
  const { config, title } = route.params;

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
        title="Unity view coming in Sprint 2"
        message="This screen will show the Unity AR scene full-screen and send your interactions to the AI tutor."
        testID="argame-sprint-note"
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
