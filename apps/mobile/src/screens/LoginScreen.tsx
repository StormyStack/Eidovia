import { useRef, useState } from 'react';
import { Keyboard, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import { Banner } from '../components/Banner';
import { BrandHeader } from '../components/BrandHeader';
import { Button } from '../components/Button';
import { ScreenContainer } from '../components/ScreenContainer';
import { TextField } from '../components/TextField';
import { CONFIG_ERROR } from '../config';
import type { ScreenProps } from '../navigation/types';
import { toApiError } from '../services/ApiClient';
import { useAuthStore } from '../store/authStore';
import { brand, palette, spacing, typography } from '../theme';
import { hasErrors, validateLogin, type FieldErrors, type LoginValues } from '../utils/validation';

export function LoginScreen({ navigation }: ScreenProps<'Login'>) {
  const login = useAuthStore((s) => s.login);
  const notice = useAuthStore((s) => s.notice);
  const clearNotice = useAuthStore((s) => s.clearNotice);

  const [values, setValues] = useState<LoginValues>({ username: '', password: '' });
  const [fieldErrors, setFieldErrors] = useState<FieldErrors<keyof LoginValues>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const passwordRef = useRef<TextInput>(null);

  const update = (key: keyof LoginValues) => (text: string) => {
    setValues((current) => ({ ...current, [key]: text }));
    setFieldErrors((current) => ({ ...current, [key]: undefined }));
    setFormError(null);
  };

  const submit = async () => {
    if (submitting) return;
    Keyboard.dismiss();
    const errors = validateLogin(values);
    setFieldErrors(errors);
    if (hasErrors(errors)) return;

    setSubmitting(true);
    setFormError(null);
    if (notice) clearNotice();
    try {
      await login(values.username.trim(), values.password);
      // Success: App.tsx switches to the signed-in stack; this screen unmounts.
    } catch (error) {
      const apiError = toApiError(error);
      setFormError(apiError.message);
      if (apiError.code === 'INVALID_CREDENTIALS') {
        setValues((current) => ({ ...current, password: '' }));
        passwordRef.current?.focus();
      }
      setSubmitting(false);
    }
  };

  const goToSignUp = () => {
    setFormError(null);
    if (notice) clearNotice();
    navigation.navigate('SignUp');
  };

  return (
    <ScreenContainer centered testID="login-screen">
      <BrandHeader subtitle="Welcome back! Log in to continue learning." />

      {CONFIG_ERROR ? <Banner tone="warning" title="App setup needed" message={CONFIG_ERROR} /> : null}
      {notice ? <Banner tone="warning" message={notice} onDismiss={clearNotice} testID="login-notice" /> : null}
      {formError ? <Banner tone="error" message={formError} testID="login-error" /> : null}

      <TextField
        testID="login-username"
        label="Username"
        value={values.username}
        onChangeText={update('username')}
        error={fieldErrors.username}
        placeholder="Your username"
        autoCapitalize="none"
        autoCorrect={false}
        autoComplete="username"
        textContentType="username"
        returnKeyType="next"
        submitBehavior="submit"
        onSubmitEditing={() => passwordRef.current?.focus()}
        editable={!submitting}
      />
      <TextField
        ref={passwordRef}
        testID="login-password"
        label="Password"
        password
        value={values.password}
        onChangeText={update('password')}
        error={fieldErrors.password}
        placeholder="Your password"
        autoCapitalize="none"
        autoCorrect={false}
        autoComplete="current-password"
        textContentType="password"
        returnKeyType="go"
        onSubmitEditing={submit}
        editable={!submitting}
      />

      <Button testID="login-submit" title={submitting ? 'Logging in…' : 'Log in'} onPress={submit} loading={submitting} />

      <Pressable
        onPress={() => navigation.navigate('ForgotPassword', { username: values.username.trim() })}
        accessibilityRole="link"
        hitSlop={12}
        style={styles.forgot}
        testID="go-to-forgot"
        disabled={submitting}
      >
        <Text style={styles.link}>Forgot password?</Text>
      </Pressable>

      <View style={styles.footer}>
        <Text style={styles.footerText}>New to {brand.name}?</Text>
        <Pressable onPress={goToSignUp} accessibilityRole="link" hitSlop={12} testID="go-to-signup" disabled={submitting}>
          <Text style={styles.link}>Create an account</Text>
        </Pressable>
      </View>
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  footer: { flexDirection: 'row', justifyContent: 'center', alignItems: 'center', marginTop: spacing.xl, gap: spacing.xs, flexWrap: 'wrap' },
  footerText: typography.bodyMuted,
  link: { ...typography.body, color: palette.primary, fontWeight: '600' },
  forgot: { alignSelf: 'center', marginTop: spacing.lg },
});
