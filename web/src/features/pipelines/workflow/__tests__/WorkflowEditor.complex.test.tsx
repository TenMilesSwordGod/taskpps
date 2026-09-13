import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import WorkflowEditor from '../WorkflowEditor';
import { COMPLEX_SCENARIOS } from './fixtures/complexPipelines';
import type { PipelineDetail } from '@/types';

/**
 * 复杂场景组件渲染测试（jsdom）
 *
 * 目标：覆盖真实浏览器之外的"渲染层"风险：
 *   - 任意复杂数据不得抛异常/白屏
 *   - 查看模式（readOnly）不得渲染连接点（Handle）
 *   - 文本/特殊字符正确进入 DOM（转义正确）
 *   - 重复节点 ID 不应触发 React 重复 key 警告（无效数据容错）
 *   - 顶层 tasks 在画布上的可见性（产品行为暴露）
 */

/** 渲染并捕获 console.error 输出，用于断言异常警告 */
function renderCapturing(pipeline: PipelineDetail, readOnly: boolean) {
  const errors: string[] = [];
  const spy = vi.spyOn(console, 'error').mockImplementation((...args: unknown[]) => {
    errors.push(args.map((a) => (a instanceof Error ? a.message : String(a))).join(' '));
  });
  const result = render(
    <WorkflowEditor
      pipeline={pipeline}
      selectedNodeId={null}
      onNodeSelect={() => {}}
      readOnly={readOnly}
    />,
  );
  spy.mockRestore();
  return { result, errors };
}

describe.each(COMPLEX_SCENARIOS)('复杂场景渲染 [$id] $title', ({ id, pipeline }) => {
  it('查看模式（readOnly）渲染不抛异常', () => {
    expect(() => renderCapturing(pipeline, true)).not.toThrow();
  });

  it('编辑模式渲染不抛异常', () => {
    expect(() => renderCapturing(pipeline, false)).not.toThrow();
  });

  it('查看模式保留透明 Handle（边锚点），且不可连接', () => {
    const { result } = renderCapturing(pipeline, true);
    const handles = result.container.querySelectorAll('.react-flow__handle');
    // v3 (2026-07): Handle 必须存在 —— React Flow 依赖它作为边锚点。
    // 原实现只读模式移除 Handle 导致所有连线消失；现改为透明 + isConnectable=false。
    expect(handles.length).toBeGreaterThan(0);
    for (const h of Array.from(handles)) {
      expect((h as HTMLElement).style.opacity).toBe('0');
    }
  });

  it('不产生 React 重复 key 警告', () => {
    const { errors } = renderCapturing(pipeline, true);
    const dupKeyErrors = errors.filter((e) => e.includes('same key'));
    expect(dupKeyErrors, `${id}: 存在重复 key 警告`).toEqual([]);
  });
});

describe('复杂场景渲染 — 内容与交互细节', () => {
  it('菱形依赖：4 个任务全部渲染', () => {
    const scenario = COMPLEX_SCENARIOS.find((s) => s.id === 'diamond')!;
    renderCapturing(scenario.pipeline, true);
    for (const name of ['a', 'b', 'c', 'd']) {
      expect(screen.getByText(name)).toBeInTheDocument();
    }
  });

  it('post 密集：三类 hook 标签都渲染', () => {
    const scenario = COMPLEX_SCENARIOS.find((s) => s.id === 'post-heavy')!;
    renderCapturing(scenario.pipeline, true);
    expect(screen.getAllByText('失败时').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('成功时').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('始终').length).toBeGreaterThanOrEqual(1);
  });

  it('特殊字符：任务名以文本形式渲染，不注入 HTML', () => {
    const scenario = COMPLEX_SCENARIOS.find((s) => s.id === 'special-chars')!;
    const { result } = renderCapturing(scenario.pipeline, true);
    expect(screen.getByText('<tag> & "amp"')).toBeInTheDocument();
    // 确认没有把尖括号当成 HTML 标签注入
    expect(result.container.querySelectorAll('tag').length).toBe(0);
  });

  it('超长名称：完整文本进入 DOM（由 CSS 截断显示）', () => {
    const scenario = COMPLEX_SCENARIOS.find((s) => s.id === 'long-names')!;
    renderCapturing(scenario.pipeline, true);
    const longName = scenario.pipeline.pipelines![0].tasks[0].name;
    expect(screen.getByText(longName)).toBeInTheDocument();
  });

  it('编辑模式渲染连接点 Handle', () => {
    const scenario = COMPLEX_SCENARIOS.find((s) => s.id === 'diamond')!;
    const { result } = renderCapturing(scenario.pipeline, false);
    expect(result.container.querySelectorAll('.react-flow__handle').length).toBeGreaterThan(0);
  });

  it('顶层 tasks：规范化为同名 SubPipeline 后可见', () => {
    const scenario = COMPLEX_SCENARIOS.find((s) => s.id === 'top-level-tasks')!;
    renderCapturing(scenario.pipeline, true);
    // v3 (2026-07): yamlToNodes 入口统一规范化顶层 tasks（与后端 _normalize 对齐）
    expect(screen.getByText('init')).toBeInTheDocument();
    expect(screen.getByText('cleanup')).toBeInTheDocument();
  });

  it('大图 60 任务：所有节点渲染且包含最后一级任务', () => {
    const scenario = COMPLEX_SCENARIOS.find((s) => s.id === 'many-tasks')!;
    renderCapturing(scenario.pipeline, true);
    expect(screen.getByText('a-1')).toBeInTheDocument();
    expect(screen.getByText('c-20')).toBeInTheDocument();
  });

  // 说明(2026-07): 边的实际渲染（react-flow__edge / 路径长度）依赖浏览器测量的
  // handle 坐标，jsdom 中无法稳定复现，统一由 e2e/pipeline-complex-scenarios.spec.ts
  // 的"应渲染连线 / 无零长度边"断言覆盖。
});
