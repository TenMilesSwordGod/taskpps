import { memo } from 'react';
import { Handle, Position } from '@xyflow/react';
import type { TaskYAML } from '@/types';
import {
  TYPE_ICON,
  TYPE_ICON_BG,
  TYPE_LABEL,
  FONT_MONO,
  FONT_SANS,
  INK,
  CARD_SHADOW,
} from '@/features/pipelines/nodes/nodeTokens';
import { inferTaskType, summarizeTask } from '@/features/pipelines/nodes/taskVisual';
import { useReadOnly } from './ReadOnlyContext';

interface EditorTaskNodeData {
  task?: TaskYAML;
  taskType?: string;
  subpipelineName?: string;
  collapsed?: boolean;
  [key: string]: unknown;
}

/**
 * 可编辑 Task 节点 —— v11 (2026-08) 与查看模式 TaskNode 视觉统一（n8n 卡片）
 *
 * 为什么改：用户反馈编辑模式与查看模式"长得不一样"。
 * - 视觉：n8n 卡片（类型色图标块 + 白色 glyph + 名称/摘要两行），
 *   数据→视觉映射与 TaskNode 同源（taskVisual.ts 共享）
 * - 连线：v11 随 LR 流向迁移 —— in=Left / out=Right / post=Bottom
 *   （post 路由向下离开主流程道）
 * - 保留：handle id 契约（in/out/post）不动 → isValidConnection、
 *   yamlToNodes 边数据、nodesToYaml 序列化零改动
 * - 编辑态以浅底微染暗示可编辑；选中态品牌橙描边；悬停边框走 CSS 变量
 */
function EditorTaskNode({ data, selected }: { data: EditorTaskNodeData; selected?: boolean }) {
  const readOnly = useReadOnly();
  const task = data.task;
  const taskName = task?.name || 'Task';
  const taskType = (data.taskType as never) || (task ? inferTaskType(task) : 'command');
  const summary = task ? summarizeTask(task) : '';
  const IconGlyph = TYPE_ICON[taskType as keyof typeof TYPE_ICON] ?? TYPE_ICON.command;

  // v9 (2026-08): 边框色走 CSS 变量 —— 悬停时 editor.css 改变量即可变色
  // （inline style 优先级高于类规则，只能用 var() 注入悬停反馈）
  const borderColor = selected
    ? INK.accent
    : 'var(--wf-card-border, #DBDFE7)';

  return (
    <div
      className="wf-card"
      style={{
        width: '100%',
        height: '100%',
        minHeight: 56,
        border: `1.5px solid ${borderColor}`,
        borderRadius: 10,
        background: readOnly ? '#FFFFFF' : '#FBFCFE',
        position: 'relative',
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        padding: '0 12px 0 10px',
        boxShadow: selected && !readOnly
          ? `0 0 0 2px ${INK.accent}55, 0 2px 4px rgba(15,23,42,0.08)`
          : CARD_SHADOW,
        boxSizing: 'border-box',
      }}
    >
      {!readOnly && (
        <>
          {/* In 端口 — v11: 左缘（LR 流向入口） */}
          <Handle
            id="in"
            type="target"
            position={Position.Left}
            style={{
              width: 10,
              height: 10,
              background: '#FFFFFF',
              border: '2px solid #64748b',
              borderRadius: '50%',
              left: -6,
              top: '50%',
            }}
          />

          {/* Out 端口 — v11: 右缘（LR 流向出口） */}
          <Handle
            id="out"
            type="source"
            position={Position.Right}
            style={{
              width: 10,
              height: 10,
              background: '#FFFFFF',
              border: '2px solid #64748b',
              borderRadius: '50%',
              right: -6,
              top: '50%',
            }}
          />

          {/* Post 端口 — v11: 底部（post 路由向下离开主流程道） */}
          <Handle
            id="post"
            type="source"
            position={Position.Bottom}
            style={{
              width: 10,
              height: 10,
              background: '#FFFFFF',
              border: '2px solid #ef4444',
              borderRadius: '50%',
              bottom: -6,
              left: '50%',
            }}
          />
        </>
      )}

      {/* 左侧类型图标块：类型色实底 + 白色 glyph（与 TaskNode 同款） */}
      <div
        aria-hidden
        title={TYPE_LABEL[taskType as keyof typeof TYPE_LABEL]}
        style={{
          width: 36,
          height: 36,
          borderRadius: 8,
          backgroundColor: TYPE_ICON_BG,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          flexShrink: 0,
        }}
      >
        <IconGlyph style={{ fontSize: 17, color: '#FFFFFF' }} />
      </div>

      {/* 右侧两行：任务名（sans）+ 命令摘要（mono） */}
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'center',
          minWidth: 0,
          gap: 2,
        }}
      >
        <span
          style={{
            fontFamily: FONT_SANS,
            fontSize: 13,
            fontWeight: 600,
            color: INK.textPrimary,
            letterSpacing: -0.1,
            lineHeight: 1.25,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          {taskName}
        </span>
        {summary && (
          <span
            style={{
              fontFamily: FONT_MONO,
              fontSize: 10.5,
              color: INK.textSecondary,
              lineHeight: 1.2,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
              maxWidth: 130,
            }}
          >
            {summary}
          </span>
        )}
        {/* when 条件徽章（编辑态可见，提示该任务带条件） */}
        {task?.when && (
          <span
            style={{
              fontFamily: FONT_MONO,
              fontSize: 9.5,
              color: '#B45309',
              lineHeight: 1.4,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            when: {task.when.slice(0, 22)}
          </span>
        )}
      </div>
    </div>
  );
}

export default memo(EditorTaskNode);
