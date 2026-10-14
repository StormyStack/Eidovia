import { useState } from 'react';
import { Keyboard, Pressable, StyleSheet, Text } from 'react-native';

import { Banner } from '../components/Banner';
import { BrandHeader } from '../components/BrandHeader';
import { Button } from '../components/Button';
import { ScreenContainer } from '../components/ScreenContainer';
import { TextField } from '../components/TextField';
import type { ScreenProps } from '../navigation/types';
import { toApiError } from '../services/ApiClient';
import { ProfileService } from '../services/ProfileService';
import { palette, spacing, typography } from '../theme';

/**
 * Forgot password: the request goes to User Support in the admin panel; an admin resets the password
 * and tells the learner the new one. There is no self-service reset (no email service in the project).
 */
export function ForgotPasswordScreen({ navigation, route }: ScreenProps<'ForgotPassword'>) {
  const [who, setWho] = useState(route.params?.username ?? '');
  const [message, setMessage] = useState('');
  const [error, setError] = useState<string | undefined>();
  const [sending, setSending] = useState(false);
  const [done, setDone] = useState<string | null>(null);

  const send = async () => {
    Keyboard.dismiss();
    if (who.trim().length < 3) {
      setError('Enter your username or email.');
      return;
    }
    setSending(true);
    setError(undefined);
    try {
      const res = await ProfileService.requestPasswordReset(who.trim(), message.trim());
      setDone(res.message);
    } catch (e) {
      setError(toApiError(e).message);
    } finally {
      setSending(false);
    }
  };

  return (
    <ScreenContainer centered testID="forgot-screen">
      <BrandHeader subtitle="Forgot your password? Ask support to reset it." />
      {done ? (
        <>
          <Banner tone="info" title="Request sent" message={done} testID="forgot-done" />
          <Button title="Back to log in" onPress={() => navigation.goBack()} testID="forgot-back" />
        </>
      ) : (
        <>
          <TextField
            label="Username or email"
            value={who}
            onChangeText={(t) => {
              setWho(t);
              setError(undefined);
            }}
            error={error}
            autoCapitalize="none"
            autoCorrect={false}
            testID="forgot-username"
          />
          <TextField
            label="Message for support (optional)"
            value={message}
            onChangeText={setMessage}
            placeholder="e.g. the best way to contact me"
            maxLength={500}
            testID="forgot-message"
          />
          <Button title="Send request" onPress={() => void send()} loading={sending} testID="forgot-send" />
          <Pressable onPress={() => navigation.goBack()} accessibilityRole="link" hitSlop={12} style={styles.back}>
            <Text style={styles.link}>Back to log in</Text>
          </Pressable>
        </>
      )}
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  back: { alignSelf: 'center', marginTop: spacing.lg },
  link: { ...typography.body, color: palette.primary, fontWeight: '600' },
});
