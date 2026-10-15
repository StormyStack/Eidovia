/**
 * Route names + params for the root native stack (src/App.tsx).
 * Auth screens and app screens are never mounted at the same time.
 */

import type { NativeStackScreenProps } from '@react-navigation/native-stack';

import type { ModuleConfig } from '../services/types';

export type RootStackParamList = {
  // signed out
  Login: undefined;
  SignUp: undefined;
  /** forgot password: ask support to reset it (prefilled with what was typed on Login) */
  ForgotPassword: { username?: string } | undefined;
  // signed in
  /** first screen after login: the topics (DNA first) */
  Topics: undefined;
  /** the DNA topic: AR game, AI tutor, quiz and the learner's progress + quiz results */
  Dna: undefined;
  /** the DNA multiple-choice quiz (start / force / approved attempt, answer, result, early-attempt requests) */
  Quiz: undefined;
  /** name, email, level, age, gender, change password, wildcards (+ request), log out */
  Profile: undefined;
  /** config = GET /api/modules/{id}/config response (PDF contract); title for the header. */
  ARGame: { config: ModuleConfig; title: string };
  /** AI chat — optional module_id scopes answers to that module's content. */
  Chat: { module_id?: string } | undefined;
};

export type ScreenProps<Name extends keyof RootStackParamList> = NativeStackScreenProps<RootStackParamList, Name>;

declare global {
  // eslint-disable-next-line @typescript-eslint/no-namespace
  namespace ReactNavigation {
    // Gives useNavigation() the right types everywhere
    // eslint-disable-next-line @typescript-eslint/no-empty-object-type
    interface RootParamList extends RootStackParamList {}
  }
}
