import { act, fireEvent, screen } from '@testing-library/react-native';

import { ApiClient } from '../../services/ApiClient';
import { useAuthStore } from '../../store/authStore';
import { errorBody, installMockAdapter, type MockHandler } from '../../test-utils/mockAdapter';
import { renderScreen } from '../../test-utils/render';
import { jwtExpiringIn, resetDeviceStorage, secureStoreData } from '../../test-utils/storage';
import { LoginScreen } from '../LoginScreen';

const USER_ID = '3f8a1c2e-5b7d-4e9f-a1b2-c3d4e5f60718';
const initialState = useAuthStore.getState();

function server(handler: MockHandler) {
  return installMockAdapter(ApiClient, handler);
}

async function fillAndSubmit(username: string, password: string) {
  await fireEvent.changeText(screen.getByTestId('login-username'), username);
  await fireEvent.changeText(screen.getByTestId('login-password'), password);
  await fireEvent.press(screen.getByTestId('login-submit'));
}

beforeEach(() => {
  resetDeviceStorage();
  useAuthStore.setState({ ...initialState, isLoading: false }, true);
});

it('renders the form with branding and a link to sign up', async () => {
  await renderScreen(LoginScreen, 'Login');
  expect(screen.getByText('Eidovia')).toBeOnTheScreen();
  expect(screen.getByLabelText('Username')).toBeOnTheScreen();
  expect(screen.getByLabelText('Password')).toBeOnTheScreen();
  expect(screen.getByRole('button', { name: 'Log in' })).toBeOnTheScreen();
});

it('validates required fields without calling the API', async () => {
  const calls = server(() => ({ status: 200, data: {} }));
  await renderScreen(LoginScreen, 'Login');

  await fireEvent.press(screen.getByTestId('login-submit'));

  expect(screen.getByTestId('login-username-error')).toHaveTextContent('Enter your username.');
  expect(screen.getByTestId('login-password-error')).toHaveTextContent('Enter your password.');
  expect(calls).toHaveLength(0);
});

it('clears a field error as soon as the user types', async () => {
  await renderScreen(LoginScreen, 'Login');
  await fireEvent.press(screen.getByTestId('login-submit'));
  await fireEvent.changeText(screen.getByTestId('login-username'), 's');
  expect(screen.queryByTestId('login-username-error')).not.toBeOnTheScreen();
  expect(screen.getByTestId('login-password-error')).toBeOnTheScreen();
});

it('logs in with the trimmed username and signs the user in', async () => {
  const token = jwtExpiringIn(60, USER_ID);
  const calls = server((req) =>
    req.url === '/api/auth/login'
      ? { status: 200, data: { user_id: USER_ID, token, profile: { detail_level: 1, language: 'en' } } }
      : { status: 200, data: { user_id: USER_ID, username: 'shanto', email: null, detail_level: 1, language: 'en', created_at: '' } },
  );
  await renderScreen(LoginScreen, 'Login');

  await fillAndSubmit('  shanto  ', 'Correct-Horse-9');

  expect(calls[0].body).toEqual({ username: 'shanto', password: 'Correct-Horse-9' });
  expect(useAuthStore.getState().isAuthenticated).toBe(true);
  expect(secureStoreData().get('auth_token')).toBe(token);
});

it('shows a loading, disabled button while submitting (no double submit)', async () => {
  let release: () => void = () => undefined;
  const calls = server(
    () =>
      new Promise((resolve) => {
        release = () => resolve({ status: 401, data: errorBody('INVALID_CREDENTIALS', 'Incorrect username or password.') });
      }),
  );
  await renderScreen(LoginScreen, 'Login');
  await fireEvent.changeText(screen.getByTestId('login-username'), 'shanto');
  await fireEvent.changeText(screen.getByTestId('login-password'), 'pw');

  // RNTL v14 awaits the press handler, so start it without awaiting to see the in-flight UI
  const pressing = fireEvent.press(screen.getByTestId('login-submit'));

  expect(await screen.findByText('Logging in…')).toBeOnTheScreen();
  expect(screen.getByTestId('login-submit')).toBeDisabled();
  expect(screen.getByTestId('login-submit-spinner')).toBeOnTheScreen();
  expect(screen.getByTestId('login-username')).toHaveProp('editable', false);

  await fireEvent.press(screen.getByTestId('login-submit')); // ignored while busy
  await act(async () => {
    release();
    await pressing;
  });

  expect(await screen.findByTestId('login-error')).toBeOnTheScreen();
  expect(calls).toHaveLength(1);
  expect(screen.getByTestId('login-submit')).toBeEnabled();
});

it('shows the 401 message and clears the password on wrong credentials', async () => {
  server(() => ({ status: 401, data: errorBody('INVALID_CREDENTIALS', 'Incorrect username or password.') }));
  await renderScreen(LoginScreen, 'Login');

  await fillAndSubmit('shanto', 'wrong-pass');

  expect(await screen.findByTestId('login-error')).toHaveTextContent(/Incorrect username or password./);
  expect(screen.getByTestId('login-password')).toHaveDisplayValue('');
  expect(screen.getByTestId('login-username')).toHaveDisplayValue('shanto');
  expect(screen.getByTestId('login-submit')).toBeEnabled();
  expect(useAuthStore.getState().isAuthenticated).toBe(false);
});

it.each([
  ['network-error', "Can't reach the server"],
  ['timeout', 'took too long'],
] as const)('shows a clear message when the server is unreachable (%s)', async (reply, text) => {
  server(() => reply);
  await renderScreen(LoginScreen, 'Login');

  await fillAndSubmit('shanto', 'pw');

  expect(await screen.findByTestId('login-error')).toHaveTextContent(new RegExp(text));
  expect(screen.getByTestId('login-password')).toHaveDisplayValue('pw'); // kept on network problems
});

it('toggles password visibility', async () => {
  await renderScreen(LoginScreen, 'Login');
  const input = screen.getByTestId('login-password');
  expect(input).toHaveProp('secureTextEntry', true);

  await fireEvent.press(screen.getByRole('button', { name: 'Show password' }));
  expect(screen.getByTestId('login-password')).toHaveProp('secureTextEntry', false);

  await fireEvent.press(screen.getByRole('button', { name: 'Hide password' }));
  expect(screen.getByTestId('login-password')).toHaveProp('secureTextEntry', true);
});

it('shows the session-expired notice and lets the user dismiss it', async () => {
  useAuthStore.setState({ notice: 'Your session has expired. Please log in again.' });
  await renderScreen(LoginScreen, 'Login');

  expect(screen.getByTestId('login-notice')).toHaveTextContent(/Your session has expired. Please log in again./);
  await fireEvent.press(screen.getByRole('button', { name: 'Dismiss message' }));

  expect(screen.queryByTestId('login-notice')).not.toBeOnTheScreen();
  expect(useAuthStore.getState().notice).toBeNull();
});

it('navigates to Sign Up', async () => {
  const { navigation } = await renderScreen(LoginScreen, 'Login');
  await fireEvent.press(screen.getByTestId('go-to-signup'));
  expect(navigation.navigate).toHaveBeenCalledWith('SignUp');
});
