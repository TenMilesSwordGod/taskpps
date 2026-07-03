import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import YamlEditor from '../YamlEditor';

describe('YamlEditor 边界值测试', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('空字符串 value 正常渲染', () => {
    const { container } = render(<YamlEditor value="" onChange={() => {}} />);
    const editor = container.querySelector('.cm-editor');
    expect(editor).toBeTruthy();
  });

  it('超长 value 正常渲染（不崩溃）', () => {
    const longYaml = 'name: test\n' + 'tasks:\n' + Array.from({ length: 500 }, (_, i) => `  - name: task-${i}\n    command: echo ${i}`).join('\n');
    const { container } = render(<YamlEditor value={longYaml} onChange={() => {}} />);
    const editor = container.querySelector('.cm-editor');
    expect(editor).toBeTruthy();
  });

  it('error 为 undefined 时不显示错误', () => {
    const { container } = render(<YamlEditor value="name: test" onChange={() => {}} error={undefined} />);
    const alerts = container.querySelectorAll('.ant-alert');
    expect(alerts).toHaveLength(0);
  });

  it('error 为 null 时不显示错误', () => {
    const { container } = render(<YamlEditor value="name: test" onChange={() => {}} error={null} />);
    const alerts = container.querySelectorAll('.ant-alert');
    expect(alerts).toHaveLength(0);
  });

  it('高度为 0 不崩溃', () => {
    const { container } = render(<YamlEditor value="name: test" onChange={() => {}} height={0} />);
    const editor = container.querySelector('.cm-editor');
    expect(editor).toBeTruthy();
  });

  it('高度为百分比字符串', () => {
    const { container } = render(<YamlEditor value="name: test" onChange={() => {}} height="50%" />);
    const editor = container.querySelector('.cm-editor');
    expect(editor).toBeTruthy();
  });

  it('高度为像素数字', () => {
    const { container } = render(<YamlEditor value="name: test" onChange={() => {}} height={400} />);
    const editor = container.querySelector('.cm-editor');
    expect(editor).toBeTruthy();
  });
});
