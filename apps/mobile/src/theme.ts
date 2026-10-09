/**
 * Shared theme: the ONLY place for colours, spacing, typography and branding.
 * To rebrand later: change `palette`/`brand` here (and set brand.logo to an image).
 */

import type { ImageSourcePropType, TextStyle } from 'react-native';

export const palette = {
  primary: '#2563EB',
  primaryPressed: '#1D4ED8',
  primarySoft: '#EFF6FF',
  onPrimary: '#FFFFFF',

  background: '#F8FAFC',
  surface: '#FFFFFF',
  border: '#E2E8F0',
  borderStrong: '#CBD5E1',

  text: '#0F172A',
  textMuted: '#64748B',
  placeholder: '#94A3B8',

  danger: '#DC2626',
  dangerSoft: '#FEF2F2',
  dangerBorder: '#FECACA',

  warning: '#B45309',
  warningSoft: '#FFFBEB',
  warningBorder: '#FDE68A',

  info: '#1D4ED8',
  infoSoft: '#EFF6FF',
  infoBorder: '#BFDBFE',

  success: '#15803D',
  successSoft: '#F0FDF4',
} as const;

export const spacing = { xxs: 2, xs: 4, sm: 8, md: 12, lg: 16, xl: 24, xxl: 32, xxxl: 48 } as const;

export const radius = { sm: 8, md: 12, lg: 16, pill: 999 } as const;

/** Content never stretches wider than this (tablets, landscape, large phones). */
export const layout = { maxContentWidth: 480, minTouchSize: 48 } as const;

export const typography = {
  display: { fontSize: 28, lineHeight: 34, fontWeight: '700', color: palette.text },
  title: { fontSize: 20, lineHeight: 26, fontWeight: '700', color: palette.text },
  subtitle: { fontSize: 16, lineHeight: 22, fontWeight: '600', color: palette.text },
  body: { fontSize: 16, lineHeight: 22, color: palette.text },
  bodyMuted: { fontSize: 15, lineHeight: 21, color: palette.textMuted },
  label: { fontSize: 14, lineHeight: 18, fontWeight: '600', color: palette.text },
  caption: { fontSize: 13, lineHeight: 18, color: palette.textMuted },
  button: { fontSize: 16, lineHeight: 20, fontWeight: '600' },
} satisfies Record<string, TextStyle>;

export const shadow = {
  card: {
    shadowColor: '#0F172A',
    shadowOpacity: 0.06,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 2 },
    elevation: 2,
  },
} as const;

export const brand: { name: string; tagline: string; monogram: string; logo?: ImageSourcePropType } = {
  name: 'EduAR-AI',
  tagline: 'Learn biology in augmented reality',
  monogram: 'AR',
  logo: undefined, // e.g. require('../assets/logo.png') once the team has a logo
};

/** Human label for a module difficulty (1 = easiest). */
export function difficultyLabel(difficulty: number): string {
  if (difficulty <= 1) return 'Beginner';
  if (difficulty === 2) return 'Intermediate';
  return 'Advanced';
}

export const theme = { palette, spacing, radius, layout, typography, shadow, brand } as const;
export type Theme = typeof theme;
