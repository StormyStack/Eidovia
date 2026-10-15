import { Ionicons } from '@expo/vector-icons';
import { useCallback, useEffect, useRef, useState, type ComponentProps } from 'react';
import { ActivityIndicator, Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import type { ScreenProps } from '../navigation/types';
import type { ApiError } from '../services/ApiClient';
import { toApiError } from '../services/ApiClient';
import { ArService, type ArProgress, type LevelStatus } from '../services/ArService';
import { formatCountdown, formatWhen, QuizService, REQUEST_LABELS, type QuizHistory, type QuizStatus } from '../services/QuizService';
import { layout, palette, radius, shadow, spacing, typography } from '../theme';
import { DNA_AR } from './ARGameScreen';

type IconName = ComponentProps<typeof Ionicons>['name'];

/** Short level names, as on the game's level buttons (Unity LevelManager.ShortNames). */
const SHORT_NAMES = ['Blocks', 'Nucleotide', 'Strand', 'Two strands', 'Helix'];

export function formatPlayTime(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
  if (h) return `${h}h ${m}m`;
  if (m) return `${m}m`;
  return `${s}s`;
}

/** The DNA topic: open the AR game, the AI tutor or the quiz, and see your own progress and quiz results. */
export function DnaScreen({ navigation }: ScreenProps<'Dna'>) {
  const insets = useSafeAreaInsets();
  const [progress, setProgress] = useState<ArProgress | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [quiz, setQuiz] = useState<{ status: QuizStatus; history: QuizHistory } | null>(null);
  const [quizError, setQuizError] = useState<ApiError | null>(null);
  const request = useRef<AbortController | null>(null);

  const loadQuiz = useCallback(async (signal: AbortSignal) => {
    try {
      const [status, history] = await Promise.all([QuizService.status(signal), QuizService.history(signal)]);
      if (signal.aborted) return;
      setQuiz({ status, history });
      setQuizError(null);
    } catch (e) {
      const apiError = toApiError(e);
      if (signal.aborted || apiError.code === 'CANCELLED' || apiError.status === 401) return;
      setQuizError(apiError);
    }
  }, []);

  const load = useCallback(async (pull = false) => {
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    if (pull) setRefreshing(true);
    const quizDone = loadQuiz(controller.signal); // separate card: one failing does not hide the other
    try {
      const data = await ArService.getProgress(controller.signal);
      if (controller.signal.aborted) return;
      setProgress(data);
      setError(null);
    } catch (e) {
      const apiError = toApiError(e);
      if (controller.signal.aborted || apiError.code === 'CANCELLED' || apiError.status === 401) return;
      setError(apiError);
    } finally {
      await quizDone;
      if (request.current === controller) setRefreshing(false);
    }
  }, [loadQuiz]);

  // fresh numbers every time the page is shown (e.g. back from the AR game, the chat or the quiz)
  useEffect(() => {
    void load();
    const unsubscribe = navigation.addListener('focus', () => void load());
    return () => {
      unsubscribe();
      request.current?.abort();
    };
  }, [navigation, load]);

  return (
    <ScrollView
      style={styles.screen}
      contentContainerStyle={[styles.content, { paddingBottom: spacing.xl + insets.bottom }]}
      testID="dna-screen"
      refreshControl={
        <RefreshControl refreshing={refreshing} onRefresh={() => void load(true)} colors={[palette.primary]} tintColor={palette.primary} />
      }
    >
      <Text style={styles.title} accessibilityRole="header">DNA</Text>
      <Text style={styles.subtitle}>Build the double helix step by step and ask the tutor anything about it.</Text>

      <Pressable
        onPress={() => navigation.navigate('ARGame', DNA_AR)}
        accessibilityRole="button"
        accessibilityLabel="Explore DNA in AR"
        testID="dna-ar-button"
        style={({ pressed }) => [styles.action, styles.actionPrimary, pressed && styles.actionPrimaryPressed]}
      >
        <View style={styles.actionIcon}>
          <Ionicons name="cube" size={26} color={palette.onPrimary} />
        </View>
        <View style={styles.actionText}>
          <Text style={[styles.actionTitle, styles.onPrimary]}>Explore DNA in AR</Text>
          <Text style={[styles.actionCaption, styles.onPrimary]}>Place the DNA model in your room and discover its parts</Text>
        </View>
        <Ionicons name="chevron-forward" size={22} color={palette.onPrimary} />
      </Pressable>

      <Pressable
        onPress={() => navigation.navigate('Chat', {})}
        accessibilityRole="button"
        accessibilityLabel="Ask the AI tutor"
        testID="dna-chat-button"
        style={({ pressed }) => [styles.action, styles.actionSecondary, pressed && styles.actionSecondaryPressed]}
      >
        <View style={[styles.actionIcon, styles.actionIconSoft]}>
          <Ionicons name="chatbubble-ellipses" size={24} color={palette.primary} />
        </View>
        <View style={styles.actionText}>
          <Text style={styles.actionTitle}>Ask the AI tutor</Text>
          <Text style={styles.actionCaption}>Questions about DNA, genes and replication</Text>
        </View>
        <Ionicons name="chevron-forward" size={22} color={palette.textMuted} />
      </Pressable>

      <Pressable
        onPress={() => navigation.navigate('Quiz')}
        accessibilityRole="button"
        accessibilityLabel="DNA Quiz"
        testID="dna-quiz-button"
        style={({ pressed }) => [styles.action, styles.actionSecondary, pressed && styles.actionSecondaryPressed]}
      >
        <View style={[styles.actionIcon, styles.actionIconSoft]}>
          <Ionicons name="school" size={24} color={palette.primary} />
        </View>
        <View style={styles.actionText}>
          <Text style={styles.actionTitle}>DNA Quiz</Text>
          <Text style={styles.actionCaption}>20 questions to test what you learned</Text>
        </View>
        <Ionicons name="chevron-forward" size={22} color={palette.textMuted} />
      </Pressable>

      <Text style={styles.sectionLabel}>Your progress</Text>
      {progress ? (
        <Dashboard progress={progress} />
      ) : error ? (
        <Pressable style={styles.card} onPress={() => void load()} accessibilityRole="button" testID="dna-progress-error">
          <Text style={styles.errorText}>Couldn't load your progress: {error.message}</Text>
          <Text style={styles.retry}>Tap to try again</Text>
        </Pressable>
      ) : (
        <View style={[styles.card, styles.center]} testID="dna-progress-loading">
          <ActivityIndicator color={palette.primary} />
        </View>
      )}

      <Text style={styles.sectionLabel}>Your quiz results</Text>
      {quiz ? (
        <QuizDashboard status={quiz.status} history={quiz.history} />
      ) : quizError ? (
        <Pressable style={styles.card} onPress={() => void load()} accessibilityRole="button" testID="dna-quiz-error">
          <Text style={styles.errorText}>Couldn't load your quiz results: {quizError.message}</Text>
          <Text style={styles.retry}>Tap to try again</Text>
        </Pressable>
      ) : (
        <View style={[styles.card, styles.center]} testID="dna-quiz-loading">
          <ActivityIndicator color={palette.primary} />
        </View>
      )}
    </ScrollView>
  );
}

const pct = (v: number | null | undefined) => (v === null || v === undefined ? '--' : `${Math.round(v)}%`);
const TYPE_LABEL = { normal: 'Normal', forced: 'Force Attempt', authorized: 'Approved by admin' } as const;

/** Quiz part of the dashboard: only completed attempts count as results (abandoned/expired are shown, not scored). */
function QuizDashboard({ status: s, history: h }: { status: QuizStatus; history: QuizHistory }) {
  const sum = h.summary;
  const next = s.active_attempt
    ? 'A quiz is in progress'
    : s.eligible
      ? 'Available now'
      : `${formatWhen(s.next_eligible_at)} (in ${formatCountdown(s.cooldown_remaining_s)})`;
  const req = s.pending_request
    ? `Waiting for an admin (sent ${formatWhen(s.pending_request.created_at)})`
    : s.authorization
      ? `Approved: start between ${formatWhen(s.authorization.window_start)} and ${formatWhen(s.authorization.window_end)}`
      : s.requests[0]
        ? `Last request: ${REQUEST_LABELS[s.requests[0].status]}`
        : null;
  return (
    <View testID="dna-quiz">
      <View style={styles.card}>
        <Text style={styles.headline} testID="quiz-latest">
          {sum.latest ? `Latest score ${sum.latest.score}/${sum.latest.total} (${pct(sum.latest.percent)})` : 'No quiz completed yet.'}
        </Text>
        <Text style={styles.quizLine} testID="quiz-completion">
          {sum.ever_completed ? 'Completed' : 'Not completed yet'} · {sum.completed_attempts} completed of {sum.total_attempts} attempt{sum.total_attempts === 1 ? '' : 's'}
        </Text>
        <Text style={styles.quizLine} testID="quiz-next">Next attempt: {next}</Text>
        {req ? <Text style={styles.quizLine} testID="quiz-request-status">Early-attempt request: {req}</Text> : null}
      </View>

      <View style={styles.grid}>
        <Stat icon="trophy" label="Best score" value={sum.best ? `${sum.best.score}/${sum.best.total}` : '--'} testID="quiz-best" />
        <Stat icon="stats-chart" label="Average" value={pct(sum.average_percent)} testID="quiz-average" />
        <Stat icon="checkmark-done" label="Completed / attempts" value={`${sum.completed_attempts}/${sum.total_attempts}`} testID="quiz-attempts" />
        <Stat icon="star" label="Wildcards" value={String(s.wildcards)} testID="quiz-wildcards" tint="#D97706" />
        <Stat icon="flash" label={`Spent on Force (${sum.forced_attempts}×)`} value={String(sum.wildcards_spent)} testID="quiz-force-spent" tint="#D97706" />
        <Stat icon="time" label="Completion rate" value={sum.completion_rate === null ? '--' : `${Math.round(sum.completion_rate)}%`} testID="quiz-rate" />
      </View>

      {h.attempts.length ? (
        <View style={styles.card} testID="quiz-history">
          {h.attempts.slice(0, 10).map((a, i) => (
            <View key={a.attempt_id} style={[styles.historyRow, i > 0 && styles.historyBorder]} testID={`quiz-history-${a.attempt_id}`}>
              <View style={styles.historyText}>
                <Text style={styles.historyWhen}>{formatWhen(a.ended_at ?? a.started_at)}</Text>
                <Text style={styles.legendText}>{TYPE_LABEL[a.attempt_type] ?? a.attempt_type}</Text>
              </View>
              <Text style={a.status === 'completed' ? styles.historyScore : styles.historyStatus}>
                {a.status === 'completed' ? `${a.score}/${a.total} · ${pct(a.percent)}` : a.status.replace('_', ' ')}
              </Text>
            </View>
          ))}
        </View>
      ) : null}
    </View>
  );
}

function Dashboard({ progress: p }: { progress: ArProgress }) {
  const done = p.levels_passed + p.levels_skipped;
  const headline = p.finished
    ? 'Journey finished! You built the whole double helix.'
    : p.current_level
      ? `Level ${p.current_level} of ${p.level_count} · ${p.current_level_name}`
      : 'Not started yet. Open the AR game to begin.';
  return (
    <View testID="dna-progress">
      <View style={styles.card}>
        <Text style={styles.headline} testID="dna-progress-headline">{headline}</Text>
        <View style={styles.track}>
          {p.levels.map((lv, i) => (
            <View key={lv.level} style={styles.trackItem}>
              {i > 0 && <View style={[styles.trackLine, p.levels[i - 1].status !== 'not_yet' && styles.trackLineDone]} />}
              <LevelDot status={lv.status} current={lv.current} level={lv.level} />
              <Text style={styles.trackLabel} numberOfLines={1}>{SHORT_NAMES[i] ?? lv.name}</Text>
            </View>
          ))}
        </View>
        <View style={styles.legend}>
          <Legend color={palette.success} label="passed" />
          <Legend color="#D97706" label="wildcard" />
          <Legend color={palette.borderStrong} label="not yet" />
        </View>
      </View>

      <View style={styles.grid}>
        <Stat icon="trophy" label="Levels done" value={`${done}/${p.level_count}`} testID="stat-levels" />
        <Stat icon="star" label="Wildcards" value={String(p.wildcards)} testID="stat-wildcards" tint="#D97706" />
        <Stat icon="time" label="Play time" value={formatPlayTime(p.play_seconds)} testID="stat-time" />
        <Stat icon="cube" label="AR sessions" value={String(p.sessions)} testID="stat-sessions" />
        <Stat icon="search" label="Parts found" value={String(p.parts_discovered)} testID="stat-parts" />
        <Stat icon="chatbubbles" label="Tutor questions" value={String(p.chat_questions)} testID="stat-chats" />
        <Stat icon="flash" label="Wildcards used" value={String(p.wildcards_used)} testID="stat-wild-used" />
        <Stat icon="arrow-undo" label="Back used" value={String(p.back_used)} testID="stat-back" />
      </View>
      {p.last_played ? (
        <Text style={styles.lastPlayed}>Last played {new Date(p.last_played).toLocaleString()}</Text>
      ) : null}
    </View>
  );
}

function LevelDot({ status, current, level }: { status: LevelStatus; current: boolean; level: number }) {
  const style =
    status === 'passed' ? styles.dotPassed : status === 'skipped' ? styles.dotSkipped : styles.dotTodo;
  const label = status === 'passed' ? 'passed' : status === 'skipped' ? 'done with a wildcard' : 'not done yet';
  return (
    <View
      style={[styles.dot, style, current && styles.dotCurrent]}
      accessibilityLabel={`Level ${level}: ${label}${current ? ', you are here' : ''}`}
      testID={`level-${level}-${status}`}
    >
      {status === 'passed' ? (
        <Ionicons name="checkmark" size={18} color={palette.onPrimary} />
      ) : status === 'skipped' ? (
        <Ionicons name="star" size={15} color={palette.onPrimary} />
      ) : (
        <Text style={styles.dotNumber}>{level}</Text>
      )}
    </View>
  );
}

function Legend({ color, label }: { color: string; label: string }) {
  return (
    <View style={styles.legendItem}>
      <View style={[styles.legendDot, { backgroundColor: color }]} />
      <Text style={styles.legendText}>{label}</Text>
    </View>
  );
}

function Stat({ icon, label, value, testID, tint = palette.primary }: { icon: IconName; label: string; value: string; testID: string; tint?: string }) {
  return (
    <View style={styles.stat} testID={testID}>
      <Ionicons name={icon} size={18} color={tint} />
      <Text style={styles.statValue}>{value}</Text>
      <Text style={styles.statLabel}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: palette.background },
  content: {
    paddingHorizontal: spacing.xl,
    paddingTop: spacing.lg,
    width: '100%',
    maxWidth: layout.maxContentWidth,
    alignSelf: 'center',
  },
  title: { ...typography.display },
  subtitle: { ...typography.bodyMuted, marginTop: spacing.xs, marginBottom: spacing.xl },
  sectionLabel: { ...typography.caption, textTransform: 'uppercase', letterSpacing: 0.6, marginTop: spacing.lg, marginBottom: spacing.sm },
  action: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    borderRadius: radius.lg,
    padding: spacing.lg,
    marginBottom: spacing.md,
  },
  actionPrimary: { backgroundColor: palette.primary },
  actionPrimaryPressed: { backgroundColor: palette.primaryPressed },
  actionSecondary: { backgroundColor: palette.surface, borderWidth: 1, borderColor: palette.border, ...shadow.card },
  actionSecondaryPressed: { backgroundColor: palette.primarySoft },
  actionIcon: {
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: 'rgba(255, 255, 255, 0.18)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  actionIconSoft: { backgroundColor: palette.primarySoft },
  actionText: { flex: 1 },
  actionTitle: { ...typography.label, fontSize: 17 },
  actionCaption: { ...typography.caption, marginTop: 2 },
  onPrimary: { color: palette.onPrimary, opacity: 0.95 },
  card: {
    backgroundColor: palette.surface,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: palette.border,
    padding: spacing.lg,
    ...shadow.card,
  },
  center: { alignItems: 'center', paddingVertical: spacing.xl },
  errorText: { ...typography.body, color: palette.danger },
  retry: { ...typography.label, color: palette.primary, marginTop: spacing.sm },
  headline: { ...typography.subtitle, marginBottom: spacing.lg },
  track: { flexDirection: 'row', justifyContent: 'space-between' },
  trackItem: { flex: 1, alignItems: 'center' },
  trackLine: { position: 'absolute', top: 17, right: '50%', width: '100%', height: 3, backgroundColor: palette.border },
  trackLineDone: { backgroundColor: palette.success },
  dot: { width: 36, height: 36, borderRadius: 18, alignItems: 'center', justifyContent: 'center' },
  dotPassed: { backgroundColor: palette.success },
  dotSkipped: { backgroundColor: '#D97706' },
  dotTodo: { backgroundColor: palette.surface, borderWidth: 2, borderColor: palette.borderStrong },
  dotCurrent: { borderWidth: 3, borderColor: palette.primary },
  dotNumber: { ...typography.label, color: palette.textMuted },
  trackLabel: { ...typography.caption, fontSize: 11, marginTop: spacing.xs },
  legend: { flexDirection: 'row', justifyContent: 'center', gap: spacing.lg, marginTop: spacing.md },
  legendItem: { flexDirection: 'row', alignItems: 'center', gap: spacing.xs },
  legendDot: { width: 10, height: 10, borderRadius: 5 },
  legendText: { ...typography.caption, fontSize: 12 },
  grid: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between', marginTop: spacing.md },
  stat: {
    width: '48.5%',
    backgroundColor: palette.surface,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: palette.border,
    padding: spacing.md,
    marginBottom: spacing.sm,
  },
  statValue: { ...typography.title, marginTop: spacing.xs },
  statLabel: { ...typography.caption },
  lastPlayed: { ...typography.caption, textAlign: 'center', marginTop: spacing.xs },
  quizLine: { ...typography.bodyMuted, marginTop: spacing.xs },
  historyRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingVertical: spacing.sm, gap: spacing.sm },
  historyBorder: { borderTopWidth: 1, borderTopColor: palette.border },
  historyText: { flex: 1 },
  historyWhen: { ...typography.label },
  historyScore: { ...typography.label, color: palette.primary },
  historyStatus: { ...typography.caption, textTransform: 'capitalize' },
});
