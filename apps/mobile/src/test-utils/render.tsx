/** Helpers for rendering single screens without a real navigator. */

import { render } from '@testing-library/react-native';
import type { ComponentType } from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import type { RootStackParamList } from '../navigation/types';

export function fakeNavigation() {
  return {
    navigate: jest.fn(),
    goBack: jest.fn(),
    canGoBack: jest.fn(() => true),
    setOptions: jest.fn(),
    replace: jest.fn(),
    addListener: jest.fn(() => jest.fn()),
  };
}

export type FakeNavigation = ReturnType<typeof fakeNavigation>;

export async function renderScreen<Name extends keyof RootStackParamList>(
  Screen: ComponentType<any>,
  name: Name,
  params?: RootStackParamList[Name],
) {
  const navigation = fakeNavigation();
  const route = { key: `${name}-test`, name, params };
  const result = await render(
    <SafeAreaProvider>
      <Screen navigation={navigation} route={route} />
    </SafeAreaProvider>,
  );
  return { ...result, navigation };
}
