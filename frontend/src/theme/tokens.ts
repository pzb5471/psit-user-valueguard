/**
 * 视觉令牌唯一来源（技术实施规格 13.5）。
 * theme.css 中的 CSS 变量必须与本文件一致，由 tests/theme.test.ts 校验。
 * 页面组件不得散落十六进制颜色、圆角和间距常量。
 */

export const colorTokens = {
  primaryAction: '#0066cc',
  focus: '#0071e3',
  linkOnDark: '#2997ff',
  textPrimary: '#1d1d1f',
  textSecondary: '#333333',
  textDisabled: '#7a7a7a',
  surfacePage: '#ffffff',
  surfaceGray: '#f5f5f7',
  surfaceSecondary: '#fafafc',
  divider: '#e0e0e0',
  topBar: '#000000',
  success: '#1f7a3d',
  warning: '#8a4b00',
  danger: '#b42318',
} as const

export const typographyTokens = {
  fontFamily: "'Inter', 'SF Pro Text', system-ui, 'Segoe UI', sans-serif",
  pageTitleSize: '34px',
  pageTitleWeight: '600',
  pageTitleLineHeight: '1.2',
  sectionTitleSize: '21px',
  sectionTitleWeight: '600',
  sectionTitleLineHeight: '1.25',
  bodySize: '17px',
  bodyWeight: '400',
  bodyLineHeight: '1.47',
  controlSize: '14px',
  controlLineHeight: '1.43',
  captionSize: '12px',
} as const

export const spacingTokens = {
  space1: '4px',
  space2: '8px',
  space3: '12px',
  space4: '17px',
  space5: '24px',
  space6: '32px',
  space7: '48px',
  pageGutter: '32px',
  pageGutterNarrow: '24px',
} as const

export const radiusTokens = {
  card: '18px',
  control: '8px',
  pill: '999px',
} as const

export const motionTokens = {
  durationFast: '120ms',
  durationBase: '180ms',
  pressScale: '0.98',
  ease: 'cubic-bezier(0.4, 0, 0.2, 1)',
} as const

export const zIndexTokens = {
  base: '0',
  subNav: '90',
  topBar: '100',
  overlay: '200',
} as const
