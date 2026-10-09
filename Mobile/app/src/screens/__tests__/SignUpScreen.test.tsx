import { fireEvent, screen } from '@testing-library/react-native';

import { ApiClient } from '../../services/ApiClient';
import { useAuthStore } from '../../store/authStore';
import { errorBody, installMockAdapter, type MockHandler } from '../../test-utils/mockAdapter';
import { renderScreen } from '../../test-utils/render';
import { jwtExpiringIn, resetDeviceStorage } from '../../test-utils/storage';
import { SignUpScreen } from '../SignUpScreen';

const USER_ID = '3f8a1c2e-5b7d-4e9f-a1b2-c3d4e5f60718';
const initialState = useAuthStore.getState();
const VALID = { username: 'shanto', email: 'shanto@example.com', password: 'Correct-Horse-9', confirm: 'Correct-Horse-9' };

function server(handler: MockHandler) {
  return installMockAdapter(ApiClient, handler);
}

async function fill(values: Partial<typeof VALID>) {
  const v = { ...VALID, ...values };
  await fireEvent.changeText(screen.getByTestId('signup-username'), v.username);
  await fireEvent.changeText(screen.getByTestId('signup-email'), v.email);
  await fireEvent.changeText(screen.getByTestId('signup-password'), v.password);
  await fireEvent.changeText(screen.getByTestId('signup-confirm'), v.confirm);
}

async function submit() {
  await fireEvent.press(screen.getByTestId('signup-submit'));
}

beforeEach(() => {
  resetDeviceStorage();
  useAuthStore.setState({ ...initialState, isLoading: false }, true);
});

it('shows every required-field error on an empty submit and calls nothing', async () => {
  const calls = server(() => ({ status: 201, data: {} }));
  await renderScreen(SignUpScreen, 'SignUp');

  await submit();

  expect(screen.getByTestId('signup-username-error')).toHaveTextContent('Enter a username.');
  expect(screen.getByTestId('signup-email-error')).toHaveTextContent('Enter your email address.');
  expect(screen.getByTestId('signup-password-error')).toHaveTextContent('Enter a password.');
  expect(screen.getByTestId('signup-confirm-error')).toHaveTextContent('Re-enter your password.');
  expect(calls).toHaveLength(0);
});

it.each([
  [{ username: 'ab' }, 'signup-username-error', 'Username must be 3 to 32 characters.'],
  [{ username: 'bad name!' }, 'signup-username-error', 'Use only letters, numbers'],
  [{ email: 'not-an-email' }, 'signup-email-error', 'Enter a valid email address.'],
  [{ password: 'short', confirm: 'short' }, 'signup-password-error', 'Password must be at least 8 characters.'],
  [{ confirm: 'Different-Pass-1' }, 'signup-confirm-error', 'Passwords do not match.'],
])('validates %j', async (values, errorId, message) => {
  const calls = server(() => ({ status: 201, data: {} }));
  await renderScreen(SignUpScreen, 'SignUp');
  await fill(values);
  await submit();
  expect(screen.getByTestId(errorId)).toHaveTextContent(new RegExp(message.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
  expect(calls).toHaveLength(0);
});

it('creates the account (trimmed values, no confirm field sent) and auto-logs in', async () => {
  const token = jwtExpiringIn(60, USER_ID);
  const calls = server(() => ({ status: 201, data: { user_id: USER_ID, token, profile: { detail_level: 1, language: 'en' } } }));
  await renderScreen(SignUpScreen, 'SignUp');

  await fill({ username: '  shanto ', email: ' Shanto@Example.com ' });
  await submit();

  expect(calls).toHaveLength(1);
  expect(calls[0]).toMatchObject({ method: 'POST', url: '/api/auth/register' });
  expect(calls[0].body).toEqual({ username: 'shanto', email: 'Shanto@Example.com', password: 'Correct-Horse-9' });
  expect(useAuthStore.getState()).toMatchObject({ isAuthenticated: true, profile: { username: 'shanto', email: 'shanto@example.com' } });
});

it.each([
  ['USERNAME_TAKEN', 'username', 'This username is already taken.', 'signup-username-error'],
  ['EMAIL_TAKEN', 'email', 'An account with this email already exists.', 'signup-email-error'],
])('shows 409 %s under the right field', async (code, field, message, errorId) => {
  server(() => ({ status: 409, data: errorBody(code, message, { [field]: message }) }));
  await renderScreen(SignUpScreen, 'SignUp');

  await fill({});
  await submit();

  expect(await screen.findByTestId(errorId)).toHaveTextContent(message);
  expect(screen.queryByTestId('signup-error')).not.toBeOnTheScreen();
  expect(screen.getByTestId('signup-submit')).toBeEnabled();
  expect(useAuthStore.getState().isAuthenticated).toBe(false);
});

it('maps server 400 field errors onto the form', async () => {
  server(() => ({ status: 400, data: errorBody('VALIDATION_ERROR', 'Please fix the highlighted fields.', { password: 'Password must be at most 72 characters.' }) }));
  await renderScreen(SignUpScreen, 'SignUp');
  await fill({});
  await submit();
  expect(await screen.findByTestId('signup-password-error')).toHaveTextContent('Password must be at most 72 characters.');
});

it('shows network problems in a banner', async () => {
  server(() => 'network-error');
  await renderScreen(SignUpScreen, 'SignUp');
  await fill({});
  await submit();
  expect(await screen.findByTestId('signup-error')).toHaveTextContent(/Can't reach the server/);
});

it('links back to Login', async () => {
  const { navigation } = await renderScreen(SignUpScreen, 'SignUp');
  await fireEvent.press(screen.getByTestId('go-to-login'));
  expect(navigation.goBack).toHaveBeenCalled();

  navigation.canGoBack.mockReturnValue(false);
  await fireEvent.press(screen.getByTestId('go-to-login'));
  expect(navigation.navigate).toHaveBeenCalledWith('Login');
});

it('has show/hide toggles on both password fields', async () => {
  await renderScreen(SignUpScreen, 'SignUp');
  expect(screen.getAllByRole('button', { name: 'Show password' })).toHaveLength(2);
});
