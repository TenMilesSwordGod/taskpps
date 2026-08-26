import { DragEvent, useState, useCallback } from 'react';
import { Input, Collapse } from 'antd';
import { SearchOutlined, CloseOutlined, CheckOutlined, ReloadOutlined } from '@ant-design/icons';
import { TYPE_ICON, SENTINEL_ICON, TYPE_ICON_BG, FONT_SANS } from '@/features/pipelines/nodes/nodeTokens';
import { SubPipelineIcon, TaskIcon, PostParentIcon } from './icons';

/**
 * 右侧节点面板 — n8n 风格可拖拽节点列表
 * 支持:
 *   - 按分类折叠展示
 *   - 搜索过滤
 *   - 拖拽到画布新增节点
 *
 * v2 (2026-07): SVG 图标替换 emoji
 * v11 (2026-08): n8n 语汇统一 —— 图标改为「类型色圆角方块 + 白色 glyph」
 * （与画布节点卡片同款解剖）；Unicode 字符图标（▶ ⏹ ✕ ✓ ↻）全部退役；
 * 标签从 mono 改 sans（文字码仅保留 CMD/STEP/PLUGIN/INVOKE 标签本身 ——
 * 它们是拖拽识别与 e2e 契约，不是装饰）
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
const CARD_ICON_SIZE = 30;

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
        padding: '0 10px',
        border: '1px solid #E4E9F0',
        borderRadius: 8,
        background: '#ffffff',
        cursor: 'grab',
        userSelect: 'none',
        transition: 'background 150ms, transform 150ms, box-shadow 150ms',
      }}
      className="hover:bg-slate-50 hover:-translate-y-px hover:shadow-sm active:bg-slate-100"
    >
      {/* n8n 式图标块：类型色圆角方块 + 白色 glyph（与画布节点同款） */}
      <div
        aria-hidden
        style={{
          width: CARD_ICON_SIZE,
          height: CARD_ICON_SIZE,
          borderRadius: 7,
          backgroundColor: color,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          flexShrink: 0,
          color: '#FFFFFF',
        }}
      >
        {icon}
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontFamily: FONT_SANS, fontSize: 12.5, fontWeight: 600, color: '#525356' }}>
          {label}
        </div>
        <div style={{ fontSize: 10.5, color: '#71747A', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {description}
        </div>
      </div>
    </div>
  );
}

// v2 (2026-07): SVG 图标尺寸常量
const PALETTE_ICON_STYLE = { width: 16, height: 16 };

export default function NodePalette() {
  const [search, setSearch] = useState('');

  const filterCards = (cards: DraggableCardProps[]) => {
    if (!search) return cards;
    const lower = search.toLowerCase();
    return cards.filter(c => c.label.toLowerCase().includes(lower) || c.description.toLowerCase().includes(lower));
  };

  const flowCards: DraggableCardProps[] = filterCards([
    { type: 'startEnd', nodeType: 'startend', label: 'Start', description: '流程开始', icon: <SENTINEL_ICON.start style={{ fontSize: 15 }} />, color: TYPE_ICON_BG },
    { type: 'startEnd', nodeType: 'startend', label: 'End', description: '流程结束', icon: <SENTINEL_ICON.end style={{ fontSize: 13 }} />, color: TYPE_ICON_BG },
  ]);

  const containerCards: DraggableCardProps[] = filterCards([
    { type: 'subpipeline', nodeType: 'subpipeline', label: 'SubPipeline', description: '子流水线容器', icon: <SubPipelineIcon style={PALETTE_ICON_STYLE} />, color: TYPE_ICON_BG },
    { type: 'task', nodeType: 'task', label: 'Task', description: '任务容器', icon: <TaskIcon style={PALETTE_ICON_STYLE} />, color: TYPE_ICON_BG },
    { type: 'post_parent', nodeType: 'post_parent', label: 'Post 父容器', description: '后置动作容器', icon: <PostParentIcon style={PALETTE_ICON_STYLE} />, color: TYPE_ICON_BG },
  ]);

  const atomicCards: DraggableCardProps[] = filterCards([
    { type: 'task', nodeType: 'task_atomic_cmd', label: 'CMD', description: '命令执行', icon: <TYPE_ICON.command style={{ fontSize: 15 }} />, color: TYPE_ICON_BG },
    { type: 'task', nodeType: 'task_atomic_step', label: 'STEP', description: '步骤执行', icon: <TYPE_ICON.steps style={{ fontSize: 15 }} />, color: TYPE_ICON_BG },
    { type: 'task', nodeType: 'task_atomic_plugin', label: 'PLUGIN', description: '插件', icon: <TYPE_ICON.plugin style={{ fontSize: 15 }} />, color: TYPE_ICON_BG },
    { type: 'task', nodeType: 'task_atomic_invoke', label: 'INVOKE', description: '调用', icon: <TYPE_ICON.invoke style={{ fontSize: 15 }} />, color: TYPE_ICON_BG },
  ]);

  const postCards: DraggableCardProps[] = filterCards([
    { type: 'post_child', nodeType: 'post_child_on_fail', label: '失败后', description: '失败时触发', icon: <CloseOutlined style={{ fontSize: 13 }} />, color: TYPE_ICON_BG },
    { type: 'post_child', nodeType: 'post_child_on_success', label: '成功后', description: '成功时触发', icon: <CheckOutlined style={{ fontSize: 13 }} />, color: TYPE_ICON_BG },
    { type: 'post_child', nodeType: 'post_child_always', label: '始终', description: '始终触发', icon: <ReloadOutlined style={{ fontSize: 13 }} />, color: TYPE_ICON_BG },
  ]);

  const collapseItems = [
    {
      key: 'flow',
      label: <span style={{ fontSize: 12, fontWeight: 600, color: '#64748B', letterSpacing: 0.3 }}>流程控制</span>,
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
      label: <span style={{ fontSize: 12, fontWeight: 600, color: '#64748B', letterSpacing: 0.3 }}>容器</span>,
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
      label: <span style={{ fontSize: 12, fontWeight: 600, color: '#64748B', letterSpacing: 0.3 }}>基础任务</span>,
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
      label: <span style={{ fontSize: 12, fontWeight: 600, color: '#64748B', letterSpacing: 0.3 }}>Post 处理</span>,
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
    <div style={{ width: 264, height: '100%', display: 'flex', flexDirection: 'column', borderLeft: '1px solid #E4E9F0', background: '#FBFCFE' }}>
      {/* 标题栏 */}
      <div
        style={{
          padding: '10px 12px',
          borderBottom: '1px solid #E4E9F0',
          background: '#ffffff',
        }}
      >
        <span style={{ fontFamily: FONT_SANS, fontSize: 13, fontWeight: 600, color: '#525356' }}>节点面板</span>
      </div>

      {/* 搜索框 */}
      <div style={{ padding: '8px 12px' }}>
        <Input
          size="small"
          prefix={<SearchOutlined style={{ color: '#8D939E' }} />}
          placeholder="搜索节点..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          allowClear
          style={{ borderRadius: 8 }}
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
