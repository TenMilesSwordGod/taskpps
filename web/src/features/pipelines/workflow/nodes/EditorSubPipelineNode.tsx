import { memo } from 'react';
import { Handle, Position, NodeResizer } from '@xyflow/react';
import { INK, FONT_SANS } from '@/features/pipelines/nodes/nodeTokens';
import { useReadOnly } from './ReadOnlyContext';

interface EditorSubPipelineNodeData {
  label?: string;
  executionStrategy?: string;
  maxConcurrentTasks?: number;
  collapsed?: boolean;
  childrenCount?: number;
  atomicCount?: number;
  [key: string]: unknown;
}

/**
 * SubPipeline 可编辑容器节点 —— v11 (2026-08) 与查看模式 SubpipelineGroupNode 统一
 *
 * 为什么改：容器必须比节点安静一层（n8n 画布层级语法"画布 < 分组 < 节点"）。
 * 极浅半透底 + 细边 + 无阴影；头部从芯片行收敛为 sans 弱文本
 * 「名称 SEQ · N tasks」。
 *
 * 保留的契约（零改动波及）：
 * - handle id（in/out/post）——isValidConnection 与边数据依赖；
 *   v11 方位随 LR 流向迁移：in=Left / out=Right / post=Bottom
 * - data 字段（label/executionStrategy/maxConcurrentTasks）——nodesToYaml 序列化来源
 * - v7 移除折叠功能；data.collapsed 字段保留兼容历史数据
 */
function EditorSubPipelineNode({ data, selected }: { data: EditorSubPipelineNodeData; selected?: boolean }) {
  const readOnly = useReadOnly();
  const label = data.label || 'SubPipeline';
  const strategy = data.executionStrategy || 'sequential';
  const maxParallel = data.maxConcurrentTasks;
  // v9: 悬停加深走 CSS 变量（editor.css），选中直接染品牌橙
  const borderColor = selected
    ? INK.accent
    : 'var(--wf-card-border, #E4E9F0)';

  const strategyCode = strategy === 'parallel'
    ? `PAR(${maxParallel || '∞'})`
    : 'SEQ';

  return (
    <div
      className="wf-card"
      style={{
        width: '100%',
        height: '100%',
        border: `1px solid ${borderColor}`,
        borderRadius: 14,
        // 与查看模式 SubpipelineGroupNode 同款半透浅底
        background: 'rgba(255, 255, 255, 0.55)',
        position: 'relative',
        boxShadow: selected && !readOnly ? `0 0 0 2px ${INK.accent}40` : undefined,
        minWidth: 200,
        minHeight: 120,
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      {/* v7: 保留容器 resize；v9: 仅选中时出现缩放手柄 */}
      {!readOnly && <NodeResizer isVisible={!!selected} minWidth={200} minHeight={120} />}
      {!readOnly && (
        <>
          {/* In 端口 — v11: 左缘（LR 入口） */}
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

          {/* Out 端口 — v11: 右缘（LR 出口） */}
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

          {/* Post 端口 — v11: 底部（post 路由向下） */}
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

      {/* header 行：sans 弱文本（名称 + 策略 · 任务数），无芯片 */}
      <div
        style={{
          display: 'flex',
          alignItems: 'baseline',
          gap: 7,
          padding: '9px 14px 0',
          fontFamily: FONT_SANS,
          whiteSpace: 'nowrap',
        }}
      >
        <span
          style={{
            fontSize: 12,
            fontWeight: 600,
            color: '#64748B',
            letterSpacing: 0.1,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
          }}
        >
          {label}
        </span>
        {/* 策略码独立 span：containerValidation 测试以 getByText('SEQ') 精确匹配为契约 */}
        <span style={{ fontSize: 10.5, fontWeight: 500, color: INK.textSecondary, letterSpacing: 0.2 }}>
          {strategyCode}
        </span>
        {(data.childrenCount ?? 0) > 0 && (
          <span style={{ fontSize: 10.5, fontWeight: 500, color: INK.textSecondary, letterSpacing: 0.2 }}>
            · {data.childrenCount} tasks
          </span>
        )}
      </div>
    </div>
  );
}

export default memo(EditorSubPipelineNode);
