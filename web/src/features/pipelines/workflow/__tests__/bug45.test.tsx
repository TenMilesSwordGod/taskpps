/**
 * Bug #45 RED 测试：Pipeline 节点缺少 in 端口 + 无 isValidConnection 校验
 *
 * 当前 Bug 表现:
 *   1. EditorPipelineNode 只有 out(source) 和 post(source) Handle，缺少 in(target) Handle
 *   2. WorkflowEditor 的 onConnect 无 isValidConnection 校验，所有连接缺乏验证
 *   3. SubPipeline/Task 的 in/out Handle 虽存在，但因缺失连接校验导致连接不可控
 *
 * RED 测试 — 当前全部失败，描述待修复行为
 */

import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { ReactFlowProvider } from '@xyflow/react';
import EditorPipelineNode from '../nodes/EditorPipelineNode';

describe('Bug#45: 节点连接问题 — RED 测试', () => {
  // ── 测试1: Pipeline 缺少 "in" Handle ──────────────────────────────
  it('RED: Pipeline 节点应有 "in"(target) 端口用于 Start 连接', () => {
    const { container } = render(
      <ReactFlowProvider>
        <EditorPipelineNode data={{}} />
      </ReactFlowProvider>
    );
    // 当前 EditorPipelineNode 未定义 id="in" 的 Handle → querySelector 返回 null
    const inHandle = container.querySelector('[data-handleid="in"]');
    // 期望存在 → 实际不存在 → RED
    expect(inHandle).not.toBeNull();
  });

  // ── 测试2: isValidConnection 函数不存在 ───────────────────────────
  it('RED: isValidConnection 函数应在 WorkflowEditor 中定义', async () => {
    // 使用动态导入检查 isValidConnection 导出
    // 当前 WorkflowEditor 未定义/导出该函数 → module.isValidConnection === undefined
    const workflowModule = await import('../WorkflowEditor');
    const isValidConnection = (workflowModule as any).isValidConnection;
    // 修复后该函数应为 function
    expect(typeof isValidConnection).toBe('function');
  });

  // ── 测试3: isValidConnection 应允许 Start→Pipeline ───────────────
  it('RED: isValidConnection 应允许 Start(out)→Pipeline(in) 连接', async () => {
    const workflowModule = await import('../WorkflowEditor');
    const isValidConnection = (workflowModule as any).isValidConnection as
      | ((conn: { source: string; target: string; sourceHandle: string | null; targetHandle: string | null }) => boolean)
      | undefined;

    // 如果函数不存在，此测试应显式失败
    if (typeof isValidConnection !== 'function') {
      expect(isValidConnection).toBeDefined();
      return;
    }

    // Start(out) → Pipeline(in) 应为有效连接
    const result = isValidConnection({
      source: '__start__',
      target: '__pipeline__',
      sourceHandle: 'out',
      targetHandle: 'in',
    });
    expect(result).toBe(true);
  });

  // ── 测试4: isValidConnection 应允许 SubPipeline↔外部节点 ─────────
  it('RED: isValidConnection 应允许 SubPipeline↔外部节点连接', async () => {
    const workflowModule = await import('../WorkflowEditor');
    const isValidConnection = (workflowModule as any).isValidConnection as
      | ((conn: { source: string; target: string; sourceHandle: string | null; targetHandle: string | null }) => boolean)
      | undefined;

    if (typeof isValidConnection !== 'function') {
      expect(isValidConnection).toBeDefined();
      return;
    }

    // Task(out) → SubPipeline(in) 应有效
    const taskToSub = isValidConnection({
      source: '__task__build.compile',
      target: '__subpipeline__deploy',
      sourceHandle: 'out',
      targetHandle: 'in',
    });
    expect(taskToSub).toBe(true);

    // SubPipeline(out) → Task(in) 应有效
    const subToTask = isValidConnection({
      source: '__subpipeline__deploy',
      target: '__task__build.compile',
      sourceHandle: 'out',
      targetHandle: 'in',
    });
    expect(subToTask).toBe(true);
  });

  // ── 测试5: isValidConnection 应允许 Task↔SubPipeline ─────────────
  it('RED: isValidConnection 应允许 Task↔SubPipeline 连接', async () => {
    const workflowModule = await import('../WorkflowEditor');
    const isValidConnection = (workflowModule as any).isValidConnection as
      | ((conn: { source: string; target: string; sourceHandle: string | null; targetHandle: string | null }) => boolean)
      | undefined;

    if (typeof isValidConnection !== 'function') {
      expect(isValidConnection).toBeDefined();
      return;
    }

    // Task(out) → SubPipeline(in)
    const taskToSub = isValidConnection({
      source: '__task__test.lint',
      target: '__subpipeline__deploy',
      sourceHandle: 'out',
      targetHandle: 'in',
    });
    expect(taskToSub).toBe(true);

    // SubPipeline(out) → Task(in)
    const subToTask = isValidConnection({
      source: '__subpipeline__deploy',
      target: '__task__test.lint',
      sourceHandle: 'out',
      targetHandle: 'in',
    });
    expect(subToTask).toBe(true);
  });
});
