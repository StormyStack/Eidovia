import { ActivityIndicator, StyleSheet, View } from 'react-native';

import { BrandHeader } from '../components/BrandHeader';
import { palette, spacing } from '../theme';

/** Shown while authStore.restoreSession() checks for a saved login. */
export function SplashScreen() {
  return (
    <View style={styles.container} testID="splash-screen" accessibilityLabel="Loading" accessibilityLiveRegion="polite">
      <BrandHeader />
      <ActivityIndicator size="large" color={palette.primary} style={styles.spinner} />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: palette.background, padding: spacing.xl },
  spinner: { marginTop: spacing.lg },
});
