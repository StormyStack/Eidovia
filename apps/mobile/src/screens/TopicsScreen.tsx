import { Ionicons } from '@expo/vector-icons';
import { useCallback, useLayoutEffect } from 'react';
import { Alert, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import type { ScreenProps } from '../navigation/types';
import { useAuthStore } from '../store/authStore';
import { layout, palette, radius, shadow, spacing, typography } from '../theme';

/** First screen after login: the topics to learn. DNA is the first (and for now the only) topic. */
export function TopicsScreen({ navigation }: ScreenProps<'Topics'>) {
  const username = useAuthStore((s) => s.profile?.username);
  const logout = useAuthStore((s) => s.logout);
  const insets = useSafeAreaInsets();

  const confirmLogout = useCallback(() => {
    Alert.alert('Log out?', 'You will need to log in again to continue.', [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Log out', style: 'destructive', onPress: () => void logout() },
    ]);
  }, [logout]);

  useLayoutEffect(() => {
    navigation.setOptions({
      headerRight: () => (
        <Pressable
          onPress={confirmLogout}
          accessibilityRole="button"
          accessibilityLabel="Log out"
          hitSlop={10}
          style={styles.headerButton}
          testID="logout-button"
        >
          <Ionicons name="log-out-outline" size={22} color={palette.primary} />
          <Text style={styles.headerButtonText}>Log out</Text>
        </Pressable>
      ),
    });
  }, [navigation, confirmLogout]);

  return (
    <ScrollView
      style={styles.screen}
      contentContainerStyle={[styles.content, { paddingBottom: spacing.xl + insets.bottom }]}
      testID="topics-screen"
    >
      <Text style={styles.greeting} testID="home-greeting" accessibilityRole="header">
        {username ? `Hi, ${username}!` : 'Hi there!'}
      </Text>
      <Text style={styles.subtitle}>Choose a topic to start learning.</Text>

      <Text style={styles.sectionLabel}>Topics</Text>
      <Pressable
        onPress={() => navigation.navigate('Dna')}
        accessibilityRole="button"
        accessibilityLabel="DNA"
        testID="topic-dna"
        style={({ pressed }) => [styles.topic, pressed && styles.topicPressed]}
      >
        <View style={styles.topicIcon}>
          <Ionicons name="infinite" size={30} color={palette.primary} />
        </View>
        <View style={styles.topicText}>
          <Text style={styles.topicTitle}>DNA</Text>
          <Text style={styles.topicCaption}>The double helix in AR, the AI tutor and your progress</Text>
        </View>
        <Ionicons name="chevron-forward" size={22} color={palette.textMuted} />
      </Pressable>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: palette.background },
  content: {
    paddingHorizontal: spacing.xl,
    paddingTop: spacing.xl,
    width: '100%',
    maxWidth: layout.maxContentWidth,
    alignSelf: 'center',
  },
  greeting: { ...typography.display },
  subtitle: { ...typography.bodyMuted, marginTop: spacing.xs, marginBottom: spacing.xl },
  sectionLabel: { ...typography.caption, textTransform: 'uppercase', letterSpacing: 0.6, marginBottom: spacing.sm },
  headerButton: { flexDirection: 'row', alignItems: 'center', gap: spacing.xs, paddingVertical: spacing.xs },
  headerButtonText: { ...typography.label, color: palette.primary },
  topic: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    backgroundColor: palette.surface,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: palette.border,
    padding: spacing.lg,
    ...shadow.card,
  },
  topicPressed: { backgroundColor: palette.primarySoft },
  topicIcon: {
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: palette.primarySoft,
    alignItems: 'center',
    justifyContent: 'center',
  },
  topicText: { flex: 1 },
  topicTitle: { ...typography.title },
  topicCaption: { ...typography.caption, marginTop: 2 },
});
