import { useRef, useState } from 'react';
import { Keyboard, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import { Banner } from '../components/Banner';
import { BrandHeader } from '../components/BrandHeader';
import { Button } from '../components/Button';
import { ScreenContainer } from '../components/ScreenContainer';
import { TextField } from '../components/TextField';
import type { ScreenProps } from '../navigation/types';
import { toApiError } from '../services/ApiClient';
import { useAuthStore } from '../store/authStore';
import { palette, spacing, typography } from '../theme';
import { PASSWORD_MIN, hasErrors, validateSignUp, type FieldErrors, type SignUpValues } from '../utils/validation';

const EMPTY: SignUpValues = { username: '', email: '', password: '', confirmPassword: '' };
const SERVER_FIELDS: (keyof SignUpValues)[] = ['username', 'email', 'password'];

export function SignUpScreen({ navigation }: ScreenProps<'SignUp'>) {
  const register = useAuthStore((s) => s.register);

  const [values, setValues] = useState<SignUpValues>(EMPTY);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors<keyof SignUpValues>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const emailRef = useRef<TextInput>(null);
  const passwordRef = useRef<TextInput>(null);
  const confirmRef = useRef<TextInput>(null);

  const update = (key: keyof SignUpValues) => (text: string) => {
    setValues((current) => ({ ...current, [key]: text }));
    setFieldErrors((current) => ({ ...current, [key]: undefined }));
    setFormError(null);
  };

  const submit = async () => {
    if (submitting) return;
    Keyboard.dismiss();
    const errors = validateSignUp(values);
    setFieldErrors(errors);
    if (hasErrors(errors)) return;

    setSubmitting(true);
    setFormError(null);
    try {
      await register({ username: values.username.trim(), email: values.email.trim(), password: values.password });
      // Success = auto-login: App.tsx switches to the signed-in stack.
    } catch (error) {
      const apiError = toApiError(error);
      // 409 USERNAME_TAKEN / EMAIL_TAKEN and 400 field errors go under their fields
      const serverFieldErrors: FieldErrors<keyof SignUpValues> = {};
      for (const field of SERVER_FIELDS) {
        if (apiError.fields[field]) serverFieldErrors[field] = apiError.fields[field];
      }
      if (hasErrors(serverFieldErrors)) {
        setFieldErrors(serverFieldErrors);
      } else {
        setFormError(apiError.message);
      }
      setSubmitting(false);
    }
  };

  const goToLogin = () => {
    if (navigation.canGoBack()) navigation.goBack();
    else navigation.navigate('Login');
  };

  return (
    <ScreenContainer centered testID="signup-screen">
      <BrandHeader subtitle="Create your account to start exploring cells in AR." />

      {formError ? <Banner tone="error" message={formError} testID="signup-error" /> : null}

      <TextField
        testID="signup-username"
        label="Username"
        value={values.username}
        onChangeText={update('username')}
        error={fieldErrors.username}
        hint="3–32 characters: letters, numbers, _ . -"
        placeholder="Choose a username"
        autoCapitalize="none"
        autoCorrect={false}
        autoComplete="username-new"
        textContentType="username"
        returnKeyType="next"
        submitBehavior="submit"
        onSubmitEditing={() => emailRef.current?.focus()}
        editable={!submitting}
      />
      <TextField
        ref={emailRef}
        testID="signup-email"
        label="Email"
        value={values.email}
        onChangeText={update('email')}
        error={fieldErrors.email}
        placeholder="you@example.com"
        keyboardType="email-address"
        autoCapitalize="none"
        autoCorrect={false}
        autoComplete="email"
        textContentType="emailAddress"
        returnKeyType="next"
        submitBehavior="submit"
        onSubmitEditing={() => passwordRef.current?.focus()}
        editable={!submitting}
      />
      <TextField
        ref={passwordRef}
        testID="signup-password"
        label="Password"
        password
        value={values.password}
        onChangeText={update('password')}
        error={fieldErrors.password}
        hint={`At least ${PASSWORD_MIN} characters.`}
        placeholder="Create a password"
        autoCapitalize="none"
        autoCorrect={false}
        autoComplete="new-password"
        textContentType="newPassword"
        returnKeyType="next"
        submitBehavior="submit"
        onSubmitEditing={() => confirmRef.current?.focus()}
        editable={!submitting}
      />
      <TextField
        ref={confirmRef}
        testID="signup-confirm"
        label="Confirm password"
        password
        value={values.confirmPassword}
        onChangeText={update('confirmPassword')}
        error={fieldErrors.confirmPassword}
        placeholder="Re-enter your password"
        autoCapitalize="none"
        autoCorrect={false}
        autoComplete="new-password"
        textContentType="newPassword"
        returnKeyType="go"
        onSubmitEditing={submit}
        editable={!submitting}
      />

      <Button testID="signup-submit" title={submitting ? 'Creating account…' : 'Create account'} onPress={submit} loading={submitting} />

      <View style={styles.footer}>
        <Text style={styles.footerText}>Already have an account?</Text>
        <Pressable onPress={goToLogin} accessibilityRole="link" hitSlop={12} testID="go-to-login" disabled={submitting}>
          <Text style={styles.link}>Log in</Text>
        </Pressable>
      </View>
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  footer: { flexDirection: 'row', justifyContent: 'center', alignItems: 'center', marginTop: spacing.xl, gap: spacing.xs, flexWrap: 'wrap' },
  footerText: typography.bodyMuted,
  link: { ...typography.body, color: palette.primary, fontWeight: '600' },
});
