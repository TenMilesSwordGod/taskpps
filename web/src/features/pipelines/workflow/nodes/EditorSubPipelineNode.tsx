import { memo } from 'react';
import { Handle, Position } from '@xyflow/react';
import { FONT_MONO } from '@/features/pipelines/nodes/nodeTokens';
import { SubPipelineIcon, CollapseIcon, ExpandIcon } from '../icons';

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
 * SubPipeline 可编辑容器节点 — n8n 风格
 * 蓝色虚线边框，左 in / 右 out / 底 post 端口，角标显示执行策略
 *
 * v2 (2026-07): SVG 图标替换 emoji + 折叠/展开按钮
 */
function EditorSubPipelineNode({ data, selected }: { data: EditorSubPipelineNodeData; selected?: boolean }) {
  const label = data.label || 'SubPipeline';
  const strategy = data.executionStrategy || 'sequential';
  const maxParallel = data.maxConcurrentTasks;
  const borderColor = selected ? '#1d4ed8' : '#3b82f6';
  const collapsed = data.collapsed === true;

  const badgeText = strategy === 'parallel'
    ? `PAR(${maxParallel || '∞'})`
    : 'SEQ';
  const badgeBg = strategy === 'parallel' ? '#fce7f3' : '#e0e7ff';
  const badgeColor = strategy === 'parallel' ? '#be185d' : '#4338ca';

  if (collapsed) {
    return (
      <div
        style={{
          width: '100%',
          height: '100%',
          border: `2px solid ${borderColor}`,
          borderRadius: 8,
          background: '#eff6ff',
          position: 'relative',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 6,
          minWidth: 120,
          minHeight: 40,
        }}
      >
        <SubPipelineIcon style={{ width: 16, height: 16, color: '#3b82f6' }} />
        <span style={{ fontFamily: FONT_MONO, fontSize: 12, fontWeight: 600, color: '#1e40af' }}>
          {label}
        </span>
        {(data.childrenCount ?? 0) > 0 && (
          <span style={{ fontSize: 10, color: '#6b7280' }}>
            ({data.childrenCount} tasks{data.atomicCount ? `, ${data.atomicCount} atomic` : ''})
          </span>
        )}
      </div>
    );
  }

  return (
    <div
      style={{
        width: '100%',
        height: '100%',
        border: `3px dashed ${borderColor}`,
        borderRadius: 12,
        background: '#eff6ff',
        position: 'relative',
        boxShadow: selected ? '0 0 0 4px rgba(59,130,246,0.12)' : undefined,
        minWidth: 200,
        minHeight: 120,
      }}
    >
      {/* In 端口 — 左侧 */}
      <Handle
        id="in"
        type="target"
        position={Position.Left}
        style={{
          width: 8,
          height: 8,
          background: 'transparent',
          border: '2px solid #64748b',
          borderRadius: '50%',
          left: -5,
          top: '50%',
        }}
      />

      {/* Out 端口 — 右侧 */}
      <Handle
        id="out"
        type="source"
        position={Position.Right}
        style={{
          width: 8,
          height: 8,
          background: 'transparent',
          border: '2px solid #64748b',
          borderRadius: '50%',
          right: -5,
          top: '50%',
        }}
      />

      {/* Post 端口 — 底部 */}
      <Handle
        id="post"
        type="source"
        position={Position.Bottom}
        style={{
          width: 8,
          height: 8,
          background: 'transparent',
          border: '2px solid #ef4444',
          borderRadius: '50%',
          bottom: -5,
        }}
      />

      {/* 标题栏 */}
      <div
        style={{
          position: 'absolute',
          top: 8,
          left: 12,
          right: 12,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          background: 'transparent',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          {/* v2 (2026-07): SVG 图标替换 emoji */}
          <SubPipelineIcon style={{ width: 18, height: 18, color: '#3b82f6' }} />
          <span
            style={{
              fontFamily: FONT_MONO,
              fontSize: 13,
              fontWeight: 700,
              color: '#1e40af',
            }}
          >
            {label}
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          <span
            style={{
              padding: '1px 6px',
              borderRadius: 4,
              background: badgeBg,
              color: badgeColor,
              fontSize: 10,
              fontFamily: FONT_MONO,
              fontWeight: 600,
            }}
          >
            {badgeText}
          </span>
          {/* v2 (2026-07): 折叠按钮 */}
          <span
            style={{
              cursor: 'pointer',
              padding: '2px',
              borderRadius: 4,
              display: 'flex',
              alignItems: 'center',
              color: '#64748b',
            }}
            title="折叠"
            className="collapse-toggle"
            data-collapsed={collapsed ? 'true' : 'false'}
          >
            <CollapseIcon style={{ width: 14, height: 14 }} />
          </span>
        </div>
      </div>
    </div>
  );
}

export default memo(EditorSubPipelineNode);
