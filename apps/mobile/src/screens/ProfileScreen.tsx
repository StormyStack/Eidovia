import { Ionicons } from '@expo/vector-icons';
import { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, Alert, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Button } from '../components/Button';
import { TextField } from '../components/TextField';
import { WildcardsCard } from '../components/WildcardsCard';
import type { ScreenProps } from '../navigation/types';
import { toApiError } from '../services/ApiClient';
import { GENDERS, LEVELS, ProfileService, type Gender, type MyProfile, type ProfileChanges } from '../services/ProfileService';
import { WildcardService, type WildcardSummary } from '../services/WildcardService';
import { useAuthStore } from '../store/authStore';
import { layout, palette, radius, shadow, spacing, typography } from '../theme';

/** Profile: name, email, level, age, gender, change password, wildcards (+ request) and log out. */
export function ProfileScreen({ navigation }: ScreenProps<'Profile'>) {
  const insets = useSafeAreaInsets();
  const logout = useAuthStore((s) => s.logout);
  const [profile, setProfile] = useState<MyProfile | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [wildcards, setWildcards] = useState<WildcardSummary | null>(null);

  // editable copy of the details
  const [email, setEmail] = useState('');
  const [level, setLevel] = useState(1);
  const [age, setAge] = useState('');
  const [gender, setGender] = useState<Gender | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const fill = (p: MyProfile) => {
    setProfile(p);
    setEmail(p.email ?? '');
    setLevel(p.level);
    setAge(p.age ? String(p.age) : '');
    setGender(p.gender);
  };

  const load = useCallback(() => {
    ProfileService.get()
      .then((p) => {
        fill(p);
        setLoadError(null);
      })
      .catch((e) => setLoadError(toApiError(e).message));
    WildcardService.summary()
      .then(setWildcards)
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    load();
    return navigation.addListener('focus', load);
  }, [navigation, load]);

  const changes = (): ProfileChanges => {
    if (!profile) return {};
    const c: ProfileChanges = {};
    if (email.trim().toLowerCase() !== (profile.email ?? '')) c.email = email.trim();
    if (level !== profile.level) c.level = level;
    const ageNum = age.trim() === '' ? null : Number(age);
    if (ageNum !== profile.age) c.age = ageNum;
    if (gender !== profile.gender) c.gender = gender;
    return c;
  };
  const dirty = Object.keys(changes()).length > 0;

  const save = async () => {
    const c = changes();
    const errors: Record<string, string> = {};
    if (c.age !== undefined && c.age !== null && !(Number.isInteger(c.age) && c.age >= 5 && c.age <= 120)) {
      errors.age = 'Enter an age from 5 to 120.';
    }
    if (c.email !== undefined && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(c.email)) errors.email = 'Enter a valid email address.';
    setFieldErrors(errors);
    if (Object.keys(errors).length) return;
    setSaving(true);
    setSaveMsg(null);
    try {
      fill(await ProfileService.update(c));
      setSaveMsg({ ok: true, text: 'Profile saved.' });
      void useAuthStore.getState().refreshProfile(); // level / email used elsewhere in the app
    } catch (e) {
      const err = toApiError(e);
      setFieldErrors(err.fields ?? {});
      setSaveMsg({ ok: false, text: err.message });
    } finally {
      setSaving(false);
    }
  };

  const confirmLogout = () => {
    Alert.alert('Log out?', 'You will need to log in again to continue.', [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Log out', style: 'destructive', onPress: () => void logout() },
    ]);
  };

  if (!profile) {
    return (
      <View style={[styles.screen, styles.center]} testID="profile-loading">
        {loadError ? (
          <Pressable onPress={load} accessibilityRole="button" testID="profile-error">
            <Text style={styles.error}>Couldn't load your profile: {loadError}</Text>
            <Text style={styles.retry}>Tap to try again</Text>
          </Pressable>
        ) : (
          <ActivityIndicator color={palette.primary} />
        )}
      </View>
    );
  }

  return (
    <ScrollView
      style={styles.screen}
      contentContainerStyle={[styles.content, { paddingBottom: spacing.xl + insets.bottom }]}
      keyboardShouldPersistTaps="handled"
      testID="profile-screen"
    >
      <View style={styles.head}>
        <View style={styles.avatar}>
          <Text style={styles.avatarText}>{profile.username.slice(0, 1).toUpperCase()}</Text>
        </View>
        <Text style={styles.name} testID="profile-name">{profile.username}</Text>
        <Text style={styles.sub}>{LEVELS[profile.level] ?? profile.level_name}{profile.email ? ` · ${profile.email}` : ''}</Text>
      </View>

      <Text style={styles.section}>Details</Text>
      <View style={styles.card}>
        <TextField
          label="Email"
          value={email}
          onChangeText={setEmail}
          autoCapitalize="none"
          keyboardType="email-address"
          error={fieldErrors.email}
          testID="profile-email"
        />
        <Text style={styles.label}>Level</Text>
        <View style={styles.chips}>
          {[1, 2, 3].map((n) => (
            <Chip key={n} label={LEVELS[n]} on={level === n} onPress={() => setLevel(n)} testID={`profile-level-${n}`} />
          ))}
        </View>
        <Text style={styles.hint}>The AI tutor explains at this level.</Text>
        <TextField
          label="Age"
          value={age}
          onChangeText={(t) => setAge(t.replace(/[^0-9]/g, '').slice(0, 3))}
          keyboardType="number-pad"
          placeholder="Optional"
          error={fieldErrors.age}
          testID="profile-age"
        />
        <Text style={styles.label}>Gender</Text>
        <View style={styles.chips}>
          {GENDERS.map((g) => (
            <Chip
              key={g.value}
              label={g.label}
              on={gender === g.value}
              onPress={() => setGender(gender === g.value ? null : g.value)}
              testID={`profile-gender-${g.value}`}
            />
          ))}
        </View>
        {saveMsg ? (
          <Text style={[styles.msg, saveMsg.ok ? styles.ok : styles.error]} testID="profile-save-msg">{saveMsg.text}</Text>
        ) : null}
        <View style={styles.saveRow}>
          <Button title="Save" onPress={() => void save()} loading={saving} disabled={!dirty} testID="profile-save" />
        </View>
      </View>

      <Text style={styles.section}>Password</Text>
      <PasswordCard username={profile.username} />

      <Text style={styles.section}>Wildcards</Text>
      <WildcardsCard summary={wildcards} onChanged={load} />

      <View style={styles.logout}>
        <Button title="Log out" variant="secondary" icon="log-out-outline" onPress={confirmLogout} testID="logout-button" />
      </View>
    </ScrollView>
  );
}

function PasswordCard({ username }: { username: string }) {
  const [open, setOpen] = useState(false);
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [done, setDone] = useState(false);
  const [resetMsg, setResetMsg] = useState<string | null>(null);

  // forgot the current password → User Support; an admin resets it
  const askReset = () => {
    Alert.alert('Forgot your password?', 'Support will reset it and tell you the new password.', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Send request',
        onPress: () => {
          ProfileService.requestPasswordReset(username)
            .then((r) => setResetMsg(r.message))
            .catch((e) => setResetMsg(toApiError(e).message));
        },
      },
    ]);
  };

  const submit = async () => {
    const e: Record<string, string> = {};
    if (!current) e.current_password = 'Enter your current password.';
    if (next.length < 8) e.new_password = 'At least 8 characters.';
    if (next !== confirm) e.confirm = 'The passwords do not match.';
    setErrors(e);
    if (Object.keys(e).length) return;
    setBusy(true);
    try {
      await ProfileService.changePassword(current, next);
      setDone(true);
      setOpen(false);
      setCurrent('');
      setNext('');
      setConfirm('');
    } catch (err) {
      const apiError = toApiError(err);
      setErrors(Object.keys(apiError.fields ?? {}).length ? apiError.fields : { new_password: apiError.message });
    } finally {
      setBusy(false);
    }
  };

  if (!open) {
    return (
      <View style={styles.card}>
        {done ? <Text style={[styles.msg, styles.ok]} testID="password-done">Password changed.</Text> : null}
        <Pressable onPress={() => { setOpen(true); setDone(false); }} style={styles.rowButton} accessibilityRole="button" testID="password-open">
          <Ionicons name="key-outline" size={20} color={palette.primary} />
          <Text style={styles.rowButtonText}>Change password</Text>
          <Ionicons name="chevron-forward" size={18} color={palette.textMuted} />
        </Pressable>
      </View>
    );
  }
  return (
    <View style={styles.card} testID="password-form">
      <TextField label="Current password" value={current} onChangeText={setCurrent} password error={errors.current_password} testID="password-current" />
      <TextField label="New password" value={next} onChangeText={setNext} password hint="At least 8 characters" error={errors.new_password} testID="password-new" />
      <TextField label="Repeat new password" value={confirm} onChangeText={setConfirm} password error={errors.confirm} testID="password-confirm" />
      <Pressable onPress={askReset} accessibilityRole="link" hitSlop={8} testID="password-forgot">
        <Text style={styles.forgot}>Forgot your current password?</Text>
      </Pressable>
      {resetMsg ? <Text style={styles.hint} testID="password-reset-msg">{resetMsg}</Text> : null}
      <View style={styles.pwButtons}>
        <Pressable onPress={() => { setOpen(false); setErrors({}); }} style={styles.cancel} accessibilityRole="button">
          <Text style={styles.cancelText}>Cancel</Text>
        </Pressable>
        <View style={styles.flex}>
          <Button title="Change password" onPress={() => void submit()} loading={busy} testID="password-save" />
        </View>
      </View>
    </View>
  );
}

function Chip({ label, on, onPress, testID }: { label: string; on: boolean; onPress: () => void; testID: string }) {
  return (
    <Pressable
      onPress={onPress}
      style={[styles.chip, on && styles.chipOn]}
      accessibilityRole="button"
      accessibilityState={{ selected: on }}
      testID={testID}
    >
      <Text style={[styles.chipText, on && styles.chipTextOn]}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: palette.background },
  center: { alignItems: 'center', justifyContent: 'center', padding: spacing.xl },
  content: {
    paddingHorizontal: spacing.xl,
    paddingTop: spacing.lg,
    width: '100%',
    maxWidth: layout.maxContentWidth,
    alignSelf: 'center',
  },
  head: { alignItems: 'center', marginBottom: spacing.md },
  avatar: {
    width: 72,
    height: 72,
    borderRadius: 36,
    backgroundColor: palette.primary,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: spacing.sm,
  },
  avatarText: { ...typography.display, color: palette.onPrimary },
  name: { ...typography.title },
  sub: { ...typography.caption, marginTop: 2 },
  section: { ...typography.caption, textTransform: 'uppercase', letterSpacing: 0.6, marginTop: spacing.lg, marginBottom: spacing.sm },
  card: {
    backgroundColor: palette.surface,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: palette.border,
    padding: spacing.lg,
    ...shadow.card,
  },
  label: { ...typography.label, marginBottom: spacing.xs },
  hint: { ...typography.caption, marginBottom: spacing.md, marginTop: -spacing.xs },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm, marginBottom: spacing.md },
  chip: {
    borderWidth: 1,
    borderColor: palette.borderStrong,
    borderRadius: radius.pill,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    backgroundColor: palette.surface,
  },
  chipOn: { backgroundColor: palette.primary, borderColor: palette.primary },
  chipText: { ...typography.label },
  chipTextOn: { color: palette.onPrimary },
  msg: { ...typography.label, marginBottom: spacing.sm },
  ok: { color: palette.success },
  error: { ...typography.body, color: palette.danger, textAlign: 'center' },
  retry: { ...typography.label, color: palette.primary, textAlign: 'center', marginTop: spacing.sm },
  saveRow: { marginTop: spacing.xs },
  rowButton: { flexDirection: 'row', alignItems: 'center', gap: spacing.md, minHeight: layout.minTouchSize },
  rowButtonText: { ...typography.body, flex: 1, color: palette.primary, fontWeight: '600' },
  pwButtons: { flexDirection: 'row', alignItems: 'center', gap: spacing.md, marginTop: spacing.sm },
  cancel: { paddingHorizontal: spacing.md, paddingVertical: spacing.md },
  cancelText: { ...typography.label, color: palette.textMuted },
  flex: { flex: 1 },
  logout: { marginTop: spacing.xl },
  forgot: { ...typography.label, color: palette.primary, marginBottom: spacing.sm },
});
