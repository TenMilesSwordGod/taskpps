import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import type { ComponentType } from 'react';
import {
  DashboardIcon,
  PipelineIcon,
  RunHistoryIcon,
  ServerIcon,
  PluginIcon,
  SubPipelineIcon,
  EnvironmentIcon,
  DependencyIcon,
  SettingsIcon,
  InfoIcon,
  CodeIcon,
  HelpIcon,
  ExamplesIcon,
  AutoLayoutIcon,
  ExportImageIcon,
  ResultIcon,
} from '@/components/icons';
import {
  PluginIcon as WorkflowPluginIcon,
  SubPipelineIcon as WorkflowSubPipelineIcon,
} from '@/features/pipelines/workflow/icons';

const ALL_ICONS: Array<[string, ComponentType]> = [
  ['DashboardIcon', DashboardIcon],
  ['PipelineIcon', PipelineIcon],
  ['RunHistoryIcon', RunHistoryIcon],
  ['ServerIcon', ServerIcon],
  ['PluginIcon', PluginIcon],
  ['SubPipelineIcon', SubPipelineIcon],
  ['EnvironmentIcon', EnvironmentIcon],
  ['DependencyIcon', DependencyIcon],
  ['SettingsIcon', SettingsIcon],
  ['InfoIcon', InfoIcon],
  ['CodeIcon', CodeIcon],
  ['HelpIcon', HelpIcon],
  ['ExamplesIcon', ExamplesIcon],
  ['AutoLayoutIcon', AutoLayoutIcon],
  ['ExportImageIcon', ExportImageIcon],
  ['ResultIcon', ResultIcon],
];

describe('品牌图标库（components/icons）', () => {
  it.each(ALL_ICONS)('%s 渲染统一工程蓝图风格（24 网格 / currentColor / 2px 描边）', (_name, Icon) => {
    const { container } = render(<Icon />);
    const svg = container.querySelector('svg');
    expect(svg).not.toBeNull();
    expect(svg).toHaveAttribute('viewBox', '0 0 24 24');
    // 尺寸用 1em：跟随父级 font-size，菜单/按钮/树节点可复用同一图标
    expect(svg).toHaveAttribute('width', '1em');
    expect(svg).toHaveAttribute('height', '1em');
    expect(svg).toHaveAttribute('fill', 'none');
    // 颜色由父级 color 透传，避免图标内写死颜色
    expect(svg).toHaveAttribute('stroke', 'currentColor');
    expect(svg).toHaveAttribute('stroke-width', '2');
    // 装饰性图标默认对读屏隐藏，语义由相邻文本提供
    expect(svg).toHaveAttribute('aria-hidden', 'true');
  });

  it('默认 verticalAlign 对齐文本基线，且调用方 style 可覆盖其他属性', () => {
    const { container } = render(<PluginIcon style={{ color: 'red' }} />);
    const svg = container.querySelector('svg')!;
    expect(svg.style.verticalAlign).toBe('-0.125em');
    expect(svg.style.color).toBe('red');
  });

  it('支持 className / 尺寸 / aria 属性透传', () => {
    const { container } = render(
      <PipelineIcon className="my-pipeline-icon" width={20} height={20} aria-label="流水线" aria-hidden="false" />,
    );
    const svg = container.querySelector('svg')!;
    expect(svg).toHaveClass('my-pipeline-icon');
    expect(svg).toHaveAttribute('width', '20');
    expect(svg).toHaveAttribute('height', '20');
    expect(svg).toHaveAttribute('aria-label', '流水线');
    expect(svg).toHaveAttribute('aria-hidden', 'false');
  });

  it('workflow/icons 的品牌图标与品牌库同源（仅 re-export，避免重复路径）', () => {
    expect(WorkflowPluginIcon).toBe(PluginIcon);
    expect(WorkflowSubPipelineIcon).toBe(SubPipelineIcon);
  });
});
