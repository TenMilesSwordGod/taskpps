import { Component, type ErrorInfo, type ReactNode } from 'react';
import { Button, Result } from 'antd';

/**
 * 全局错误边界（issue #213）。
 *
 * 设计决策（为什么这么写）：
 * - 用 class 组件实现：React 18 尚无函数式错误边界，getDerivedStateFromError 是唯一稳定方案；
 * - 兜底 UI 用 role="alert"：让读屏与自动化（getByRole）都能立即感知故障；
 * - 提供「重新加载」按钮：整页刷新是渲染异常后最可靠的恢复方式（组件树状态已不可信）；
 * - 不向用户展示 error.message/堆栈：错误细节只进 console，避免泄露内部实现。
 *
 * 覆盖范围：所有挂载在 <App/> 下的路由页面；懒加载 chunk 失败（React.lazy reject）
 * 同样会被 Suspense 向上抛出，由本边界兜底，避免整页白屏。
 */
interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
}

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // 仅记录到控制台，便于开发定位；不渲染给用户
    console.error('页面渲染异常已被全局错误边界捕获:', error, info.componentStack);
  }

  handleReload = () => {
    window.location.reload();
  };

  render() {
    if (this.state.hasError) {
      return (
        <div role="alert" style={{ minHeight: '60vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <Result
            status="error"
            title="页面出错了"
            subTitle="页面渲染时发生异常，请重新加载；若问题持续出现，请反馈给管理员。"
            extra={
              <Button type="primary" onClick={this.handleReload}>
                重新加载
              </Button>
            }
          />
        </div>
      );
    }
    return this.props.children;
  }
}
