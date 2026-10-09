/**
 * Root navigation (PDF §1: "App.tsx — Root navigation (React Navigation stack)").
 *
 * 1. While authStore.restoreSession() runs → SplashScreen.
 * 2. Signed out → Login, SignUp.   Signed in → Home, ARGame.
 * Signing in/out swaps the screen set; React Navigation moves to the right screen
 * automatically (never navigate to Home manually after login).
 */

import { DefaultTheme, NavigationContainer, type Theme as NavigationTheme } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { StatusBar } from 'expo-status-bar';
import { useEffect } from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import type { RootStackParamList } from './navigation/types';
import { ARGameScreen } from './screens/ARGameScreen';
import { ChatScreen } from './screens/ChatScreen';
import { HomeScreen } from './screens/HomeScreen';
import { LoginScreen } from './screens/LoginScreen';
import { SignUpScreen } from './screens/SignUpScreen';
import { SplashScreen } from './screens/SplashScreen';
import { useAuthStore } from './store/authStore';
import { brand, palette } from './theme';

const Stack = createNativeStackNavigator<RootStackParamList>();

const navigationTheme: NavigationTheme = {
  ...DefaultTheme,
  colors: {
    ...DefaultTheme.colors,
    primary: palette.primary,
    background: palette.background,
    card: palette.surface,
    text: palette.text,
    border: palette.border,
  },
};

export default function App() {
  const isLoading = useAuthStore((s) => s.isLoading);
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const restoreSession = useAuthStore((s) => s.restoreSession);

  useEffect(() => {
    void restoreSession();
  }, [restoreSession]);

  return (
    <SafeAreaProvider>
      <StatusBar style="dark" />
      {isLoading ? (
        <SplashScreen />
      ) : (
        <NavigationContainer theme={navigationTheme}>
          <Stack.Navigator
            screenOptions={{
              headerTitleStyle: { fontWeight: '700' },
              headerShadowVisible: false,
              headerTintColor: palette.primary,
              headerStyle: { backgroundColor: palette.background },
              headerTitleAlign: 'center',
              contentStyle: { backgroundColor: palette.background },
              headerBackButtonDisplayMode: 'minimal',
            }}
          >
            {isAuthenticated ? (
              <Stack.Group>
                <Stack.Screen name="Home" component={HomeScreen} options={{ title: brand.name }} />
                <Stack.Screen name="ARGame" component={ARGameScreen} options={({ route }) => ({ title: route.params.title })} />
                <Stack.Screen name="Chat" component={ChatScreen} options={{ title: 'AI Tutor' }} />
              </Stack.Group>
            ) : (
              <Stack.Group screenOptions={{ headerShown: false }}>
                {/* 'pop' makes logout/session-expiry animate like going back */}
                <Stack.Screen name="Login" component={LoginScreen} options={{ animationTypeForReplace: 'pop' }} />
                <Stack.Screen name="SignUp" component={SignUpScreen} />
              </Stack.Group>
            )}
          </Stack.Navigator>
        </NavigationContainer>
      )}
    </SafeAreaProvider>
  );
}
