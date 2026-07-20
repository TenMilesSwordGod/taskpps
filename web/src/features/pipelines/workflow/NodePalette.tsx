import { DragEvent, useState, useCallback } from 'react';
import { Input, Collapse } from 'antd';
import { SearchOutlined } from '@ant-design/icons';
import type { TaskType } from '@/types';
import { TYPE_COLOR, FONT_MONO } from '@/features/pipelines/nodes/nodeTokens';
import { SubPipelineIcon, TaskIcon, PostParentIcon, CmdIcon, StepIcon, PluginIcon, InvokeIcon } from './icons';

/**
 * 右侧节点面板 — n8n 风格可拖拽节点列表
 * 支持:
 *   - 按分类折叠展示
 *   - 搜索过滤
 *   - 拖拽到画布新增节点
 *
 * v2 (2026-07): SVG 图标替换 emoji
 */

interface DraggableCardProps {
  type: string;
  nodeType: string;
  label: string;
  description: string;
  icon: React.ReactNode;
  color: string;
}

const CARD_HEIGHT = 52;
const CARD_ICON_SIZE = 22;

function DraggableCard({ type, nodeType, label, description, icon, color }: DraggableCardProps) {
  const handleDragStart = useCallback(
    (event: DragEvent) => {
      event.dataTransfer.setData('application/reactflow-type', type);
      event.dataTransfer.setData('application/reactflow-node-type', nodeType);
      event.dataTransfer.setData('application/reactflow-label', label);
      event.dataTransfer.effectAllowed = 'move';
    },
    [type, nodeType, label],
  );

  return (
    <div
      draggable
      onDragStart={handleDragStart}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        height: CARD_HEIGHT,
        padding: '0 12px',
        border: '1px solid #e5e7eb',
        borderRadius: 6,
        background: '#ffffff',
        cursor: 'grab',
        userSelect: 'none',
        transition: 'background 150ms, transform 150ms',
      }}
      className="hover:bg-blue-50 hover:-translate-y-px active:bg-blue-100 active:scale-95"
    >
      <div
        style={{
          width: CARD_ICON_SIZE,
          height: CARD_ICON_SIZE,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: 16,
          color,
          flexShrink: 0,
        }}
      >
        {icon}
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontFamily: FONT_MONO, fontSize: 12, fontWeight: 600, color: '#0f172a' }}>
          {label}
        </div>
        <div style={{ fontSize: 10, color: '#94a3b8', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {description}
        </div>
      </div>
    </div>
  );
}

// v2 (2026-07): SVG 图标尺寸常量
const PALETTE_ICON_STYLE = { width: 18, height: 18 };

export default function NodePalette() {
  const [search, setSearch] = useState('');

  const filterCards = (cards: DraggableCardProps[]) => {
    if (!search) return cards;
    const lower = search.toLowerCase();
    return cards.filter(c => c.label.toLowerCase().includes(lower) || c.description.toLowerCase().includes(lower));
  };

  const flowCards: DraggableCardProps[] = filterCards([
    { type: 'startEnd', nodeType: 'startend', label: 'Start', description: '流程开始', icon: <span style={{ fontSize: 16 }}>▶</span>, color: '#10B981' },
    { type: 'startEnd', nodeType: 'startend', label: 'End', description: '流程结束', icon: <span style={{ fontSize: 16 }}>⏹</span>, color: '#94A3B8' },
  ]);

  const containerCards: DraggableCardProps[] = filterCards([
    { type: 'subpipeline', nodeType: 'subpipeline', label: 'SubPipeline', description: '蓝色虚线容器', icon: <SubPipelineIcon style={{ ...PALETTE_ICON_STYLE, color: '#3b82f6' }} />, color: '#3b82f6' },
    { type: 'task', nodeType: 'task', label: 'Task', description: '绿色虚线容器', icon: <TaskIcon style={{ ...PALETTE_ICON_STYLE, color: '#22c55e' }} />, color: '#22c55e' },
    { type: 'post_parent', nodeType: 'post_parent', label: 'Post 父容器', description: '红色虚线容器', icon: <PostParentIcon style={{ ...PALETTE_ICON_STYLE, color: '#ef4444' }} />, color: '#ef4444' },
  ]);

  const atomicCards: DraggableCardProps[] = filterCards([
    { type: 'task', nodeType: 'task_atomic_cmd', label: 'CMD', description: '命令执行', icon: <CmdIcon style={{ ...PALETTE_ICON_STYLE, color: TYPE_COLOR.command }} />, color: TYPE_COLOR.command },
    { type: 'task', nodeType: 'task_atomic_step', label: 'STEP', description: '步骤执行', icon: <StepIcon style={{ ...PALETTE_ICON_STYLE, color: TYPE_COLOR.steps }} />, color: TYPE_COLOR.steps },
    { type: 'task', nodeType: 'task_atomic_plugin', label: 'PLUGIN', description: '插件', icon: <PluginIcon style={{ ...PALETTE_ICON_STYLE, color: TYPE_COLOR.plugin }} />, color: TYPE_COLOR.plugin },
    { type: 'task', nodeType: 'task_atomic_invoke', label: 'INVOKE', description: '调用', icon: <InvokeIcon style={{ ...PALETTE_ICON_STYLE, color: TYPE_COLOR.invoke }} />, color: TYPE_COLOR.invoke },
  ]);

  const postCards: DraggableCardProps[] = filterCards([
    { type: 'post_child', nodeType: 'post_child_on_fail', label: 'on_fail 子容器', description: '失败时触发', icon: <span style={{ fontSize: 16 }}>✕</span>, color: '#ef4444' },
    { type: 'post_child', nodeType: 'post_child_on_success', label: 'on_success 子容器', description: '成功时触发', icon: <span style={{ fontSize: 16 }}>✓</span>, color: '#22c55e' },
    { type: 'post_child', nodeType: 'post_child_always', label: 'always 子容器', description: '始终触发', icon: <span style={{ fontSize: 16 }}>↻</span>, color: '#6b7280' },
  ]);

  const collapseItems = [
    {
      key: 'flow',
      label: <span style={{ fontSize: 12, fontWeight: 700, color: '#6b7280', letterSpacing: 0.5 }}>流程控制</span>,
      children: (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {flowCards.map((c) => (
            <DraggableCard key={c.label} {...c} />
          ))}
        </div>
      ),
    },
    {
      key: 'container',
      label: <span style={{ fontSize: 12, fontWeight: 700, color: '#6b7280', letterSpacing: 0.5 }}>容器</span>,
      children: (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {containerCards.map((c) => (
            <DraggableCard key={c.label} {...c} />
          ))}
        </div>
      ),
    },
    {
      key: 'atomic',
      label: <span style={{ fontSize: 12, fontWeight: 700, color: '#6b7280', letterSpacing: 0.5 }}>原子行为</span>,
      children: (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {atomicCards.map((c) => (
            <DraggableCard key={c.label} {...c} />
          ))}
        </div>
      ),
    },
    {
      key: 'post',
      label: <span style={{ fontSize: 12, fontWeight: 700, color: '#6b7280', letterSpacing: 0.5 }}>Post 处理</span>,
      children: (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {postCards.map((c) => (
            <DraggableCard key={c.label} {...c} />
          ))}
        </div>
      ),
    },
  ];

  return (
    <div style={{ width: 280, height: '100%', display: 'flex', flexDirection: 'column', borderLeft: '1px solid #f0f0f0', background: '#fafafa' }}>
      {/* 标题栏 */}
      <div
        style={{
          padding: '10px 12px',
          borderBottom: '1px solid #f0f0f0',
          background: '#ffffff',
        }}
      >
        <span style={{ fontSize: 13, fontWeight: 600, color: '#374151' }}>节点面板</span>
      </div>

      {/* 搜索框 */}
      <div style={{ padding: '8px 12px' }}>
        <Input
          size="small"
          prefix={<SearchOutlined style={{ color: '#94a3b8' }} />}
          placeholder="搜索节点..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          allowClear
          style={{ borderRadius: 6 }}
        />
      </div>

      {/* 分类折叠列表 */}
      <div style={{ flex: 1, overflow: 'auto', padding: '0 8px 8px' }}>
        <Collapse
          defaultActiveKey={['flow', 'container', 'atomic', 'post']}
          items={collapseItems}
          size="small"
          style={{ background: 'transparent', border: 'none' }}
          expandIconPosition="end"
        />
      </div>
    </div>
  );
}
