import { Ionicons } from '@expo/vector-icons';
import type { ComponentProps } from 'react';
import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';

import { palette, spacing, typography } from '../theme';
import { Button } from './Button';

type IconName = ComponentProps<typeof Ionicons>['name'];

export function LoadingState({ message = 'Loading…', testID }: { message?: string; testID?: string }) {
  return (
    <View style={styles.container} testID={testID} accessibilityLabel={message}>
      <ActivityIndicator size="large" color={palette.primary} />
      <Text style={[styles.message, styles.loadingText]}>{message}</Text>
    </View>
  );
}

export interface MessageStateProps {
  icon: IconName;
  title: string;
  message: string;
  actionLabel?: string;
  onAction?: () => void;
  testID?: string;
  tone?: 'neutral' | 'error';
}

/** Empty and error states: icon, title, explanation and an optional action (e.g. Retry). */
export function MessageState({ icon, title, message, actionLabel, onAction, testID, tone = 'neutral' }: MessageStateProps) {
  return (
    <View style={styles.container} testID={testID}>
      <View style={[styles.iconCircle, tone === 'error' && styles.iconCircleError]}>
        <Ionicons name={icon} size={30} color={tone === 'error' ? palette.danger : palette.primary} />
      </View>
      <Text style={styles.title}>{title}</Text>
      <Text style={styles.message}>{message}</Text>
      {actionLabel && onAction ? (
        <View style={styles.action}>
          <Button title={actionLabel} onPress={onAction} variant="secondary" icon="refresh" testID={testID ? `${testID}-action` : undefined} />
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { alignItems: 'center', paddingVertical: spacing.xxxl, paddingHorizontal: spacing.xl },
  iconCircle: {
    width: 64,
    height: 64,
    borderRadius: 32,
    backgroundColor: palette.primarySoft,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: spacing.lg,
  },
  iconCircleError: { backgroundColor: palette.dangerSoft },
  title: { ...typography.subtitle, textAlign: 'center', marginBottom: spacing.xs },
  message: { ...typography.bodyMuted, textAlign: 'center' },
  loadingText: { marginTop: spacing.md },
  action: { marginTop: spacing.xl, minWidth: 160 },
});
