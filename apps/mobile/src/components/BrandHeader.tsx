import { Image, StyleSheet, Text, View } from 'react-native';

import { brand, palette, radius, spacing, typography } from '../theme';

/** Logo + app name + tagline. Uses brand.logo from theme.ts when the team adds one. */
export function BrandHeader({ subtitle }: { subtitle?: string }) {
  return (
    <View style={styles.container} accessibilityRole="header">
      {brand.logo ? (
        <Image source={brand.logo} style={styles.logo} accessibilityLabel={`${brand.name} logo`} />
      ) : (
        <View style={styles.monogram} accessibilityElementsHidden importantForAccessibility="no-hide-descendants">
          <Text style={styles.monogramText}>{brand.monogram}</Text>
        </View>
      )}
      <Text style={styles.name}>{brand.name}</Text>
      <Text style={styles.tagline}>{subtitle ?? brand.tagline}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { alignItems: 'center', marginBottom: spacing.xxl },
  logo: { width: 72, height: 72, borderRadius: radius.lg, marginBottom: spacing.md },
  monogram: {
    width: 72,
    height: 72,
    borderRadius: radius.lg,
    backgroundColor: palette.primary,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: spacing.md,
  },
  monogramText: { color: palette.onPrimary, fontSize: 28, fontWeight: '800', letterSpacing: 1 },
  name: { ...typography.display },
  tagline: { ...typography.bodyMuted, marginTop: spacing.xs, textAlign: 'center' },
});
