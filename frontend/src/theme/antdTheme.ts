import type { ThemeConfig } from 'antd'
import { colorTokens, typographyTokens } from './tokens'

/** Ant Design 主题映射（规格 13.5：主色、状态色、文字、表面、圆角、字体）。 */
export const antdTheme: ThemeConfig = {
  token: {
    colorPrimary: colorTokens.primaryAction,
    colorInfo: colorTokens.primaryAction,
    colorLink: colorTokens.primaryAction,
    colorSuccess: colorTokens.success,
    colorWarning: colorTokens.warning,
    colorError: colorTokens.danger,
    colorText: colorTokens.textPrimary,
    colorTextSecondary: colorTokens.textSecondary,
    colorTextDisabled: colorTokens.textDisabled,
    colorBgLayout: colorTokens.surfaceGray,
    colorBgContainer: colorTokens.surfacePage,
    colorBorderSecondary: colorTokens.divider,
    fontFamily: typographyTokens.fontFamily,
    fontSize: 14,
  },
}
