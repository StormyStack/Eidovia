import { Ionicons } from '@expo/vector-icons';
import { useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import { toApiError } from '../services/ApiClient';
import { WildcardService, type WildcardSummary } from '../services/WildcardService';
import { palette, radius, shadow, spacing, typography } from '../theme';

/**
 * The learner's wildcards (total only) and "Ask your teacher for wildcards" with a reason
 * (once every 3 days; the request appears in the admin panel under User Support). Shows the answer.
 */
export function WildcardsCard({ summary, onChanged }: { summary: WildcardSummary | null; onChanged: () => void }) {
  const [open, setOpen] = useState(false);
  const [amount, setAmount] = useState(2);
  const [reason, setReason] = useState('');
  const [sending, setSending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const latest = summary?.requests[0];
  const canAsk = summary ? summary.can_request : true;

  const send = async () => {
    if (reason.trim().length < 5) {
      setMessage('Please write why you need wildcards (at least 5 characters).');
      return;
    }
    setSending(true);
    setMessage(null);
    try {
      await WildcardService.request(amount, reason.trim());
      setOpen(false);
      setReason('');
      onChanged();
    } catch (e) {
      setMessage(toApiError(e).message);
    } finally {
      setSending(false);
    }
  };

  let status: string | null = null;
  if (latest) {
    const day = latest.created_at ? new Date(latest.created_at).toLocaleDateString() : '';
    if (latest.status !== 'resolved') status = `You asked for ${latest.amount} on ${day}. Waiting for your teacher.`;
    else if (latest.granted) status = `Your teacher gave you ${latest.granted} wildcard${latest.granted === 1 ? '' : 's'}.`;
    else status = 'Your teacher answered your request.';
  }

  return (
    <View style={[styles.card, styles.askCard]} testID="ask-wildcards">
      <View style={styles.askHead}>
        <Ionicons name="star" size={20} color="#D97706" />
        <Text style={styles.askTitle}>Wildcards</Text>
        <Text style={styles.total} testID="wildcards-total">{summary ? summary.total : '–'}</Text>
      </View>
      <Text style={styles.askHint}>Use them in the app, e.g. to skip or jump levels in the AR game. Need more? Ask your teacher.</Text>
      {status ? (
        <View style={styles.askStatus} testID="ask-status">
          <Text style={styles.askStatusText}>{status}</Text>
          {latest?.admin_reply ? <Text style={styles.askReply}>“{latest.admin_reply}”</Text> : null}
        </View>
      ) : null}

      {open ? (
        <View testID="ask-form">
          <Text style={styles.askLabel}>How many?</Text>
          <View style={styles.amounts}>
            {[1, 2, 3, 4, 5].map((n) => (
              <Pressable
                key={n}
                onPress={() => setAmount(n)}
                style={[styles.amount, amount === n && styles.amountOn]}
                accessibilityRole="button"
                accessibilityState={{ selected: amount === n }}
                testID={`ask-amount-${n}`}
              >
                <Text style={[styles.amountText, amount === n && styles.amountTextOn]}>{n}</Text>
              </Pressable>
            ))}
          </View>
          <Text style={styles.askLabel}>Why do you need them?</Text>
          <TextInput
            value={reason}
            onChangeText={setReason}
            placeholder="e.g. I'm stuck on the double helix level"
            placeholderTextColor={palette.placeholder}
            multiline
            maxLength={500}
            style={styles.askInput}
            testID="ask-reason"
          />
          {message ? <Text style={styles.askError} testID="ask-error">{message}</Text> : null}
          <View style={styles.askButtons}>
            <Pressable onPress={() => { setOpen(false); setMessage(null); }} style={styles.askCancel} accessibilityRole="button">
              <Text style={styles.askCancelText}>Cancel</Text>
            </Pressable>
            <Pressable onPress={() => void send()} disabled={sending} style={styles.askSend} accessibilityRole="button" testID="ask-send">
              {sending ? <ActivityIndicator color={palette.onPrimary} /> : <Text style={styles.askSendText}>Send request</Text>}
            </Pressable>
          </View>
        </View>
      ) : canAsk ? (
        <Pressable onPress={() => setOpen(true)} style={styles.askOpen} accessibilityRole="button" testID="ask-open">
          <Text style={styles.askOpenText}>Ask your teacher for wildcards</Text>
        </Pressable>
      ) : (
        <Text style={styles.askLater} testID="ask-later">
          {summary?.next_request_at
            ? `You can ask again on ${new Date(summary.next_request_at).toLocaleDateString()}.`
            : 'You can ask again once your teacher has answered.'}
        </Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: palette.surface,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: palette.border,
    padding: spacing.lg,
    ...shadow.card,
  },
  askCard: {},
  askHead: { flexDirection: 'row', alignItems: 'center', gap: spacing.xs, marginBottom: spacing.sm },
  askTitle: { ...typography.subtitle },
  askStatus: { backgroundColor: palette.warningSoft, borderRadius: radius.md, padding: spacing.md, marginBottom: spacing.md },
  askStatusText: { ...typography.label, color: palette.warning },
  askReply: { ...typography.caption, marginTop: spacing.xs, fontStyle: 'italic' },
  askLabel: { ...typography.label, marginBottom: spacing.xs, marginTop: spacing.xs },
  amounts: { flexDirection: 'row', gap: spacing.sm, marginBottom: spacing.sm },
  amount: {
    width: 44, height: 44, borderRadius: 22, borderWidth: 1, borderColor: palette.borderStrong,
    alignItems: 'center', justifyContent: 'center', backgroundColor: palette.surface,
  },
  amountOn: { backgroundColor: '#D97706', borderColor: '#D97706' },
  amountText: { ...typography.label },
  amountTextOn: { color: palette.onPrimary },
  askInput: {
    ...typography.body, minHeight: 80, textAlignVertical: 'top', borderWidth: 1, borderColor: palette.border,
    borderRadius: radius.md, padding: spacing.md, backgroundColor: palette.background,
  },
  askError: { ...typography.caption, color: palette.danger, marginTop: spacing.sm },
  askButtons: { flexDirection: 'row', justifyContent: 'flex-end', gap: spacing.sm, marginTop: spacing.md },
  askCancel: { paddingHorizontal: spacing.lg, paddingVertical: spacing.md },
  askCancelText: { ...typography.label, color: palette.textMuted },
  askSend: { backgroundColor: palette.primary, borderRadius: radius.md, paddingHorizontal: spacing.lg, paddingVertical: spacing.md, minWidth: 130, alignItems: 'center' },
  askSendText: { ...typography.label, color: palette.onPrimary },
  askOpen: { borderWidth: 1, borderColor: '#D97706', borderRadius: radius.md, paddingVertical: spacing.md, alignItems: 'center' },
  askOpenText: { ...typography.label, color: '#B45309' },
  askLater: { ...typography.caption },
  total: { ...typography.title, color: '#B45309', marginLeft: 'auto' },
  askHint: { ...typography.caption, marginBottom: spacing.md },
});
