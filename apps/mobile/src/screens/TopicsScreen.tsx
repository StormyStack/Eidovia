import { Ionicons } from '@expo/vector-icons';
import { useLayoutEffect } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import type { ScreenProps } from '../navigation/types';
import { useAuthStore } from '../store/authStore';
import { layout, palette, radius, shadow, spacing, typography } from '../theme';

/** First screen after login: the topics to learn (DNA first). The header opens the Profile page. */
export function TopicsScreen({ navigation }: ScreenProps<'Topics'>) {
  const username = useAuthStore((s) => s.profile?.username);
  const insets = useSafeAreaInsets();
  useLayoutEffect(() => {
    navigation.setOptions({
      headerRight: () => (
        <Pressable
          onPress={() => navigation.navigate('Profile')}
          accessibilityRole="button"
          accessibilityLabel="Profile"
          hitSlop={10}
          style={styles.headerButton}
          testID="profile-button"
        >
          <Ionicons name="person-circle-outline" size={26} color={palette.primary} />
          <Text style={styles.headerButtonText}>Profile</Text>
        </Pressable>
      ),
    });
  }, [navigation]);

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
