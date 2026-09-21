import type { ThemeConfig } from 'antd';

/** 「黑白极简（Monochrome）」AntD 主题配置
 *
 * v3 (2026-07): 曾由「工程蓝图」改造为 n8n 暖橙 #FF6D5A 主题。
 * v4 (2026-07): 用户反馈橙色过于刺激，改为"主要黑与白"——品牌色全部收敛为
 *   黑灰阶，仅保留语义状态色（成功绿/失败红/跳过琥珀/信息蓝）用于状态辨识。
 * 设计决策（为什么这么写）：
 * - 主色 #1F1F1F（主按钮/链接/激活态），hover #3A3A3A，避免高饱和品牌色；
 * - 背景/边框全部中性灰阶（#F5F5F5/#FAFAFA/#E0E0E0），去除暖橙暖灰偏色；
 * - 语义状态色保留独立（颜色承载"状态信息"，不属于"装饰刺激"）。
 */
const antdTheme: ThemeConfig = {
  token: {
    colorPrimary: '#1F1F1F',
    colorInfo: '#2F7FF5',
    colorSuccess: '#16A34A',
    colorWarning: '#F59E0B',
    colorError: '#EF4444',
    colorBgLayout: '#F5F5F5',
    colorBgContainer: '#FFFFFF',
    colorText: '#262626',
    colorTextSecondary: '#525252',
    colorTextTertiary: '#8C8C8C',
    colorBorder: '#E0E0E0',
    colorBorderSecondary: '#E0E0E0',
    colorSplit: '#E8E8E8',
    colorLink: '#1F1F1F',
    colorLinkHover: '#3A3A3A',
    borderRadius: 8,
    borderRadiusSM: 6,
    borderRadiusLG: 12,
    fontSize: 14,
    fontFamily:
      "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans', Helvetica, Arial, sans-serif",
    boxShadow: 'rgba(30, 25, 20, 0.06) 0px 1px 2px, rgba(30, 25, 20, 0.04) 0px 2px 8px',
    boxShadowSecondary: 'rgba(30, 25, 20, 0.08) 0px 4px 16px',
    boxShadowTertiary: 'rgba(30, 25, 20, 0.04) 0px 1px 3px, rgba(30, 25, 20, 0.03) 0px 4px 12px',
    motionDurationMid: '220ms',
    motionDurationSlow: '400ms',
    motionEaseInOut: 'cubic-bezier(0.76, 0, 0.24, 1)',
  },
  components: {
    Layout: {
      headerBg: '#FFFFFF',
      siderBg: '#FFFFFF',
      bodyBg: '#F5F5F5',
      headerHeight: 56,
      headerPadding: '0 24px',
    },
    Card: {
      borderRadiusLG: 12,
      headerBg: 'transparent',
      headerFontSize: 16,
      headerHeight: 48,
      paddingLG: 24,
    },
    Table: {
      headerBg: '#FAFAFA',
      headerColor: '#525252',
      headerSplitColor: '#E8E8E8',
      borderColor: '#E8E8E8',
      rowHoverBg: 'rgba(31, 31, 31, 0.06)',
      cellPaddingBlock: 12,
      cellPaddingInline: 16,
    },
    Menu: {
      itemSelectedBg: 'rgba(31, 31, 31, 0.10)',
      itemSelectedColor: '#262626',
      itemHoverBg: 'rgba(31, 31, 31, 0.06)',
      itemColor: '#525252',
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
      activeBorderColor: '#3A3A3A',
      hoverBorderColor: '#3A3A3A',
      activeShadow: '0 0 0 2px rgba(31, 31, 31, 0.10)',
    },
    Select: {
      borderRadius: 8,
      activeBorderColor: '#3A3A3A',
      hoverBorderColor: '#3A3A3A',
      optionSelectedBg: 'rgba(31, 31, 31, 0.10)',
    },
    Tag: {
      borderRadiusSM: 6,
    },
    Segmented: {
      borderRadius: 8,
      itemSelectedBg: '#FFFFFF',
      itemSelectedColor: '#262626',
      trackBg: '#F0F0F0',
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
    Dropdown: {
      borderRadius: 8,
    },
    Modal: {
      borderRadius: 12,
    },
    Drawer: {
      borderRadius: 0,
    },
    Empty: {
      colorTextDescription: '#8C8C8C',
    },
    Tabs: {
      itemSelectedColor: '#1F1F1F',
      itemHoverColor: '#3A3A3A',
      inkBarColor: '#1F1F1F',
    },
    Checkbox: {
      colorPrimary: '#1F1F1F',
    },
    Radio: {
      colorPrimary: '#1F1F1F',
    },
    Switch: {
      colorPrimary: '#1F1F1F',
    },
    Progress: {
      defaultColor: '#1F1F1F',
    },
  },
};

export default antdTheme;
