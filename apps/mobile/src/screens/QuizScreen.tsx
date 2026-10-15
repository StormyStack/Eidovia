import { Ionicons } from '@expo/vector-icons';
import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import { Alert, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Banner } from '../components/Banner';
import { Button } from '../components/Button';
import { LoadingState, MessageState } from '../components/StateView';
import { TextField } from '../components/TextField';
import type { ScreenProps } from '../navigation/types';
import { toApiError, type ApiError } from '../services/ApiClient';
import {
  formatCountdown,
  formatWhen,
  newIdempotencyKey,
  QuizService,
  REQUEST_LABELS,
  type OptionKey,
  type QuizAttempt,
  type QuizMode,
  type QuizQuestion,
  type QuizStatus,
} from '../services/QuizService';
import { layout, palette, radius, shadow, spacing, typography } from '../theme';
import { formatPlayTime } from './DnaScreen';

type Phase = 'loading' | 'error' | 'home' | 'play' | 'result';
type Notice = { tone: 'error' | 'warning' | 'info'; message: string } | null;
interface Running {
  id: string;
  questions: QuizQuestion[];
  /** local clock time when the server's time limit ends (from the server's own started/expires times) */
  deadline: number;
  type: QuizMode;
}

/** Server answers that change what the screen should show: reload the status. */
const RELOAD_ON = new Set(['COOLDOWN', 'ATTEMPT_IN_PROGRESS', 'FORCE_NOT_NEEDED', 'AUTH_NOT_NEEDED', 'NOT_ENOUGH_WILDCARDS',
  'NOT_YET', 'NOT_AUTHORIZED', 'ATTEMPT_CLOSED', 'REQUEST_EXISTS']);

/**
 * The DNA quiz: start (normal / Force Attempt / approved by an admin), answer one question at a time,
 * submit, and see the result with a review. The server checks every rule and computes the score.
 */
export function QuizScreen({ navigation }: ScreenProps<'Quiz'>) {
  const insets = useSafeAreaInsets();
  const [phase, setPhase] = useState<Phase>('loading');
  const [status, setStatus] = useState<QuizStatus | null>(null);
  const [loadedAt, setLoadedAt] = useState(0);
  const [loadError, setLoadError] = useState<ApiError | null>(null);
  const [notice, setNotice] = useState<Notice>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [running, setRunning] = useState<Running | null>(null);
  const [answers, setAnswers] = useState<Record<string, OptionKey>>({});
  const [index, setIndex] = useState(0);
  const [result, setResult] = useState<QuizAttempt | null>(null);
  const [asking, setAsking] = useState(false);
  const [reason, setReason] = useState('');
  const [now, setNow] = useState(() => Date.now());
  const startKeys = useRef<Partial<Record<QuizMode, string>>>({});
  const phaseRef = useRef<Phase>('loading');
  const runningRef = useRef<Running | null>(null);
  const scroll = useRef<ScrollView>(null);
  phaseRef.current = phase;
  runningRef.current = running;

  const load = useCallback(async () => {
    try {
      const s = await QuizService.status();
      setStatus(s);
      setLoadedAt(Date.now());
      setNow(Date.now());
      setLoadError(null);
      setPhase((p) => (p === 'loading' || p === 'error' ? 'home' : p));
    } catch (e) {
      const err = toApiError(e);
      if (err.status === 401) return; // the app goes back to Login
      setLoadError(err);
      setPhase((p) => (p === 'loading' ? 'error' : p));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  // clock for the cooldown countdown and the quiz timer
  const ticking = phase === 'play' || (phase === 'home' && !!status && !status.eligible);
  useEffect(() => {
    if (!ticking) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [ticking]);

  // a pending request or a scheduled approval: check for the admin's decision every 30 s
  const waiting = phase === 'home' && !!status && (!!status.pending_request || (!!status.authorization && !status.authorization.usable_now));
  useEffect(() => {
    if (!waiting) return;
    const id = setInterval(() => void load(), 30_000);
    return () => clearInterval(id);
  }, [waiting, load]);

  const cooldownLeft = status ? Math.max(0, status.cooldown_remaining_s - (now - loadedAt) / 1000) : 0;
  // cooldown over → ask the server (it decides, not the phone's clock)
  useEffect(() => {
    if (phase === 'home' && status && !status.eligible && !status.active_attempt && status.cooldown_remaining_s > 0 && cooldownLeft <= 0) void load();
  }, [phase, status, cooldownLeft, load]);

  // leaving while answering = abandoning the attempt (asks first)
  const abandon = useCallback(async (): Promise<boolean> => {
    const r = runningRef.current;
    if (!r) return true;
    setBusy('abandon');
    try {
      await QuizService.abandon(r.id);
      setRunning(null);
      return true;
    } catch (e) {
      setNotice({ tone: 'error', message: `Couldn't leave the quiz: ${toApiError(e).message}` });
      return false;
    } finally {
      setBusy(null);
    }
  }, []);

  useEffect(() => {
    return navigation.addListener('beforeRemove', (e) => {
      if (phaseRef.current !== 'play') return;
      e.preventDefault();
      Alert.alert(
        'Leave the quiz?',
        'Your answers will not be scored. The attempt still counts for the 12-hour wait, and wildcards paid for a Force Attempt are not returned.',
        [
          { text: 'Keep going', style: 'cancel' },
          {
            text: 'Leave',
            style: 'destructive',
            onPress: () => {
              void abandon().then((ok) => {
                if (ok) {
                  phaseRef.current = 'home';
                  navigation.dispatch(e.data.action);
                }
              });
            },
          },
        ],
      );
    });
  }, [navigation, abandon]);

  function begin(id: string, questions: QuizQuestion[], msLeft: number, type: QuizMode, previous: Record<string, OptionKey> = {}) {
    setRunning({ id, questions, deadline: Date.now() + msLeft, type });
    setAnswers(previous);
    setIndex(0);
    setResult(null);
    setNotice(null);
    setNow(Date.now());
    setPhase('play');
  }

  async function start(mode: QuizMode) {
    // the same key is reused when a retry follows a network failure: never two attempts or two charges
    const key = startKeys.current[mode] ?? newIdempotencyKey();
    startKeys.current[mode] = key;
    setBusy(mode);
    setNotice(null);
    try {
      const a = await QuizService.start(mode, key);
      delete startKeys.current[mode];
      begin(a.attempt_id, a.questions, Date.parse(a.expires_at) - Date.parse(a.started_at), a.attempt_type);
    } catch (e) {
      const err = toApiError(e);
      if (!err.isRetryable) delete startKeys.current[mode]; // the server answered: a new tap is a new request
      setNotice({ tone: err.code === 'COOLDOWN' || err.code === 'NOT_YET' ? 'warning' : 'error', message: err.message });
      if (RELOAD_ON.has(err.code)) void load();
    } finally {
      setBusy(null);
    }
  }

  async function resume() {
    const active = status?.active_attempt;
    if (!active || !status) return;
    setBusy('resume');
    setNotice(null);
    try {
      const a = await QuizService.getAttempt(active.attempt_id);
      if (a.status !== 'in_progress' || !a.questions) {
        setNotice({ tone: 'warning', message: 'That attempt has already ended.' });
        void load();
        return;
      }
      // time left measured on the server's clock (status.server_time), minus the time since it was fetched
      const msLeft = Date.parse(active.expires_at) - Date.parse(status.server_time) - (Date.now() - loadedAt);
      begin(a.attempt_id, a.questions, msLeft, a.attempt_type);
    } catch (e) {
      setNotice({ tone: 'error', message: toApiError(e).message });
    } finally {
      setBusy(null);
    }
  }

  function confirmAbandonActive() {
    const active = status?.active_attempt;
    if (!active) return;
    Alert.alert('Leave this quiz?', 'It will not be scored and still counts as an attempt.', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Leave',
        style: 'destructive',
        onPress: () => {
          setBusy('abandon');
          QuizService.abandon(active.attempt_id)
            .then(() => load())
            .catch((e) => setNotice({ tone: 'error', message: toApiError(e).message }))
            .finally(() => setBusy(null));
        },
      },
    ]);
  }

  async function submit() {
    if (!running) return;
    const missing = running.questions.findIndex((q) => !answers[q.id]);
    if (missing >= 0) {
      const left = running.questions.filter((q) => !answers[q.id]).length;
      setIndex(missing);
      setNotice({ tone: 'warning', message: `Answer every question first (${left} left).` });
      return;
    }
    setBusy('submit');
    setNotice(null);
    try {
      const r = await QuizService.submit(running.id, answers); // safe to retry: a repeat returns the same result
      setResult(r);
      setRunning(null);
      setPhase('result');
      scroll.current?.scrollTo?.({ y: 0, animated: false });
      void load();
    } catch (e) {
      const err = toApiError(e);
      if (err.code === 'ATTEMPT_CLOSED' || err.code === 'ATTEMPT_NOT_FOUND') {
        setRunning(null);
        setPhase('home');
        void load();
      }
      setNotice({ tone: 'error', message: err.isRetryable ? `${err.message} Your answers are kept: tap Submit again.` : err.message });
    } finally {
      setBusy(null);
    }
  }

  async function sendRequest() {
    setBusy('request');
    setNotice(null);
    try {
      await QuizService.requestAccess(reason);
      setAsking(false);
      setReason('');
      setNotice({ tone: 'info', message: 'Request sent. An admin will approve or reject it here.' });
      await load();
    } catch (e) {
      const err = toApiError(e);
      setNotice({ tone: 'error', message: err.message });
      if (RELOAD_ON.has(err.code)) void load();
    } finally {
      setBusy(null);
    }
  }

  // time is up: the server no longer accepts this attempt
  const timeLeft = running ? (running.deadline - now) / 1000 : 0;
  useEffect(() => {
    if (phase === 'play' && running && timeLeft <= 0) {
      setRunning(null);
      setPhase('home');
      setNotice({ tone: 'warning', message: 'Time is up. This attempt expired without a score.' });
      void load();
    }
  }, [phase, running, timeLeft, load]);

  let body: ReactNode;
  if (phase === 'loading') {
    body = <LoadingState message="Loading the quiz…" testID="quiz-loading" />;
  } else if (phase === 'error' || !status) {
    body = (
      <MessageState
        icon="cloud-offline-outline"
        tone="error"
        title="Couldn't load the quiz"
        message={loadError?.message ?? 'Please try again.'}
        actionLabel="Try again"
        onAction={() => {
          setPhase('loading');
          void load();
        }}
        testID="quiz-error"
      />
    );
  } else if (phase === 'play' && running) {
    body = (
      <Play
        running={running}
        index={index}
        answers={answers}
        timeLeft={timeLeft}
        busy={busy === 'submit'}
        onPick={(qid, key) => setAnswers((a) => ({ ...a, [qid]: key }))}
        onGo={(i) => setIndex(i)}
        onSubmit={() => void submit()}
      />
    );
  } else if (phase === 'result' && result) {
    body = <Result result={result} onDone={() => navigation.goBack()} onAgain={() => setPhase('home')} />;
  } else {
    body = (
      <Home
        status={status}
        cooldownLeft={cooldownLeft}
        busy={busy}
        asking={asking}
        reason={reason}
        onStart={(m) => void start(m)}
        onResume={() => void resume()}
        onAbandon={confirmAbandonActive}
        onAsk={() => setAsking(true)}
        onReason={setReason}
        onSend={() => void sendRequest()}
        onCancelAsk={() => setAsking(false)}
      />
    );
  }

  return (
    <ScrollView
      ref={scroll}
      style={styles.screen}
      contentContainerStyle={[styles.content, { paddingBottom: spacing.xl + insets.bottom }]}
      keyboardShouldPersistTaps="handled"
      testID="quiz-screen"
    >
      {notice ? <Banner tone={notice.tone} message={notice.message} onDismiss={() => setNotice(null)} testID="quiz-notice" /> : null}
      {body}
    </ScrollView>
  );
}

// ============================================================
// HOME: start / cooldown / force / admin approval / requests
// ============================================================

function Home(props: {
  status: QuizStatus;
  cooldownLeft: number;
  busy: string | null;
  asking: boolean;
  reason: string;
  onStart: (mode: QuizMode) => void;
  onResume: () => void;
  onAbandon: () => void;
  onAsk: () => void;
  onReason: (v: string) => void;
  onSend: () => void;
  onCancelAsk: () => void;
}) {
  const { status: s, busy } = props;
  const minutes = Math.round(s.quiz.time_limit_s / 60);
  const auth = s.authorization;
  return (
    <View testID="quiz-home">
      <Text style={styles.title} accessibilityRole="header">{s.quiz.title}</Text>
      <Text style={styles.subtitle}>
        {s.quiz.question_count} questions · {minutes} minutes · one attempt every {s.quiz.cooldown_hours} hours
      </Text>

      {s.active_attempt ? (
        <View style={styles.card} testID="quiz-active">
          <Text style={styles.cardTitle}>You have a quiz in progress</Text>
          <Text style={styles.muted}>Started {formatWhen(s.active_attempt.started_at)}. Finish it before {formatWhen(s.active_attempt.expires_at)}.</Text>
          <View style={styles.gap}>
            <Button title="Continue the quiz" icon="play" onPress={props.onResume} loading={busy === 'resume'} disabled={!!busy} testID="quiz-resume" />
            <Button title="Leave it (no score)" variant="ghost" onPress={props.onAbandon} disabled={!!busy} testID="quiz-abandon-active" />
          </View>
        </View>
      ) : s.eligible ? (
        <View style={styles.card} testID="quiz-ready">
          <Text style={styles.cardTitle}>Ready when you are</Text>
          <Text style={styles.muted}>
            Answer all {s.quiz.question_count} questions, then submit. Your score is checked on the server. Once you start, the
            next attempt opens {s.quiz.cooldown_hours} hours later.
          </Text>
          <View style={styles.gap}>
            <Button title="Start the quiz" icon="play" onPress={() => props.onStart('normal')} loading={busy === 'normal'} disabled={!!busy} testID="quiz-start" />
          </View>
        </View>
      ) : (
        <View style={styles.card} testID="quiz-cooldown">
          <View style={styles.row}>
            <Ionicons name="time-outline" size={22} color={palette.warning} />
            <Text style={styles.cardTitle}>Next attempt in {formatCountdown(props.cooldownLeft)}</Text>
          </View>
          <Text style={styles.muted} testID="quiz-next-at">Opens {formatWhen(s.next_eligible_at)}</Text>

          {auth ? (
            auth.usable_now ? (
              <View style={styles.gap} testID="quiz-auth-ready">
                <Text style={styles.ok}>An admin approved an early attempt (until {formatWhen(auth.window_end)}).</Text>
                <Button title="Start approved attempt" icon="checkmark-circle" onPress={() => props.onStart('authorized')}
                  loading={busy === 'authorized'} disabled={!!busy} testID="quiz-start-authorized" />
              </View>
            ) : (
              <Text style={[styles.ok, styles.gapTop]} testID="quiz-auth-scheduled">
                Approved: you can start between {formatWhen(auth.window_start)} and {formatWhen(auth.window_end)}.
              </Text>
            )
          ) : null}

          <View style={styles.divider} />
          <Text style={styles.label}>Force Attempt</Text>
          <Text style={styles.muted}>
            Skip the wait for {s.force_cost} wildcards. They are taken only when the quiz starts. You have{' '}
            <Text style={styles.strong} testID="quiz-wildcards">{s.wildcards}</Text>.
          </Text>
          <View style={styles.gap}>
            <Button title={`Force Attempt (${s.force_cost} wildcards)`} icon="flash" variant="secondary"
              onPress={() => props.onStart('forced')} loading={busy === 'forced'} disabled={!!busy || !s.can_force} testID="quiz-force" />
            {!s.can_force && s.wildcards < s.force_cost ? (
              <Text style={styles.warn} testID="quiz-force-short">You need {s.force_cost - s.wildcards} more wildcard{s.force_cost - s.wildcards === 1 ? '' : 's'}.</Text>
            ) : null}
          </View>
        </View>
      )}

      <Text style={styles.sectionLabel}>Ask an admin</Text>
      <View style={styles.card} testID="quiz-requests">
        {s.pending_request ? (
          <Text style={styles.muted} testID="quiz-request-pending">
            Your request from {formatWhen(s.pending_request.created_at)} is waiting for an admin. You can send a new one after it is decided.
          </Text>
        ) : !s.can_request ? (
          <Text style={styles.muted} testID="quiz-request-blocked">You have an approved attempt. Use it before asking again.</Text>
        ) : props.asking ? (
          <View>
            <TextField label="Why do you need an early attempt? (optional)" value={props.reason} onChangeText={props.onReason}
              maxLength={500} multiline testID="quiz-request-reason" />
            <View style={styles.gap}>
              <Button title="Send request" icon="send" onPress={props.onSend} loading={busy === 'request'} disabled={!!busy} testID="quiz-request-send" />
              <Button title="Cancel" variant="ghost" onPress={props.onCancelAsk} disabled={!!busy} testID="quiz-request-cancel" />
            </View>
          </View>
        ) : (
          <View>
            <Text style={styles.muted}>Ask for permission to take the quiz before the {s.quiz.cooldown_hours}-hour wait ends. One approval allows one attempt.</Text>
            <View style={styles.gap}>
              <Button title="Request an early attempt" variant="secondary" icon="hand-left" onPress={props.onAsk} disabled={!!busy} testID="quiz-request-open" />
            </View>
          </View>
        )}

        {s.requests.length ? (
          <View style={styles.gapTop}>
            {s.requests.map((r) => (
              <View key={r.request_id} style={styles.reqItem} testID={`quiz-request-${r.request_id}`}>
                <View style={styles.rowBetween}>
                  <Text style={styles.label}>{formatWhen(r.created_at)}</Text>
                  <Text style={[styles.pill, PILL[r.status]]} testID={`quiz-request-${r.request_id}-status`}>{REQUEST_LABELS[r.status]}</Text>
                </View>
                {r.reason ? <Text style={styles.muted}>“{r.reason}”</Text> : null}
                {r.decided_at ? (
                  <Text style={styles.caption}>
                    {r.status === 'rejected' ? 'Rejected' : 'Decided'} {formatWhen(r.decided_at)}
                    {r.decision_reason ? `: ${r.decision_reason}` : ''}
                  </Text>
                ) : null}
                {r.window_start && (r.status === 'approved' || r.status === 'expired') ? (
                  <Text style={styles.caption}>Window {formatWhen(r.window_start)} → {formatWhen(r.window_end)}</Text>
                ) : null}
                {r.used_at ? <Text style={styles.caption}>Used {formatWhen(r.used_at)}</Text> : null}
              </View>
            ))}
          </View>
        ) : null}
      </View>
    </View>
  );
}

// ============================================================
// PLAY: one question at a time
// ============================================================

function Play(props: {
  running: Running;
  index: number;
  answers: Record<string, OptionKey>;
  timeLeft: number;
  busy: boolean;
  onPick: (qid: string, key: OptionKey) => void;
  onGo: (i: number) => void;
  onSubmit: () => void;
}) {
  const { running, index, answers } = props;
  const q = running.questions[index];
  const count = running.questions.length;
  const answered = running.questions.filter((x) => answers[x.id]).length;
  const last = index === count - 1;
  const low = props.timeLeft < 120;
  return (
    <View testID="quiz-play">
      <View style={styles.rowBetween}>
        <Text style={styles.label} testID="quiz-progress">Question {index + 1} of {count} · {q.level}</Text>
        <View style={[styles.timer, low && styles.timerLow]}>
          <Ionicons name="timer-outline" size={16} color={low ? palette.danger : palette.textMuted} />
          <Text style={[styles.caption, low && { color: palette.danger }]} testID="quiz-timer">{formatCountdown(props.timeLeft)}</Text>
        </View>
      </View>
      <View style={styles.bar}><View style={[styles.barFill, { width: `${(100 * answered) / count}%` }]} /></View>

      <View style={styles.card}>
        <Text style={styles.question} testID="quiz-question">{q.text}</Text>
        {q.options.map((o) => {
          const picked = answers[q.id] === o.key;
          return (
            <Pressable
              key={o.key}
              onPress={() => props.onPick(q.id, o.key)}
              accessibilityRole="radio"
              accessibilityState={{ selected: picked }}
              accessibilityLabel={`${o.key}. ${o.text}`}
              testID={`quiz-option-${o.key}`}
              style={({ pressed }) => [styles.option, picked && styles.optionPicked, pressed && !picked && styles.optionPressed]}
            >
              <View style={[styles.optionKey, picked && styles.optionKeyPicked]}>
                <Text style={[styles.label, picked && { color: palette.onPrimary }]}>{o.key}</Text>
              </View>
              <Text style={styles.optionText}>{o.text}</Text>
            </Pressable>
          );
        })}
      </View>

      <View style={styles.navRow}>
        <View style={styles.flex}>
          <Button title="Previous" variant="secondary" icon="chevron-back" onPress={() => props.onGo(index - 1)} disabled={index === 0 || props.busy} testID="quiz-prev" />
        </View>
        <View style={styles.flex}>
          {last ? (
            <Button title="Submit" icon="checkmark-done" onPress={props.onSubmit} loading={props.busy} testID="quiz-submit" />
          ) : (
            <Button title="Next" icon="chevron-forward" onPress={() => props.onGo(index + 1)} disabled={props.busy} testID="quiz-next" />
          )}
        </View>
      </View>

      <Text style={[styles.caption, styles.gapTop]}>{answered} of {count} answered · tap a number to jump</Text>
      <View style={styles.jumps}>
        {running.questions.map((x, i) => (
          <Pressable key={x.id} onPress={() => props.onGo(i)} testID={`quiz-jump-${x.id}`}
            accessibilityRole="button" accessibilityLabel={`Question ${i + 1}${answers[x.id] ? ', answered' : ''}`}
            style={[styles.jump, answers[x.id] ? styles.jumpDone : null, i === index && styles.jumpCurrent]}>
            <Text style={[styles.caption, answers[x.id] ? { color: palette.onPrimary } : null]}>{i + 1}</Text>
          </Pressable>
        ))}
      </View>
      {!last && answered === count ? (
        <View style={styles.gapTop}>
          <Button title="Submit" icon="checkmark-done" onPress={props.onSubmit} loading={props.busy} testID="quiz-submit-early" />
        </View>
      ) : null}
    </View>
  );
}

// ============================================================
// RESULT + review
// ============================================================

function Result({ result: r, onDone, onAgain }: { result: QuizAttempt; onDone: () => void; onAgain: () => void }) {
  return (
    <View testID="quiz-result">
      <View style={[styles.card, styles.center]}>
        <Ionicons name="ribbon" size={36} color={palette.primary} />
        <Text style={styles.score} testID="quiz-result-score">{r.score}/{r.total}</Text>
        <Text style={styles.subtitle} testID="quiz-result-percent">{Math.round(r.percent ?? 0)}%</Text>
      </View>
      <View style={styles.grid}>
        <Fact label="Correct" value={String(r.correct)} testID="quiz-result-correct" />
        <Fact label="Incorrect" value={String(r.incorrect)} testID="quiz-result-incorrect" />
        <Fact label="Status" value={r.status === 'completed' ? 'Completed' : r.status} testID="quiz-result-status" />
        <Fact label="Time taken" value={r.duration_s !== null ? formatPlayTime(r.duration_s) : '--'} testID="quiz-result-time" />
      </View>
      <Text style={styles.caption} testID="quiz-result-when">Finished {formatWhen(r.ended_at)}</Text>
      <View style={[styles.navRow, styles.gapTop]}>
        <View style={styles.flex}><Button title="Back to DNA" icon="arrow-back" variant="secondary" onPress={onDone} testID="quiz-done" /></View>
        <View style={styles.flex}><Button title="Quiz page" icon="list" variant="secondary" onPress={onAgain} testID="quiz-home-button" /></View>
      </View>

      {r.review?.length ? (
        <>
          <Text style={styles.sectionLabel}>Review</Text>
          {r.review.map((q, i) => (
            <View key={q.id} style={[styles.card, styles.reviewCard]} testID={`quiz-review-${q.id}`}>
              <View style={styles.row}>
                <Ionicons name={q.correct ? 'checkmark-circle' : 'close-circle'} size={20} color={q.correct ? palette.success : palette.danger} />
                <Text style={styles.label}>{i + 1}. {q.text}</Text>
              </View>
              {!q.correct ? (
                <Text style={[styles.caption, { color: palette.danger }]}>
                  Your answer: {q.your_answer}. {q.options.find((o) => o.key === q.your_answer)?.text ?? ''}
                </Text>
              ) : null}
              <Text style={[styles.caption, { color: palette.success }]}>
                Correct: {q.correct_answer}. {q.options.find((o) => o.key === q.correct_answer)?.text ?? ''}
              </Text>
              <Text style={styles.caption}>{q.explanation}</Text>
            </View>
          ))}
        </>
      ) : null}
    </View>
  );
}

function Fact({ label, value, testID }: { label: string; value: string; testID: string }) {
  return (
    <View style={styles.fact} testID={testID}>
      <Text style={styles.factValue}>{value}</Text>
      <Text style={styles.caption}>{label}</Text>
    </View>
  );
}

const PILL = StyleSheet.create({
  pending: { backgroundColor: palette.warningSoft, color: palette.warning },
  approved: { backgroundColor: palette.successSoft, color: palette.success },
  used: { backgroundColor: palette.primarySoft, color: palette.primary },
  rejected: { backgroundColor: palette.dangerSoft, color: palette.danger },
  expired: { backgroundColor: palette.background, color: palette.textMuted },
});

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: palette.background },
  content: { paddingHorizontal: spacing.xl, paddingTop: spacing.lg, width: '100%', maxWidth: layout.maxContentWidth, alignSelf: 'center' },
  title: { ...typography.title },
  subtitle: { ...typography.bodyMuted, marginTop: spacing.xs, marginBottom: spacing.lg },
  sectionLabel: { ...typography.caption, textTransform: 'uppercase', letterSpacing: 0.6, marginTop: spacing.lg, marginBottom: spacing.sm },
  card: { backgroundColor: palette.surface, borderRadius: radius.lg, borderWidth: 1, borderColor: palette.border, padding: spacing.lg, ...shadow.card },
  center: { alignItems: 'center' },
  cardTitle: { ...typography.subtitle, marginBottom: spacing.xs, flexShrink: 1 },
  muted: { ...typography.bodyMuted },
  caption: { ...typography.caption },
  label: { ...typography.label, flexShrink: 1 },
  strong: { fontWeight: '700', color: palette.text },
  ok: { ...typography.body, color: palette.success },
  warn: { ...typography.caption, color: palette.warning, textAlign: 'center' },
  gap: { gap: spacing.sm, marginTop: spacing.md },
  gapTop: { marginTop: spacing.md },
  row: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  rowBetween: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: spacing.sm },
  divider: { height: 1, backgroundColor: palette.border, marginVertical: spacing.lg },
  reqItem: { borderTopWidth: 1, borderTopColor: palette.border, paddingVertical: spacing.sm, gap: spacing.xxs },
  pill: { ...typography.caption, fontSize: 12, fontWeight: '600', paddingHorizontal: spacing.sm, paddingVertical: 2, borderRadius: radius.pill, overflow: 'hidden' },
  timer: { flexDirection: 'row', alignItems: 'center', gap: spacing.xs, paddingHorizontal: spacing.sm, paddingVertical: 2, borderRadius: radius.pill, backgroundColor: palette.surface, borderWidth: 1, borderColor: palette.border },
  timerLow: { borderColor: palette.dangerBorder, backgroundColor: palette.dangerSoft },
  bar: { height: 6, borderRadius: 3, backgroundColor: palette.border, marginVertical: spacing.md, overflow: 'hidden' },
  barFill: { height: '100%', backgroundColor: palette.primary },
  question: { ...typography.subtitle, marginBottom: spacing.md },
  option: { flexDirection: 'row', alignItems: 'center', gap: spacing.md, borderWidth: 1, borderColor: palette.border, borderRadius: radius.md, padding: spacing.md, marginBottom: spacing.sm, minHeight: layout.minTouchSize },
  optionPicked: { borderColor: palette.primary, backgroundColor: palette.primarySoft },
  optionPressed: { backgroundColor: palette.background },
  optionKey: { width: 30, height: 30, borderRadius: 15, borderWidth: 1, borderColor: palette.borderStrong, alignItems: 'center', justifyContent: 'center' },
  optionKeyPicked: { backgroundColor: palette.primary, borderColor: palette.primary },
  optionText: { ...typography.body, flex: 1 },
  navRow: { flexDirection: 'row', gap: spacing.md, marginTop: spacing.lg },
  flex: { flex: 1 },
  jumps: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs, marginTop: spacing.sm },
  jump: { width: 34, height: 34, borderRadius: 17, borderWidth: 1, borderColor: palette.borderStrong, alignItems: 'center', justifyContent: 'center', backgroundColor: palette.surface },
  jumpDone: { backgroundColor: palette.primary, borderColor: palette.primary },
  jumpCurrent: { borderWidth: 3, borderColor: palette.text },
  score: { ...typography.display, fontSize: 40, lineHeight: 48, marginTop: spacing.sm },
  grid: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between', marginTop: spacing.md },
  fact: { width: '48.5%', backgroundColor: palette.surface, borderRadius: radius.md, borderWidth: 1, borderColor: palette.border, padding: spacing.md, marginBottom: spacing.sm },
  factValue: { ...typography.title },
  reviewCard: { marginBottom: spacing.sm, gap: spacing.xs },
});
