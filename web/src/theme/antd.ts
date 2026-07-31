import type { ThemeConfig } from 'antd';

/** 工程蓝图（Engineering Schematic）AntD 主题配置
 * v2 (2026-07): 主色从 #3D5BFF(indigo) 切换为 #0EA5E9(sky)，
 *   与 DAG 画布 INK.accent 对齐，统一全局视觉语言。
 */
const antdTheme: ThemeConfig = {
  token: {
    colorPrimary: '#0EA5E9',
    colorBgLayout: '#F8FAFC',
    colorBgContainer: '#FFFFFF',
    colorText: '#0F172A',
    colorTextSecondary: '#475569',
    colorTextTertiary: '#94A3B8',
    colorBorder: '#E2E8F0',
    colorBorderSecondary: '#E2E8F0',
    colorSplit: '#E2E8F0',
    colorLink: '#0EA5E9',
    colorLinkHover: '#38BDF8',
    borderRadius: 8,
    borderRadiusSM: 3,
    borderRadiusLG: 12,
    fontSize: 14,
    fontFamily:
      "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans', Helvetica, Arial, sans-serif",
    boxShadow: 'rgba(1, 24, 33, 0.05) 0px 0px 0px 1px',
    boxShadowSecondary: 'rgba(1, 24, 33, 0.05) 0px 0px 0px 1px',
    motionDurationMid: '220ms',
    motionDurationSlow: '400ms',
    motionEaseInOut: 'cubic-bezier(0.76, 0, 0.24, 1)',
  },
  components: {
    Layout: {
      headerBg: '#FFFFFF',
      siderBg: '#FFFFFF',
      bodyBg: '#F8FAFC',
      headerHeight: 56,
      headerPadding: '0 24px',
    },
    Card: {
      borderRadiusLG: 8,
      boxShadowTertiary: 'rgba(1, 24, 33, 0.05) 0px 0px 0px 1px',
      headerBg: 'transparent',
      headerFontSize: 16,
      headerHeight: 48,
      paddingLG: 24,
    },
    Table: {
      headerBg: '#F8FAFC',
      headerColor: '#64748B',
      headerSplitColor: '#E2E8F0',
      borderColor: '#E2E8F0',
      rowHoverBg: 'rgba(14, 165, 233, 0.06)',
      cellPaddingBlock: 12,
      cellPaddingInline: 16,
    },
    Menu: {
      itemSelectedBg: 'rgba(14, 165, 233, 0.12)',
      itemSelectedColor: '#0F172A',
      itemHoverBg: 'rgba(14, 165, 233, 0.06)',
      itemColor: '#475569',
      itemBorderRadius: 8,
      itemHeight: 40,
      itemMarginInline: 8,
    },
    Button: {
      borderRadius: 8,
      fontWeight: 500,
      primaryShadow: 'none',
      defaultShadow: 'none',
    },
    Input: {
      borderRadius: 8,
      activeBorderColor: '#38BDF8',
      hoverBorderColor: '#38BDF8',
    },
    Tag: {
      borderRadiusSM: 3,
    },
    Segmented: {
      borderRadius: 8,
      itemSelectedBg: '#FFFFFF',
      itemSelectedColor: '#0F172A',
      trackBg: '#F1F5F9',
    },
    Statistic: {
      contentFontSize: 32,
      titleFontSize: 13,
    },
    Tooltip: {
      borderRadius: 8,
    },
    Popover: {
      borderRadius: 8,
    },
    Modal: {
      borderRadius: 8,
    },
    Empty: {
      colorTextDescription: '#7C7F88',
    },
  },
};

export default antdTheme;