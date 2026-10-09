import { act, fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import type { ReactElement } from 'react';
import { Alert } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { ApiClient } from '../../services/ApiClient';
import type { ModuleSummary } from '../../services/types';
import { useAuthStore } from '../../store/authStore';
import { errorBody, installMockAdapter, type MockHandler, type MockReply } from '../../test-utils/mockAdapter';
import { renderScreen } from '../../test-utils/render';
import { jwtExpiringIn, resetDeviceStorage } from '../../test-utils/storage';
import { HomeScreen } from '../HomeScreen';

const USER_ID = '3f8a1c2e-5b7d-4e9f-a1b2-c3d4e5f60718';
const initialState = useAuthStore.getState();

const MODULES: ModuleSummary[] = [
  { module_id: 'cell-explore', title: 'Explore the Cell', description: 'Tap organelles.', difficulty: 1, thumbnail_url: null },
  { module_id: 'cell-quiz', title: 'Cell Quiz', description: 'Test yourself.', difficulty: 3, thumbnail_url: 'https://cdn.example.com/q.png' },
];
const CONFIG = { module_id: 'cell-quiz', scene_name: 'GameScene_CellQuiz', cdn_bundle_url: 'https://cdn.example.com/bundles/cell-quiz', difficulty: 3, config: {} };

function server(handler: MockHandler) {
  return installMockAdapter(ApiClient, handler);
}

function routes(map: Record<string, MockReply | (() => MockReply | Promise<MockReply>)>): MockHandler {
  return (req) => {
    const reply = map[req.url];
    // Silently accept fire-and-forget AI event logs so they don't pollute test output
    if (!reply && req.url === '/api/events') return { status: 200, data: {} };
    if (!reply) return { status: 404, data: errorBody('NOT_FOUND', 'Not found') };
    return typeof reply === 'function' ? reply() : reply;
  };
}

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

it('greets the user and lists modules after a loading state', async () => {
  let release: () => void = () => undefined;
  server(
    routes({
      '/api/modules': () =>
        new Promise((resolve) => {
          release = () => resolve({ status: 200, data: MODULES });
        }),
    }),
  );
  await renderScreen(HomeScreen, 'Home');

  expect(screen.getByTestId('home-greeting')).toHaveTextContent('Hi, Shanto!');
  expect(screen.getByTestId('home-loading')).toBeOnTheScreen();

  await act(async () => release());

  expect(await screen.findByText('Explore the Cell')).toBeOnTheScreen();
  expect(screen.getByText('Cell Quiz')).toBeOnTheScreen();
  expect(screen.getByText('2 modules')).toBeOnTheScreen();
  expect(screen.getByText('Beginner')).toBeOnTheScreen();
  expect(screen.getByText('Advanced')).toBeOnTheScreen();
  expect(screen.queryByTestId('home-loading')).not.toBeOnTheScreen();
});

it('falls back to a friendly greeting when the username is unknown', async () => {
  useAuthStore.setState({ profile: { detail_level: 1, language: 'en' } });
  server(routes({ '/api/modules': { status: 200, data: [] } }));
  await renderScreen(HomeScreen, 'Home');
  expect(screen.getByTestId('home-greeting')).toHaveTextContent('Hi there!');
});

it('shows the empty state when there are no modules', async () => {
  server(routes({ '/api/modules': { status: 200, data: [] } }));
  await renderScreen(HomeScreen, 'Home');
  expect(await screen.findByTestId('home-empty')).toHaveTextContent(/No modules yet/);
});

it('shows an error with Retry, and Retry loads the list', async () => {
  let fail = true;
  server(routes({ '/api/modules': () => (fail ? 'network-error' : { status: 200, data: MODULES }) }));
  await renderScreen(HomeScreen, 'Home');

  expect(await screen.findByTestId('home-error')).toHaveTextContent(/Can't reach the server/);

  fail = false;
  await fireEvent.press(screen.getByRole('button', { name: 'Try again' }));

  expect(await screen.findByText('Explore the Cell')).toBeOnTheScreen();
  expect(screen.queryByTestId('home-error')).not.toBeOnTheScreen();
});

it('pull-to-refresh reloads the list', async () => {
  let list: ModuleSummary[] = [MODULES[0]];
  const calls = server(routes({ '/api/modules': () => ({ status: 200, data: list }) }));
  await renderScreen(HomeScreen, 'Home');
  expect(await screen.findByText('Explore the Cell')).toBeOnTheScreen();

  list = MODULES;
  await act(() => screen.getByTestId('home-list').props.refreshControl.props.onRefresh());

  expect(await screen.findByText('Cell Quiz')).toBeOnTheScreen();
  expect(calls.filter((c) => c.url === '/api/modules')).toHaveLength(2);
});

it('a failed refresh keeps the list and shows a dismissible banner', async () => {
  let fail = false;
  server(routes({ '/api/modules': () => (fail ? 'timeout' : { status: 200, data: MODULES }) }));
  await renderScreen(HomeScreen, 'Home');
  expect(await screen.findByText('Explore the Cell')).toBeOnTheScreen();

  fail = true;
  await act(() => screen.getByTestId('home-list').props.refreshControl.props.onRefresh());

  expect(await screen.findByTestId('home-refresh-error')).toHaveTextContent(/Couldn't refresh/);
  expect(screen.getByText('Explore the Cell')).toBeOnTheScreen();
  await fireEvent.press(screen.getByRole('button', { name: 'Dismiss message' }));
  expect(screen.queryByTestId('home-refresh-error')).not.toBeOnTheScreen();
});

it('tapping a module fetches its config and opens ARGame with it', async () => {
  const calls = server(routes({ '/api/modules': { status: 200, data: MODULES }, '/api/modules/cell-quiz/config': { status: 200, data: CONFIG } }));
  const { navigation } = await renderScreen(HomeScreen, 'Home');

  await fireEvent.press(await screen.findByTestId('module-cell-quiz'));

  await waitFor(() => expect(navigation.navigate).toHaveBeenCalledWith('ARGame', { config: CONFIG, title: 'Cell Quiz' }));
  expect(calls.find((c) => c.url === '/api/modules/cell-quiz/config')?.authorization).toMatch(/^Bearer /);
});

it('shows a clear message if the module no longer exists', async () => {
  server(routes({ '/api/modules': { status: 200, data: MODULES }, '/api/modules/cell-quiz/config': { status: 404, data: errorBody('MODULE_NOT_FOUND', 'gone') } }));
  const { navigation } = await renderScreen(HomeScreen, 'Home');

  await fireEvent.press(await screen.findByTestId('module-cell-quiz'));

  expect(await screen.findByTestId('home-action-error')).toHaveTextContent(/no longer available/);
  expect(navigation.navigate).not.toHaveBeenCalled();
});

it('shows network errors when opening a module', async () => {
  server(routes({ '/api/modules': { status: 200, data: MODULES }, '/api/modules/cell-quiz/config': 'network-error' }));
  await renderScreen(HomeScreen, 'Home');
  await fireEvent.press(await screen.findByTestId('module-cell-quiz'));
  expect(await screen.findByTestId('home-action-error')).toHaveTextContent(/Can't reach the server/);
});

it('a 401 while loading signs the user out instead of showing an error', async () => {
  server(routes({ '/api/modules': { status: 401, data: errorBody('TOKEN_EXPIRED', 'Your session has expired. Please log in again.') } }));
  await renderScreen(HomeScreen, 'Home');

  await waitFor(() => expect(useAuthStore.getState().isAuthenticated).toBe(false));
  expect(useAuthStore.getState().notice).toBe('Your session has expired. Please log in again.');
  expect(screen.queryByTestId('home-error')).not.toBeOnTheScreen();
});

it('the header Log out button asks for confirmation, then logs out', async () => {
  server(routes({ '/api/modules': { status: 200, data: MODULES } }));
  const alertSpy = jest.spyOn(Alert, 'alert').mockImplementation(() => undefined);
  const { navigation } = await renderScreen(HomeScreen, 'Home');

  const headerRight = navigation.setOptions.mock.calls.at(-1)[0].headerRight as () => ReactElement;
  await render(<SafeAreaProvider>{headerRight()}</SafeAreaProvider>);
  await fireEvent.press(screen.getByTestId('logout-button'));

  expect(alertSpy).toHaveBeenCalledWith('Log out?', expect.any(String), expect.any(Array));
  const buttons = alertSpy.mock.calls[0][2] as { text: string; onPress?: () => void }[];
  expect(buttons.map((b) => b.text)).toEqual(['Cancel', 'Log out']);

  await act(async () => buttons[1].onPress?.());
  await waitFor(() => expect(useAuthStore.getState().isAuthenticated).toBe(false));
});
