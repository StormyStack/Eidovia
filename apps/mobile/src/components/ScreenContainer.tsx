import type { ReactNode } from 'react';
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, View, type StyleProp, type ViewStyle } from 'react-native';
import { SafeAreaView, type Edge } from 'react-native-safe-area-context';

import { layout, palette, spacing } from '../theme';

export interface ScreenContainerProps {
  children: ReactNode;
  /** Safe-area edges to pad; screens under a native header only need the bottom. */
  edges?: Edge[];
  /** Vertically centre short content (auth forms). */
  centered?: boolean;
  contentStyle?: StyleProp<ViewStyle>;
  testID?: string;
}

/**
 * Keyboard-safe, scrollable, safe-area-aware page with a max content width,
 * so forms work on small phones (scroll) and large phones/tablets (centred column).
 */
export function ScreenContainer({ children, edges = ['top', 'bottom'], centered = false, contentStyle, testID }: ScreenContainerProps) {
  return (
    <SafeAreaView style={styles.safe} edges={edges} testID={testID}>
      <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <ScrollView
          style={styles.flex}
          contentContainerStyle={[styles.scrollContent, centered && styles.centered]}
          keyboardShouldPersistTaps="handled"
          keyboardDismissMode="on-drag"
          showsVerticalScrollIndicator={false}
        >
          <View style={[styles.column, contentStyle]}>{children}</View>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: palette.background },
  flex: { flex: 1 },
  scrollContent: { flexGrow: 1, paddingHorizontal: spacing.xl, paddingVertical: spacing.xl },
  centered: { justifyContent: 'center' },
  column: { width: '100%', maxWidth: layout.maxContentWidth, alignSelf: 'center' },
});
