import type { TaskYAML, TaskType } from '@/types';

/**
 * v7 (2026-08): 任务节点共享视觉工具 —— 查看模式（TaskNode）与编辑模式
 * （EditorTaskNode）统一数据→视觉的映射逻辑，消除双实现漂移
 * （此前 inferType 在两处各有一份且字段分支不一致）。
 */

/** 推断任务类型 */
export function inferTaskType(task: TaskYAML): TaskType {
  if (task.invoke) return 'invoke';
  if (task.steps) return 'steps';
  if (task.plugin) return 'plugin';
  if (task.git) return 'git';
  if (task.nexus) return 'nexus';
  return 'command';
}

/**
 * 命令摘要提取 —— 节点第二行展示任务的"一句话本质"。
 * 为什么按类型分派：不同任务类型的关键信息不同（command 是命令原文、
 * invoke 是目标流水线、git 是仓库短名），统一截断原文会丢失语义。
 */
export function summarizeTask(task: TaskYAML): string {
  if (task.command) return task.command;
  if (task.steps) return `${task.steps.length} steps`;
  const invoke = task.invoke as unknown as { task?: string; pipeline?: string } | null | undefined;
  if (invoke) return `→ ${invoke.task ?? invoke.pipeline ?? ''}`;
  if (task.git) {
    const g = task.git as { repo?: string; url?: string };
    const repo = g.repo ?? g.url ?? '';
    const short = repo.split('/').pop() ?? repo;
    return short.replace(/\.git$/, '');
  }
  if (task.nexus) return 'nexus artifact';
  return '';
}

/** 类型主色 → 12% 透明浅底（图标块背景），hex → rgba */
export function tintOf(hex: string, alpha = 0.12): string {
  const c = hex.replace('#', '');
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(c.slice(i, i + 2), 16));
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}
