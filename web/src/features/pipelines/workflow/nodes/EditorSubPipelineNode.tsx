import { memo, useCallback, type CSSProperties } from 'react';
import { Handle, Position, useReactFlow, NodeResizer } from '@xyflow/react';
import { FONT_MONO } from '@/features/pipelines/nodes/nodeTokens';
import { SubPipelineIcon, CollapseIcon } from '../icons';
import { useReadOnly } from './ReadOnlyContext';
import { applyCollapse } from '../collapse';

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
 * v3 (2026-07): 折叠按钮添加 onClick — 通过 useReactFlow 直接操作 store 避免回调传递
 */
/**
 * SubPipeline 容器端口组
 *
 * v4 (2026-07): 与 EditorTaskNode 同理 —— Handle 是 React Flow 边的锚点，
 * 只读/折叠时不能移除，否则连线消失；只读时透明且不可连接。
 * v5 (2026-07): 端口方位改为 上 in / 下 out，与 TB 布局一致，消除两侧绕线。
 */
function SubPipelineHandles({ readOnly }: { readOnly: boolean }) {
  const base: CSSProperties = {
    width: 8,
    height: 8,
    background: 'transparent',
    borderRadius: '50%',
    ...(readOnly ? { opacity: 0, pointerEvents: 'none' } : null),
  };
  return (
    <>
      {/* In 端口 — 顶部（接收上游容器） */}
      <Handle
        id="in"
        type="target"
        position={Position.Top}
        isConnectable={!readOnly}
        style={{ ...base, border: '2px solid #64748b' }}
      />

      {/* Out 端口 — 底部（连向下游容器） */}
      <Handle
        id="out"
        type="source"
        position={Position.Bottom}
        isConnectable={!readOnly}
        style={{ ...base, border: '2px solid #64748b' }}
      />

      {/* Post 端口 — 底部偏右（与 out 错开） */}
      <Handle
        id="post"
        type="source"
        position={Position.Bottom}
        isConnectable={!readOnly}
        style={{ ...base, border: '2px solid #ef4444', left: '75%', transform: 'translateX(-50%)' }}
      />
    </>
  );
}

function EditorSubPipelineNode({ id, data, selected }: { id: string; data: EditorSubPipelineNodeData; selected?: boolean }) {
  const readOnly = useReadOnly();
  const label = data.label || 'SubPipeline';
  const strategy = data.executionStrategy || 'sequential';
  const maxParallel = data.maxConcurrentTasks;
  // 注意(2026-07): 只读模式下使用实线边框 + 无蓝色选中阴影
  const borderStyle = readOnly ? 'solid' : 'dashed';
  const borderColor = selected ? (readOnly ? '#64748b' : '#1d4ed8') : '#3b82f6';
  const collapsed = data.collapsed === true;

  const { setNodes } = useReactFlow();

  // v3 (2026-07): 折叠/展开按钮点击处理
  // 通过 useReactFlow().setNodes 直接操作 store，避免通过 data 传递回调导致的闭包问题
  // v4 (2026-07): 统一走 applyCollapse —— 折叠时隐藏后代节点、保存原尺寸供展开恢复
  const handleToggleClick = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation(); // 防止触发节点选中
      setNodes((nds) => {
        const nextCollapsed = nds.find((n) => n.id === id)?.data?.collapsed !== true;
        return applyCollapse(nds, id, nextCollapsed);
      });
    },
    [id, setNodes],
  );

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
        {!readOnly && <NodeResizer minWidth={120} minHeight={40} />}
        <SubPipelineHandles readOnly={readOnly} />
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
        border: `3px ${borderStyle} ${borderColor}`,
        borderRadius: 12,
        background: '#eff6ff',
        position: 'relative',
        boxShadow: selected && !readOnly ? '0 0 0 4px rgba(59,130,246,0.12)' : undefined,
        minWidth: 200,
        minHeight: 120,
      }}
    >
      {!readOnly && <NodeResizer minWidth={200} minHeight={120} />}
      <SubPipelineHandles readOnly={readOnly} />

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
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 0, flex: 1 }}>
          {/* v2 (2026-07): SVG 图标替换 emoji */}
          <SubPipelineIcon style={{ width: 18, height: 18, color: '#3b82f6', flexShrink: 0 }} />
          {/* v3 (2026-07): 超长子流水线名换行撑破容器（截图验证），改为单行 ellipsis */}
          <span
            style={{
              fontFamily: FONT_MONO,
              fontSize: 13,
              fontWeight: 700,
              color: '#1e40af',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
              minWidth: 0,
            }}
          >
            {label}
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 4, flexShrink: 0, marginLeft: 8 }}>
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
          {/* 注意(2026-07): 只读模式下隐藏折叠按钮 */}
          {!readOnly && (
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
              onClick={handleToggleClick}
            >
              <CollapseIcon style={{ width: 14, height: 14 }} />
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

export default memo(EditorSubPipelineNode);
