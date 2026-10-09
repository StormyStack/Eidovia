/**
 * ChatScreen unit tests.
 * Network is faked via the mock adapter; storage mocks are in jest.setup.ts.
 *
 * ChatScreen uses ScrollView + map (not FlatList) so every message node is
 * always in the React tree — RNTL can find them without any special setup.
 */

import { fireEvent, screen, waitFor } from '@testing-library/react-native';

import { ApiClient } from '../../services/ApiClient';
import { useAuthStore } from '../../store/authStore';
import { errorBody, installMockAdapter } from '../../test-utils/mockAdapter';
import { renderScreen } from '../../test-utils/render';
import { jwtExpiringIn, resetDeviceStorage } from '../../test-utils/storage';
import { ChatScreen } from '../ChatScreen';

const USER_ID = '3f8a1c2e-5b7d-4e9f-a1b2-c3d4e5f60718';
const initialState = useAuthStore.getState();

const CHAT_RESPONSE = {
  answer: 'Photosynthesis converts light into glucose.',
  is_on_topic: true,
  max_similarity: 0.92,
  num_documents: 3,
  latency_ms: 120,
  decision_id: 'dec-001',
  cached: false,
};

const CACHED_RESPONSE = { ...CHAT_RESPONSE, answer: 'Cached answer.', cached: true };

beforeEach(() => {
  resetDeviceStorage();
  jest.restoreAllMocks();
  useAuthStore.setState(
    {
      ...initialState,
      isLoading: false,
      isAuthenticated: true,
      user_id: USER_ID,
      token: jwtExpiringIn(60, USER_ID),
      profile: { detail_level: 1, language: 'en', username: 'Shanto' },
    },
    true,
  );
});

it('renders the empty state with a prompt', async () => {
  installMockAdapter(ApiClient, () => ({ status: 200, data: CHAT_RESPONSE }));
  await renderScreen(ChatScreen, 'Chat');

  expect(screen.getByText('Ask me anything!')).toBeOnTheScreen();
  expect(screen.getByTestId('chat-input')).toBeOnTheScreen();
  expect(screen.getByTestId('chat-send')).toBeOnTheScreen();
});

it('send button is disabled when input is empty', async () => {
  installMockAdapter(ApiClient, () => ({ status: 200, data: CHAT_RESPONSE }));
  await renderScreen(ChatScreen, 'Chat');

  const send = screen.getByTestId('chat-send');
  expect(send.props.accessibilityState?.disabled).toBe(true);
});

it('send button becomes enabled when text is typed', async () => {
  installMockAdapter(ApiClient, () => ({ status: 200, data: CHAT_RESPONSE }));
  await renderScreen(ChatScreen, 'Chat');

  fireEvent.changeText(screen.getByTestId('chat-input'), 'Hello');
  expect(screen.getByTestId('chat-send').props.accessibilityState?.disabled).toBe(false);
});

it('sends a message and displays the user bubble and AI response', async () => {
  installMockAdapter(ApiClient, (req) => {
    if (req.url === '/api/chat') return { status: 200, data: CHAT_RESPONSE };
    return { status: 200, data: {} };
  });
  await renderScreen(ChatScreen, 'Chat');

  fireEvent.changeText(screen.getByTestId('chat-input'), 'What is photosynthesis?');
  fireEvent.press(screen.getByTestId('chat-send'));

  // User bubble appears immediately
  expect(await screen.findByText('What is photosynthesis?')).toBeOnTheScreen();
  // AI response arrives after the mock resolves
  expect(await screen.findByText('Photosynthesis converts light into glucose.')).toBeOnTheScreen();
});

it('clears the input after sending', async () => {
  installMockAdapter(ApiClient, (req) => {
    if (req.url === '/api/chat') return { status: 200, data: CHAT_RESPONSE };
    return { status: 200, data: {} };
  });
  await renderScreen(ChatScreen, 'Chat');

  fireEvent.changeText(screen.getByTestId('chat-input'), 'Tell me something');
  fireEvent.press(screen.getByTestId('chat-send'));

  await waitFor(() =>
    expect(screen.getByTestId('chat-input').props.value).toBe(''),
  );
});

it('shows a ⚡ cached badge when the response is cached', async () => {
  installMockAdapter(ApiClient, (req) => {
    if (req.url === '/api/chat') return { status: 200, data: CACHED_RESPONSE };
    return { status: 200, data: {} };
  });
  await renderScreen(ChatScreen, 'Chat');

  fireEvent.changeText(screen.getByTestId('chat-input'), 'What is mitosis?');
  fireEvent.press(screen.getByTestId('chat-send'));

  expect(await screen.findByText('⚡ cached')).toBeOnTheScreen();
});

it('shows an error bubble when the AI service is unavailable', async () => {
  installMockAdapter(ApiClient, (req) => {
    if (req.url === '/api/chat')
      return {
        status: 503,
        data: errorBody('AI_SERVICE_UNAVAILABLE', 'The AI service is temporarily unavailable. Please try again in a moment.'),
      };
    return { status: 200, data: {} };
  });
  await renderScreen(ChatScreen, 'Chat');

  fireEvent.changeText(screen.getByTestId('chat-input'), 'Hello?');
  fireEvent.press(screen.getByTestId('chat-send'));

  expect(await screen.findByText(/temporarily unavailable/)).toBeOnTheScreen();
});

it('shows a network error bubble when offline', async () => {
  installMockAdapter(ApiClient, (req) => {
    if (req.url === '/api/chat') return 'network-error';
    return { status: 200, data: {} };
  });
  await renderScreen(ChatScreen, 'Chat');

  fireEvent.changeText(screen.getByTestId('chat-input'), 'Hello?');
  fireEvent.press(screen.getByTestId('chat-send'));

  expect(await screen.findByText(/Can't reach the server/)).toBeOnTheScreen();
});
