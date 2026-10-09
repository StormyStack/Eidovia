/**
 * Automated version of the manual E2E checklist, against a REAL running Gateway.
 * Skipped unless GATEWAY_E2E_URL is set:
 *
 *   $env:GATEWAY_E2E_URL = "http://127.0.0.1:8000"; npx jest app.gateway.e2e
 *
 * Real App.tsx + React Navigation + services + store; network goes through axios'
 * xhr adapter (as on the phone) via the xhr2 XMLHttpRequest implementation.
 * Modules are require()d (not imported) so XMLHttpRequest exists before axios loads.
 * Each step "relaunches" the app from device storage, like reopening it on a phone.
 */

/* eslint-disable @typescript-eslint/no-require-imports */

const GATEWAY = process.env.GATEWAY_E2E_URL;
if (GATEWAY) (globalThis as { XMLHttpRequest?: unknown }).XMLHttpRequest = require('xhr2');

const rntl = require('@testing-library/react-native') as typeof import('@testing-library/react-native');
const App = (require('../App') as typeof import('../App')).default;
const { useAuthStore } = require('../store/authStore') as typeof import('../store/authStore');
const { ApiClient } = require('../services/ApiClient') as typeof import('../services/ApiClient');
const storage = require('../test-utils/storage') as typeof import('../test-utils/storage');
const { Alert } = require('react-native') as typeof import('react-native');

const describeIfGateway = GATEWAY ? describe : describe.skip;

describeIfGateway('E2E checklist against the real gateway', () => {
  const { fireEvent, act } = rntl;
  // `screen` is a live binding that RNTL replaces on every render: always read rntl.screen
  const initialState = useAuthStore.getState();
  const username = `e2e_${Date.now().toString(36)}`;
  const password = 'E2e-Checklist-123';

  const g = globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean };
  let previousActEnvironment: boolean | undefined;

  beforeAll(() => {
    ApiClient.defaults.baseURL = GATEWAY;
    storage.resetDeviceStorage();
    // Real network I/O resolves outside React's act() scheduler, like on a device. Tell React
    // this is a real environment (RNTL still enables act inside its own render/fireEvent).
    previousActEnvironment = g.IS_REACT_ACT_ENVIRONMENT;
    g.IS_REACT_ACT_ENVIRONMENT = false;
  });

  afterAll(() => {
    g.IS_REACT_ACT_ENVIRONMENT = previousActEnvironment;
  });

  /** "Kill and reopen": all in-memory state is gone; device storage remains. */
  async function launchApp() {
    useAuthStore.setState(initialState, true);
    await rntl.render(<App />);
  }

  async function login(pass: string) {
    await fireEvent.changeText(await rntl.screen.findByTestId('login-username'), username);
    await fireEvent.changeText(rntl.screen.getByTestId('login-password'), pass);
    await fireEvent.press(rntl.screen.getByTestId('login-submit'));
  }

  it('1. sign up → auto-login → Home shows modules', async () => {
    await launchApp();
    await fireEvent.press(await rntl.screen.findByTestId('go-to-signup'));
    await fireEvent.changeText(await rntl.screen.findByTestId('signup-username'), username);
    await fireEvent.changeText(rntl.screen.getByTestId('signup-email'), `${username}@example.com`);
    await fireEvent.changeText(rntl.screen.getByTestId('signup-password'), password);
    await fireEvent.changeText(rntl.screen.getByTestId('signup-confirm'), password);
    await fireEvent.press(rntl.screen.getByTestId('signup-submit'));

    expect(await rntl.screen.findByTestId('home-greeting')).toHaveTextContent(`Hi, ${username}!`);
    expect(await rntl.screen.findByText('Explore the Cell')).toBeOnTheScreen();
    expect(rntl.screen.getByText('Cell Quiz')).toBeOnTheScreen();
  });

  it('2. kill and reopen the app → still logged in', async () => {
    await launchApp();
    expect(await rntl.screen.findByTestId('home-greeting')).toHaveTextContent(`Hi, ${username}!`);
  });

  it('3. open a module → ARGame shows its scene_name', async () => {
    await launchApp();
    await fireEvent.press(await rntl.screen.findByTestId('module-cell-quiz'));
    expect(await rntl.screen.findByTestId('argame-scene-name')).toHaveTextContent('GameScene_CellQuiz');
  });

  it('4. logout → Login, credentials purged', async () => {
    await launchApp();
    const alertSpy = jest.spyOn(Alert, 'alert').mockImplementation(() => undefined);
    try {
      await fireEvent.press(await rntl.screen.findByTestId('logout-button'));
      const buttons = alertSpy.mock.calls[0][2] ?? [];
      await act(async () => buttons.find((b) => b.text === 'Log out')?.onPress?.());

      expect(await rntl.screen.findByTestId('login-screen')).toBeOnTheScreen();
      expect(storage.secureStoreData().size).toBe(0);
    } finally {
      alertSpy.mockRestore();
    }
  });

  it('5. wrong password → error message, stays on Login', async () => {
    await launchApp();
    await login('Not-The-Password-1');
    expect(await rntl.screen.findByTestId('login-error')).toHaveTextContent(/Incorrect username or password/);
    expect(rntl.screen.queryByTestId('home-greeting')).not.toBeOnTheScreen();
  });

  it('6. correct password → Home', async () => {
    await launchApp();
    await login(password);
    expect(await rntl.screen.findByTestId('home-greeting')).toBeOnTheScreen();
  });

  it('7. backend offline → network error on Login', async () => {
    await act(async () => useAuthStore.getState().logout());
    ApiClient.defaults.baseURL = 'http://127.0.0.1:9'; // nothing listens here
    try {
      await launchApp();
      await login(password);
      expect(await rntl.screen.findByTestId('login-error')).toHaveTextContent(/Can't reach the server/);
    } finally {
      ApiClient.defaults.baseURL = GATEWAY;
    }
  });
});
