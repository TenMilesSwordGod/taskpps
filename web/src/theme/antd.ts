import type { ThemeConfig } from 'antd';

/** AntD 主题配置 */
const antdTheme: ThemeConfig = {
  token: {
    colorPrimary: '#1677ff',
    borderRadius: 6,
    fontSize: 14,
  },
  components: {
    Layout: {
      headerBg: '#fff',
      siderBg: '#fff',
    },
  },
};

export default antdTheme;
