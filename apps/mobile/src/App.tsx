/**
 * Root navigation (PDF §1: "App.tsx — Root navigation (React Navigation stack)").
 *
 * 1. While authStore.restoreSession() runs → SplashScreen.
 * 2. Signed out → Login, SignUp.   Signed in → Topics → Dna (AR game, AI tutor, quiz, progress) → ARGame / Chat / Quiz;
 *    Topics → Profile (details, password, wildcards, log out).
 * Signing in/out swaps the screen set; React Navigation moves to the right screen
 * automatically (never navigate to Topics manually after login).
 */

import { DefaultTheme, NavigationContainer, type Theme as NavigationTheme } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { StatusBar } from 'expo-status-bar';
import { useEffect } from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import type { RootStackParamList } from './navigation/types';
import { ARGameScreen } from './screens/ARGameScreen';
import { ChatScreen } from './screens/ChatScreen';
import { DnaScreen } from './screens/DnaScreen';
import { ForgotPasswordScreen } from './screens/ForgotPasswordScreen';
import { ProfileScreen } from './screens/ProfileScreen';
import { QuizScreen } from './screens/QuizScreen';
import { LoginScreen } from './screens/LoginScreen';
import { SignUpScreen } from './screens/SignUpScreen';
import { SplashScreen } from './screens/SplashScreen';
import { useAppUsageLog } from './services/AppUsage';
import { TopicsScreen } from './screens/TopicsScreen';
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

  useAppUsageLog(isAuthenticated); // admin panel: times the app was used

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
                <Stack.Screen name="Topics" component={TopicsScreen} options={{ title: brand.name }} />
                <Stack.Screen name="Dna" component={DnaScreen} options={{ title: 'DNA' }} />
                <Stack.Screen name="Profile" component={ProfileScreen} options={{ title: 'Profile' }} />
                <Stack.Screen name="ARGame" component={ARGameScreen} options={({ route }) => ({ title: route.params.title })} />
                <Stack.Screen name="Chat" component={ChatScreen} options={{ title: 'AI Tutor' }} />
                <Stack.Screen name="Quiz" component={QuizScreen} options={{ title: 'DNA Quiz' }} />
              </Stack.Group>
            ) : (
              <Stack.Group screenOptions={{ headerShown: false }}>
                {/* 'pop' makes logout/session-expiry animate like going back */}
                <Stack.Screen name="Login" component={LoginScreen} options={{ animationTypeForReplace: 'pop' }} />
                <Stack.Screen name="SignUp" component={SignUpScreen} />
                <Stack.Screen name="ForgotPassword" component={ForgotPasswordScreen} />
              </Stack.Group>
            )}
          </Stack.Navigator>
        </NavigationContainer>
      )}
    </SafeAreaProvider>
  );
}
