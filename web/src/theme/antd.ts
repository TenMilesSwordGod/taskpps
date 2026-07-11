import type { ThemeConfig } from 'antd';

/** Column design system AntD 主题配置 */
const antdTheme: ThemeConfig = {
  token: {
    colorPrimary: '#3D5BFF',
    colorBgLayout: '#F6F6F8',
    colorBgContainer: '#FFFFFF',
    colorText: '#121620',
    colorTextSecondary: '#7C7F88',
    colorTextTertiary: '#7C7F88',
    colorBorder: '#E3E4E8',
    colorBorderSecondary: '#E3E4E8',
    colorSplit: '#E3E4E8',
    colorLink: '#3D5BFF',
    colorLinkHover: '#7EADFF',
    borderRadius: 8,
    borderRadiusSM: 3,
    borderRadiusLG: 12,
    fontSize: 14,
    fontFamily:
      "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans', Helvetica, Arial, sans-serif",
    boxShadow: 'rgba(17, 26, 74, 0.1) 0px 1px 3px 0px',
    boxShadowSecondary: 'rgba(1, 24, 33, 0.05) 0px 0px 0px 1px',
    motionDurationMid: '220ms',
    motionDurationSlow: '400ms',
    motionEaseInOut: 'cubic-bezier(0.76, 0, 0.24, 1)',
  },
  components: {
    Layout: {
      headerBg: '#FFFFFF',
      siderBg: '#FFFFFF',
      bodyBg: '#F6F6F8',
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
      headerBg: '#F6F6F8',
      headerColor: '#7C7F88',
      headerSplitColor: '#E3E4E8',
      borderColor: '#E3E4E8',
      rowHoverBg: 'rgba(126, 173, 255, 0.06)',
      cellPaddingBlock: 12,
      cellPaddingInline: 16,
    },
    Menu: {
      itemSelectedBg: 'rgba(126, 173, 255, 0.12)',
      itemSelectedColor: '#121620',
      itemHoverBg: 'rgba(126, 173, 255, 0.06)',
      itemColor: '#7C7F88',
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
      activeBorderColor: '#7EADFF',
      hoverBorderColor: '#7EADFF',
    },
    Tag: {
      borderRadiusSM: 3,
    },
    Segmented: {
      borderRadius: 8,
      itemSelectedBg: '#FFFFFF',
      itemSelectedColor: '#121620',
      trackBg: '#F6F6F8',
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