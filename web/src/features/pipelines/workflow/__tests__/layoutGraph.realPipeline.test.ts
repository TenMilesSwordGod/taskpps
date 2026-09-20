import { describe, it, expect } from 'vitest';
import type { Node } from '@xyflow/react';
import { parseYamlToPipeline } from '@/utils/yamlParser';
import { yamlToNodes } from '../yamlToNodes';
import yamlText from '../../HelpPanel/examplePipeline.yaml?raw';

/**
 * 真实样例端到端布局回归
 *
 * 使用仓库自带的 examplePipeline.yaml（3 个 subpipeline：prepare/build/deploy，
 * 含并行/串行、显式 depends_on、when 条件），验证从 YAML → 节点 → 布局的
 * 全链路不会出现"节点重叠 / 子节点越出容器"两类回归。
 */

/** 与 layoutGraph 相同的尺寸回退策略，仅用于测试矩形计算 */
function sizeOf(n: Node): { width: number; height: number } {
  const style = n.style as { width?: number; height?: number } | undefined;
  const measured = (n as { measured?: { width?: number; height?: number } }).measured;
  if (measured?.width && measured?.height) return { width: measured.width, height: measured.height };
  if (typeof style?.width === 'number' && typeof style?.height === 'number') {
    return { width: style.width, height: style.height };
  }
  const defaults: Record<string, { width: number; height: number }> = {
    editorTask: { width: 180, height: 56 },
    editorPostChild: { width: 180, height: 56 },
    editorStartEnd: { width: 64, height: 28 },
    editorPostParent: { width: 220, height: 100 },
    editorSubPipeline: { width: 220, height: 120 },
    editorPipeline: { width: 400, height: 200 },
  };
  return defaults[n.type ?? ''] ?? { width: 180, height: 56 };
}

function rect(n: Node) {
  const { width, height } = sizeOf(n);
  return { x: n.position.x, y: n.position.y, right: n.position.x + width, bottom: n.position.y + height, width, height };
}

function overlap(a: ReturnType<typeof rect>, b: ReturnType<typeof rect>): boolean {
  return a.x < b.right && b.x < a.right && a.y < b.bottom && b.y < a.bottom;
}

describe('真实样例 examplePipeline.yaml — 布局回归', () => {
  it('YAML 可解析', () => {
    const parsed = parseYamlToPipeline(yamlText);
    expect(parsed.success).toBe(true);
    expect(parsed.pipeline?.pipelines?.length).toBeGreaterThanOrEqual(3);
  });

  it('同一父容器下的节点两两不重叠', () => {
    const parsed = parseYamlToPipeline(yamlText);
    const { nodes } = yamlToNodes(parsed.pipeline!);

    const byParent = new Map<string | null, Node[]>();
    for (const n of nodes) {
      const pid = n.parentId ?? null;
      if (!byParent.has(pid)) byParent.set(pid, []);
      byParent.get(pid)!.push(n);
    }

    for (const [parentId, siblings] of byParent) {
      for (let i = 0; i < siblings.length; i++) {
        for (let j = i + 1; j < siblings.length; j++) {
          const a = rect(siblings[i]);
          const b = rect(siblings[j]);
          expect(
            overlap(a, b),
            `父容器 ${parentId ?? 'root'} 下节点 ${siblings[i].id} 与 ${siblings[j].id} 重叠`,
          ).toBe(false);
        }
      }
    }
  });

  it('每个容器都包裹其直接子节点，子节点不越界', () => {
    const parsed = parseYamlToPipeline(yamlText);
    const { nodes } = yamlToNodes(parsed.pipeline!);

    const hasChildren = new Set(nodes.filter((n) => n.parentId).map((n) => n.parentId!));
    const containers = nodes.filter((n) => hasChildren.has(n.id));
    expect(containers.length).toBeGreaterThan(0);

    for (const container of containers) {
      const { width, height } = sizeOf(container);
      for (const child of nodes.filter((n) => n.parentId === container.id)) {
        const c = rect(child);
        expect(
          c.x >= 0 && c.y >= 0 && c.right <= width + 0.01 && c.bottom <= height + 0.01,
          `容器 ${container.id} 未包裹子节点 ${child.id}（子 ${JSON.stringify(rect(child))}，容器 ${width}x${height}）`,
        ).toBe(true);
      }
    }
  });

  it('跨 subpipeline 依赖方向正确（prepare → build → deploy 自上而下）', () => {
    const parsed = parseYamlToPipeline(yamlText);
    const { nodes } = yamlToNodes(parsed.pipeline!);

    const y = (id: string) => nodes.find((n) => n.id === id)!.position.y;
    expect(y('__pipeline__prepare')).toBeLessThan(y('__pipeline__build'));
    expect(y('__pipeline__build')).toBeLessThan(y('__pipeline__deploy'));
  });
});
