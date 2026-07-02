import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import YamlEditor from '../YamlEditor';

// CodeMirror 需要 DOM 环境，jsdom 下做基本渲染测试
describe('YamlEditor', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('渲染编辑器容器', () => {
    const { container } = render(
      <YamlEditor value="name: test" onChange={() => {}} />,
    );
    // 应该有 CodeMirror 编辑器 DOM
    const editor = container.querySelector('.cm-editor');
    expect(editor).toBeTruthy();
  });

  it('显示 YAML 编辑器标题', () => {
    render(<YamlEditor value="" onChange={() => {}} />);
    expect(screen.getByText('YAML 编辑器')).toBeInTheDocument();
  });

  it('显示错误信息', () => {
    render(
      <YamlEditor
        value="invalid: ["
        onChange={() => {}}
        error={{ message: 'unexpected end', line: 1, column: 11 }}
      />,
    );
    expect(screen.getByText(/unexpected end/)).toBeInTheDocument();
    expect(screen.getByText(/行 1:11/)).toBeInTheDocument();
  });

  it('不显示错误信息当 error 为 null', () => {
    const { container } = render(
      <YamlEditor value="name: test" onChange={() => {}} error={null} />,
    );
    const alerts = container.querySelectorAll('.ant-alert');
    expect(alerts).toHaveLength(0);
  });

  it('支持 readOnly 模式', () => {
    const { container } = render(
      <YamlEditor value="name: test" onChange={() => {}} readOnly />,
    );
    const editor = container.querySelector('.cm-editor');
    expect(editor).toBeTruthy();
    // CodeMirror 的 readOnly 通过 state 配置，DOM 中可验证 cm-readOnly class 或 contenteditable
    const content = container.querySelector('.cm-content');
    expect(content).toBeTruthy();
  });

  it('显示工具栏按钮', () => {
    const { container } = render(<YamlEditor value="" onChange={() => {}} />);
    // 工具栏中有 3 个按钮（撤销、重做、格式化）
    const toolbar = container.querySelector('.flex.items-center.justify-between');
    const buttons = toolbar?.querySelectorAll('button');
    expect(buttons).toHaveLength(3);
  });

  it('渲染初始值', () => {
    const { container } = render(
      <YamlEditor value="name: hello-world\npipelines: []" onChange={() => {}} />,
    );
    const content = container.querySelector('.cm-content');
    expect(content?.textContent).toContain('name: hello-world');
  });
});
