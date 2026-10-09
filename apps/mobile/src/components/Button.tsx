import { Ionicons } from '@expo/vector-icons';
import type { ComponentProps } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';

import { layout, palette, radius, spacing, typography } from '../theme';

type Variant = 'primary' | 'secondary' | 'ghost';

export interface ButtonProps {
  title: string;
  onPress: () => void;
  variant?: Variant;
  loading?: boolean;
  disabled?: boolean;
  icon?: ComponentProps<typeof Ionicons>['name'];
  testID?: string;
  accessibilityHint?: string;
}

export function Button({ title, onPress, variant = 'primary', loading = false, disabled = false, icon, testID, accessibilityHint }: ButtonProps) {
  const inactive = disabled || loading;
  const textColor = variant === 'primary' ? palette.onPrimary : palette.primary;

  return (
    <Pressable
      testID={testID}
      onPress={onPress}
      disabled={inactive}
      accessibilityRole="button"
      accessibilityLabel={title}
      accessibilityHint={accessibilityHint}
      accessibilityState={{ disabled: inactive, busy: loading }}
      style={({ pressed }) => [
        styles.base,
        styles[variant],
        pressed && !inactive && (variant === 'primary' ? styles.primaryPressed : styles.softPressed),
        inactive && styles.inactive,
      ]}
    >
      <View style={styles.content}>
        {loading ? (
          <ActivityIndicator color={textColor} testID={testID ? `${testID}-spinner` : undefined} />
        ) : icon ? (
          <Ionicons name={icon} size={20} color={textColor} />
        ) : null}
        <Text style={[styles.text, { color: textColor }]}>{title}</Text>
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  base: {
    minHeight: layout.minTouchSize,
    borderRadius: radius.md,
    paddingHorizontal: spacing.lg,
    justifyContent: 'center',
  },
  primary: { backgroundColor: palette.primary },
  secondary: { backgroundColor: palette.surface, borderWidth: 1, borderColor: palette.primary },
  ghost: { backgroundColor: 'transparent' },
  primaryPressed: { backgroundColor: palette.primaryPressed },
  softPressed: { backgroundColor: palette.primarySoft },
  inactive: { opacity: 0.6 },
  content: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: spacing.sm },
  text: typography.button,
});
