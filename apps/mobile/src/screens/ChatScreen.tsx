/**
 * ChatScreen — conversational interface connected to the AI service via the Gateway.
 *
 * Architecture:
 *   Mobile → POST /api/chat (Gateway :8000) → AI service (:8001)
 *
 * Uses ScrollView + map (not FlatList) so every message is always in the
 * React tree — required for RNTL tests and fine for chat (bounded message count).
 */

import { Ionicons } from '@expo/vector-icons';
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import type { ScreenProps } from '../navigation/types';
import { AiService, type ChatMessage } from '../services/AiService';
import { useAuthStore } from '../store/authStore';
import { layout, palette, radius, shadow, spacing, typography } from '../theme';

// ── Stable session ID for this conversation ──
function makeSessionId(): string {
  return `session_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`;
}

let _msgCounter = 0;
function nextId(): string {
  return `msg_${Date.now()}_${++_msgCounter}`;
}

export function ChatScreen({ route }: ScreenProps<'Chat'>) {
  const module_id = route.params?.module_id ?? null;
  const userId = useAuthStore((s) => s.user_id);

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);

  const sessionId = useRef(makeSessionId());
  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<ScrollView>(null);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  // Log content_viewed on open
  useEffect(() => {
    if (!userId) return;
    void AiService.logEvent({
      session_id: sessionId.current,
      event_type: 'content_viewed',
      payload: { content_id: 'chat_screen', ...(module_id ? { module_id } : {}) },
      client_timestamp: new Date().toISOString(),
    });
  }, [userId, module_id]);

  const appendMessage = useCallback((msg: ChatMessage) => {
    setMessages((prev) => [...prev, msg]);
    setTimeout(() => scrollRef.current?.scrollToEnd({ animated: true }), 80);
  }, []);

  const sendMessage = useCallback(async () => {
    const text = input.trim();
    if (!text || sending) return;

    setInput('');
    setSending(true);

    const userMsg: ChatMessage = {
      id: nextId(),
      role: 'user',
      text,
      timestamp: new Date().toISOString(),
    };
    appendMessage(userMsg);

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const response = await AiService.chat(
        { question: text, session_id: sessionId.current, module_id },
        controller.signal,
      );
      if (controller.signal.aborted) return;

      appendMessage({
        id: nextId(),
        role: 'assistant',
        text: response.answer,
        timestamp: new Date().toISOString(),
      });

      void AiService.logEvent({
        session_id: sessionId.current,
        event_type: 'hint_requested',
        payload: { hint_type: 'chat', is_on_topic: response.is_on_topic, decision_id: response.decision_id },
        client_timestamp: new Date().toISOString(),
      });
    } catch (error: unknown) {
      if (controller.signal.aborted) return;
      const message =
        error instanceof Error ? error.message : 'Something went wrong. Please try again.';
      appendMessage({
        id: nextId(),
        role: 'assistant',
        text: `⚠️ ${message}`,
        timestamp: new Date().toISOString(),
      });
    } finally {
      if (!controller.signal.aborted) setSending(false);
    }
  }, [input, sending, module_id, appendMessage]);

  const insets = useSafeAreaInsets();
  const isEmpty = messages.length === 0;

  return (
    <KeyboardAvoidingView
      style={styles.root}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
      keyboardVerticalOffset={Platform.OS === 'ios' ? 90 : 0}
    >
      {/* Message list — ScrollView + map so every node is always in the tree */}
      <ScrollView
        ref={scrollRef}
        style={styles.scroll}
        contentContainerStyle={[styles.listContent, { paddingBottom: spacing.md }]}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
        testID="chat-message-list"
      >
        {isEmpty ? (
          <View style={styles.emptyContainer}>
            <View style={styles.emptyIcon}>
              <Ionicons name="sparkles" size={32} color={palette.primary} />
            </View>
            <Text style={styles.emptyTitle}>Ask me anything!</Text>
            <Text style={styles.emptySubtitle}>
              {module_id
                ? 'Ask questions about this AR module.'
                : 'Ask questions about biology, AR modules, or anything you are learning.'}
            </Text>
          </View>
        ) : (
          messages.map((item) => {
            const isUser = item.role === 'user';
            return (
              <View
                key={item.id}
                style={[styles.bubbleRow, isUser ? styles.bubbleRowUser : styles.bubbleRowAssistant]}
                testID={`chat-bubble-${item.role}`}
              >
                {!isUser && (
                  <View style={styles.avatar}>
                    <Ionicons name="sparkles" size={16} color={palette.onPrimary} />
                  </View>
                )}
                <View style={[styles.bubble, isUser ? styles.bubbleUser : styles.bubbleAssistant]}>
                  <Text style={isUser ? styles.bubbleTextUser : styles.bubbleTextAssistant}>
                    {item.text}
                  </Text>
                </View>
              </View>
            );
          })
        )}
      </ScrollView>

      {/* Input bar */}
      <View style={[styles.inputBar, { paddingBottom: insets.bottom + spacing.sm }]}>
        <TextInput
          style={styles.textInput}
          value={input}
          onChangeText={setInput}
          placeholder="Type a message…"
          placeholderTextColor={palette.placeholder}
          multiline
          maxLength={500}
          returnKeyType="send"
          blurOnSubmit={false}
          onSubmitEditing={sendMessage}
          editable={!sending}
          accessibilityLabel="Chat message input"
          testID="chat-input"
        />
        <Pressable
          onPress={sendMessage}
          disabled={!input.trim() || sending}
          accessibilityRole="button"
          accessibilityLabel="Send message"
          accessibilityState={{ disabled: !input.trim() || sending }}
          testID="chat-send"
          style={[
            styles.sendButton,
            (!input.trim() || sending) && styles.sendButtonDisabled,
          ]}
        >
          {sending ? (
            <ActivityIndicator color={palette.onPrimary} size="small" testID="chat-send-spinner" />
          ) : (
            <Ionicons name="send" size={18} color={palette.onPrimary} />
          )}
        </Pressable>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: palette.background },
  scroll: { flex: 1 },
  listContent: {
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.lg,
    flexGrow: 1,
    maxWidth: layout.maxContentWidth,
    alignSelf: 'center',
    width: '100%',
  },

  // Empty state
  emptyContainer: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: spacing.xxxl,
    paddingHorizontal: spacing.xl,
  },
  emptyIcon: {
    width: 64,
    height: 64,
    borderRadius: 32,
    backgroundColor: palette.primarySoft,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: spacing.lg,
  },
  emptyTitle: { ...typography.subtitle, textAlign: 'center', marginBottom: spacing.xs },
  emptySubtitle: { ...typography.bodyMuted, textAlign: 'center' },

  // Bubbles
  bubbleRow: { flexDirection: 'row', marginBottom: spacing.sm, alignItems: 'flex-end' },
  bubbleRowUser: { justifyContent: 'flex-end' },
  bubbleRowAssistant: { justifyContent: 'flex-start' },

  avatar: {
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: palette.primary,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: spacing.xs,
    flexShrink: 0,
  },

  bubble: {
    maxWidth: '80%',
    borderRadius: radius.lg,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    ...shadow.card,
  },
  bubbleUser: { backgroundColor: palette.primary, borderBottomRightRadius: radius.sm },
  bubbleAssistant: { backgroundColor: palette.surface, borderBottomLeftRadius: radius.sm },
  bubbleTextUser: { ...typography.body, color: palette.onPrimary, lineHeight: 22 },
  bubbleTextAssistant: { ...typography.body, color: palette.text, lineHeight: 22 },

  // Input bar
  inputBar: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.sm,
    backgroundColor: palette.surface,
    borderTopWidth: 1,
    borderTopColor: palette.border,
    gap: spacing.sm,
    maxWidth: layout.maxContentWidth,
    alignSelf: 'center',
    width: '100%',
  },
  textInput: {
    flex: 1,
    minHeight: layout.minTouchSize,
    maxHeight: 120,
    borderWidth: 1,
    borderColor: palette.borderStrong,
    borderRadius: radius.md,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    backgroundColor: palette.background,
    fontSize: 16,
    color: palette.text,
  },
  sendButton: {
    width: layout.minTouchSize,
    height: layout.minTouchSize,
    borderRadius: radius.md,
    backgroundColor: palette.primary,
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  sendButtonDisabled: { opacity: 0.45 },
  sendButtonPressed: { backgroundColor: palette.primaryPressed },
});
