/**
 * AiService — Chat and event logging via the Gateway proxy (POST /api/chat, POST /api/events).
 *
 * The mobile app NEVER talks directly to the AI service on port 8001.
 * All requests go to the Gateway (EXPO_PUBLIC_API_URL / port 8000), which
 * validates the JWT and forwards to the AI service internally.
 *
 * The Gateway injects the authenticated user_id, so we do not send it here.
 */

import { ApiClient, toApiError } from './ApiClient';

// ============================================================
// TYPES
// ============================================================

export interface ChatMessage {
  /** Unique client-side ID for the message (e.g. uuid or Date.now()). */
  id: string;
  role: 'user' | 'assistant';
  text: string;
  /** ISO timestamp string. */
  timestamp: string;
  /** True if this answer came from the Redis cache. */
  cached?: boolean;
}

export interface ChatRequest {
  question: string;
  session_id?: string | null;
  module_id?: string | null;
}

export interface ChatResponse {
  answer: string;
  is_on_topic: boolean;
  max_similarity: number;
  num_documents: number;
  latency_ms: number;
  decision_id?: string | null;
  cached: boolean;
}

export type EventType =
  | 'quiz_answer'
  | 'ar_interaction'
  | 'hint_requested'
  | 'content_skip'
  | 'content_viewed';

export interface EventRequest {
  session_id: string;
  event_type: EventType | string;
  payload?: Record<string, unknown> | null;
  client_timestamp?: string | null;
}

// ============================================================
// SERVICE
// ============================================================

export const AiService = {
  /**
   * Send a chat question to the Gateway → AI service.
   * Rejects with ApiError on network/server failures.
   */
  async chat(request: ChatRequest, signal?: AbortSignal): Promise<ChatResponse> {
    try {
      const { data } = await ApiClient.post<ChatResponse>('/api/chat', request, { signal });
      return data;
    } catch (error) {
      throw toApiError(error);
    }
  },

  /**
   * Log a learner interaction event.  Fire-and-forget: never rejects.
   */
  async logEvent(event: EventRequest): Promise<void> {
    try {
      await ApiClient.post('/api/events', event);
    } catch {
      // Intentionally swallowed — event logging must not disrupt the UX.
    }
  },
};
