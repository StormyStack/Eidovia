import { Ionicons } from '@expo/vector-icons';
import { useState, type Ref } from 'react';
import { Pressable, StyleSheet, Text, TextInput, View, type TextInputProps } from 'react-native';

import { layout, palette, radius, spacing, typography } from '../theme';

export interface TextFieldProps extends Omit<TextInputProps, 'style' | 'secureTextEntry'> {
  label: string;
  error?: string;
  hint?: string;
  /** Password field with a show/hide toggle. */
  password?: boolean;
  ref?: Ref<TextInput>;
}

export function TextField({ label, error, hint, password = false, ref, testID, onFocus, onBlur, ...inputProps }: TextFieldProps) {
  const [focused, setFocused] = useState(false);
  const [hidden, setHidden] = useState(true);

  return (
    <View style={styles.container}>
      <Text style={styles.label} nativeID={testID ? `${testID}-label` : undefined}>
        {label}
      </Text>
      <View style={[styles.inputRow, focused && styles.inputFocused, !!error && styles.inputError]}>
        <TextInput
          ref={ref}
          testID={testID}
          style={styles.input}
          placeholderTextColor={palette.placeholder}
          secureTextEntry={password && hidden}
          accessibilityLabel={label}
          accessibilityHint={error ?? hint}
          onFocus={(e) => {
            setFocused(true);
            onFocus?.(e);
          }}
          onBlur={(e) => {
            setFocused(false);
            onBlur?.(e);
          }}
          {...inputProps}
        />
        {password && (
          <Pressable
            testID={testID ? `${testID}-toggle` : undefined}
            onPress={() => setHidden((value) => !value)}
            accessibilityRole="button"
            accessibilityLabel={hidden ? 'Show password' : 'Hide password'}
            hitSlop={8}
            style={styles.toggle}
          >
            <Ionicons name={hidden ? 'eye-outline' : 'eye-off-outline'} size={22} color={palette.textMuted} />
          </Pressable>
        )}
      </View>
      {error ? (
        <Text style={styles.error} testID={testID ? `${testID}-error` : undefined} accessibilityLiveRegion="polite">
          {error}
        </Text>
      ) : hint ? (
        <Text style={styles.hint}>{hint}</Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { marginBottom: spacing.lg },
  label: { ...typography.label, marginBottom: spacing.xs },
  inputRow: {
    flexDirection: 'row',
    alignItems: 'center',
    minHeight: layout.minTouchSize,
    borderWidth: 1,
    borderColor: palette.borderStrong,
    borderRadius: radius.md,
    backgroundColor: palette.surface,
  },
  inputFocused: { borderColor: palette.primary, borderWidth: 1.5 },
  inputError: { borderColor: palette.danger },
  input: {
    flex: 1,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.md,
    fontSize: 16,
    color: palette.text,
  },
  toggle: {
    width: layout.minTouchSize,
    height: layout.minTouchSize,
    alignItems: 'center',
    justifyContent: 'center',
  },
  error: { ...typography.caption, color: palette.danger, marginTop: spacing.xs },
  hint: { ...typography.caption, marginTop: spacing.xs },
});
