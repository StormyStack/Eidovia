import { Ionicons } from '@expo/vector-icons';
import { ActivityIndicator, Image, Pressable, StyleSheet, Text, View } from 'react-native';

import type { ModuleSummary } from '../services/types';
import { difficultyLabel, layout, palette, radius, shadow, spacing, typography } from '../theme';

export interface ModuleCardProps {
  module: ModuleSummary;
  onPress: (module: ModuleSummary) => void;
  /** This card is fetching its config. */
  busy?: boolean;
  /** Another card is busy: ignore taps. */
  disabled?: boolean;
}

export function ModuleCard({ module, onPress, busy = false, disabled = false }: ModuleCardProps) {
  const level = difficultyLabel(module.difficulty);
  return (
    <Pressable
      testID={`module-${module.module_id}`}
      onPress={() => onPress(module)}
      disabled={busy || disabled}
      accessibilityRole="button"
      accessibilityLabel={`${module.title}. ${level}.${module.description ? ` ${module.description}` : ''}`}
      accessibilityHint="Opens this AR module"
      accessibilityState={{ busy, disabled: busy || disabled }}
      style={({ pressed }) => [styles.card, pressed && styles.pressed, disabled && styles.dimmed]}
    >
      {module.thumbnail_url ? (
        <Image source={{ uri: module.thumbnail_url }} style={styles.thumb} accessibilityIgnoresInvertColors />
      ) : (
        <View style={[styles.thumb, styles.thumbPlaceholder]}>
          <Ionicons name="cube-outline" size={28} color={palette.primary} />
        </View>
      )}

      <View style={styles.body}>
        <Text style={styles.title} numberOfLines={2}>
          {module.title}
        </Text>
        {module.description ? (
          <Text style={styles.description} numberOfLines={2}>
            {module.description}
          </Text>
        ) : null}
        <View style={styles.levelRow}>
          {[1, 2, 3].map((dot) => (
            <View key={dot} style={[styles.dot, dot <= Math.min(module.difficulty, 3) && styles.dotOn]} />
          ))}
          <Text style={styles.level}>{level}</Text>
        </View>
      </View>

      <View style={styles.trailing}>
        {busy ? (
          <ActivityIndicator color={palette.primary} testID={`module-${module.module_id}-spinner`} />
        ) : (
          <Ionicons name="chevron-forward" size={22} color={palette.placeholder} />
        )}
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: palette.surface,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: palette.border,
    padding: spacing.md,
    marginBottom: spacing.md,
    minHeight: layout.minTouchSize + spacing.xl,
    ...shadow.card,
  },
  pressed: { backgroundColor: palette.primarySoft },
  dimmed: { opacity: 0.55 },
  thumb: { width: 64, height: 64, borderRadius: radius.md },
  thumbPlaceholder: { backgroundColor: palette.primarySoft, alignItems: 'center', justifyContent: 'center' },
  body: { flex: 1, marginLeft: spacing.md },
  title: { ...typography.subtitle },
  description: { ...typography.caption, marginTop: spacing.xxs },
  levelRow: { flexDirection: 'row', alignItems: 'center', marginTop: spacing.sm, gap: spacing.xs },
  dot: { width: 8, height: 8, borderRadius: 4, backgroundColor: palette.border },
  dotOn: { backgroundColor: palette.primary },
  level: { ...typography.caption, fontWeight: '600', color: palette.primary, marginLeft: spacing.xs },
  trailing: { width: 32, alignItems: 'flex-end' },
});
