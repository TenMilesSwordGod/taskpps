import { useCallback, useRef } from 'react';
import { Terminal, Braces, Layers, Puzzle, GitBranch, Package, Key, Search, ChevronLeft } from 'lucide-react';
import { usePipelineEditorStore } from './stores/pipelineEditorStore';

/**
 * 左侧节点面板 — N8N 风格暗色侧边栏，按 Task 类型分组展示可拖拽节点
 *
 * 设计决策：
 * - 使用 @xyflow/react 的 application/reactflow MIME 类型传递拖拽数据
 * - 分组逻辑：按语义归为 4 组（命令/调用、步骤/插件、版本控制/仓库、远程连接）
 * - 颜色从 design-tokens.json task_type_colors 读取
 * - 面板宽度 260px（展开）/ 40px（折叠），使用 CSS transition 动画
 */

interface TaskTypeItem {
  type: string;
  label: string;
  color: string;
  icon: typeof Terminal;
}

/** 7 种 Task 类型按 4 组组织 */
const TASK_TYPE_GROUPS: { key: string; label: string; items: TaskTypeItem[] }[] = [
  {
    key: 'cmd-invoke',
    label: '命令与调用',
    items: [
      { type: 'command', label: '命令', color: '#4C6EF5', icon: Terminal },
      { type: 'invoke', label: '调用', color: '#7950F2', icon: Braces },
    ],
  },
  {
    key: 'step-plugin',
    label: '步骤与插件',
    items: [
      { type: 'steps', label: '步骤', color: '#15AABF', icon: Layers },
      { type: 'plugin', label: '插件', color: '#F06595', icon: Puzzle },
    ],
  },
  {
    key: 'vcs-repo',
    label: '版本控制与仓库',
    items: [
      { type: 'git', label: 'Git', color: '#F76707', icon: GitBranch },
      { type: 'nexus', label: 'Nexus', color: '#20C997', icon: Package },
    ],
  },
  {
    key: 'remote',
    label: '远程连接',
    items: [
      { type: 'ssh', label: 'SSH', color: '#74B816', icon: Key },
    ],
  },
];

export default function NodePanel() {
  const nodePanelOpen = usePipelineEditorStore((s) => s.nodePanelOpen);
  const toggleNodePanel = usePipelineEditorStore((s) => s.toggleNodePanel);
  const editMode = usePipelineEditorStore((s) => s.editMode);
  const searchRef = useRef<HTMLInputElement>(null);

  const onDragStartHandler = useCallback(
    (event: React.DragEvent<HTMLDivElement>, item: TaskTypeItem) => {
      event.dataTransfer.setData(
        'application/reactflow',
        JSON.stringify({
          taskType: item.type,
          label: item.label,
          color: item.color,
        }),
      );
      event.dataTransfer.effectAllowed = 'move';
    },
    [],
  );

  // 只读模式或面板关闭时隐藏
  if (!editMode || !nodePanelOpen) return null;

  return (
    <div
      className="flex-shrink-0 flex flex-col h-full overflow-hidden"
      style={{
        width: 260,
        backgroundColor: '#1A1B1E',
        transition: 'width 250ms cubic-bezier(0.4, 0, 0.2, 1)',
      }}
    >
      {/* Header */}
      <div
        className="flex items-center justify-between shrink-0 px-3"
        style={{ height: 48, borderBottom: '1px solid #2C2E33' }}
      >
        <span
          style={{
            fontFamily: 'ui-monospace, monospace',
            fontSize: 13,
            fontWeight: 600,
            color: '#C1C2C5',
          }}
        >
          节点面板
        </span>
        <button
          onClick={toggleNodePanel}
          className="flex items-center justify-center rounded-md hover:bg-[#25262B] transition-colors"
          style={{ width: 28, height: 28, background: 'none', border: 'none', cursor: 'pointer' }}
        >
          <ChevronLeft size={16} color="#909296" />
        </button>
      </div>

      {/* Search */}
      <div className="px-3 py-2 shrink-0">
        <div
          className="flex items-center gap-2 rounded-md px-2"
          style={{ height: 32, backgroundColor: '#25262B', border: '1px solid #373A40' }}
        >
          <Search size={14} color="#909296" />
          <input
            ref={searchRef}
            placeholder="搜索节点..."
            className="flex-1 bg-transparent border-none outline-none text-sm"
            style={{ color: '#C1C2C5', fontSize: 12 }}
          />
        </div>
      </div>

      {/* Groups */}
      <div className="flex-1 overflow-y-auto px-2 py-1">
        {TASK_TYPE_GROUPS.map((group) => (
          <div key={group.key} className="mb-3">
            <div
              className="px-2 py-1 select-none"
              style={{
                fontFamily: 'ui-monospace, monospace',
                fontSize: 11,
                fontWeight: 600,
                color: '#909296',
                letterSpacing: '0.05em',
                textTransform: 'uppercase',
              }}
            >
              {group.label}
            </div>
            {group.items.map((item) => (
              <div
                key={item.type}
                draggable
                onDragStart={(e) => onDragStartHandler(e, item)}
                className="flex items-center gap-3 px-3 cursor-grab active:cursor-grabbing select-none rounded-lg my-0.5 transition-colors"
                style={{ height: 40 }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.backgroundColor = '#25262B';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.backgroundColor = 'transparent';
                }}
              >
                {/* 色标圆点 */}
                <div
                  style={{
                    width: 8,
                    height: 8,
                    borderRadius: '50%',
                    backgroundColor: item.color,
                    flexShrink: 0,
                  }}
                />
                {/* 图标 */}
                <item.icon size={18} color="#909296" />
                {/* 名称 */}
                <span
                  style={{
                    fontFamily: 'ui-monospace, monospace',
                    fontSize: 13,
                    fontWeight: 500,
                    color: '#C1C2C5',
                  }}
                >
                  {item.label}
                </span>
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
