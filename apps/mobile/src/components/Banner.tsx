import { Ionicons } from '@expo/vector-icons';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { palette, radius, spacing, typography } from '../theme';

type Tone = 'error' | 'warning' | 'info';

const TONES = {
  error: { icon: 'alert-circle', fg: palette.danger, bg: palette.dangerSoft, border: palette.dangerBorder },
  warning: { icon: 'time-outline', fg: palette.warning, bg: palette.warningSoft, border: palette.warningBorder },
  info: { icon: 'information-circle-outline', fg: palette.info, bg: palette.infoSoft, border: palette.infoBorder },
} as const;

export interface BannerProps {
  message: string;
  title?: string;
  tone?: Tone;
  onDismiss?: () => void;
  testID?: string;
}

/** Inline message (form errors, session notices, info). Announced by screen readers. */
export function Banner({ message, title, tone = 'error', onDismiss, testID }: BannerProps) {
  const t = TONES[tone];
  return (
    <View
      testID={testID}
      accessibilityRole={tone === 'error' ? 'alert' : undefined}
      accessibilityLiveRegion="polite"
      style={[styles.container, { backgroundColor: t.bg, borderColor: t.border }]}
    >
      <Ionicons name={t.icon} size={20} color={t.fg} style={styles.icon} />
      <View style={styles.body}>
        {title ? <Text style={[styles.title, { color: t.fg }]}>{title}</Text> : null}
        <Text style={[styles.message, { color: t.fg }]}>{message}</Text>
      </View>
      {onDismiss ? (
        <Pressable onPress={onDismiss} accessibilityRole="button" accessibilityLabel="Dismiss message" hitSlop={10}>
          <Ionicons name="close" size={18} color={t.fg} />
        </Pressable>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    borderWidth: 1,
    borderRadius: radius.md,
    padding: spacing.md,
    marginBottom: spacing.lg,
    gap: spacing.sm,
  },
  icon: { marginTop: 1 },
  body: { flex: 1 },
  title: { ...typography.label, marginBottom: spacing.xxs },
  message: { ...typography.caption, fontSize: 14, lineHeight: 20 },
});
