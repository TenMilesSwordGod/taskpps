import { useCallback, useEffect, useRef } from 'react';
import { Dropdown } from 'antd';
import type { MenuProps } from 'antd';
import {
  CopyOutlined,
  SnippetsOutlined,
  DeleteOutlined,
  InfoCircleOutlined,
  FileTextOutlined,
  FormOutlined,
} from '@ant-design/icons';
import { usePipelineEditorStore } from './stores/pipelineEditorStore';

/**
 * 画布右键菜单 — 节点/空白区域上下文操作
 *
 * 设计决策：
 * - 使用 Ant Design Dropdown 的 open+trigger=[] 模式手动控制显示/隐藏
 * - editMode=false 时菜单仅保留"查看属性"和"查看日志"（只读安全操作）
 * - 菜单关闭逻辑：点击菜单项 → closeContextMenu()；点击外部 → mousedown handler
 */

interface NodeContextMenuProps {
  onCopyNode?: (nodeId: string) => void;
  onDeleteNode?: (nodeId: string) => void;
  onViewProperties?: (nodeId: string) => void;
  onViewLogs?: (nodeId: string) => void;
  onAddStickyNote?: (nodeId: string | null) => void;
}

export default function NodeContextMenu({
  onCopyNode,
  onDeleteNode,
  onViewProperties,
  onViewLogs,
  onAddStickyNote,
}: NodeContextMenuProps) {
  const contextMenu = usePipelineEditorStore((s) => s.contextMenu);
  const closeContextMenu = usePipelineEditorStore((s) => s.closeContextMenu);
  const editMode = usePipelineEditorStore((s) => s.editMode);

  // 点击菜单外部时关闭
  useEffect(() => {
    if (!contextMenu) return;
    const handler = (e: MouseEvent) => {
      // 忽略菜单内部点击（由 Dropdown 自行处理）
      const target = e.target as HTMLElement;
      if (target.closest('.ant-dropdown-menu') || target.closest('.ant-dropdown')) return;
      closeContextMenu();
    };
    const timer = setTimeout(() => {
      document.addEventListener('mousedown', handler);
    }, 0);
    return () => {
      clearTimeout(timer);
      document.removeEventListener('mousedown', handler);
    };
  }, [contextMenu, closeContextMenu]);

  const handleMenuClick: MenuProps['onClick'] = useCallback(
    ({ key }) => {
      const nodeId = contextMenu?.nodeId;
      switch (key) {
        case 'copy-node':
          if (nodeId) onCopyNode?.(nodeId);
          break;
        case 'paste-node':
          break;
        case 'delete-node':
          if (nodeId) onDeleteNode?.(nodeId);
          break;
        case 'view-properties':
          if (nodeId) onViewProperties?.(nodeId);
          break;
        case 'view-logs':
          if (nodeId) onViewLogs?.(nodeId);
          break;
        case 'add-note':
          onAddStickyNote?.(nodeId ?? null);
          break;
      }
      closeContextMenu();
    },
    [contextMenu, onCopyNode, onDeleteNode, onViewProperties, onViewLogs, onAddStickyNote, closeContextMenu],
  );

  if (!contextMenu) return null;

  const hasNode = contextMenu.nodeId !== null;

  const nodeItems: MenuProps['items'] = [
    { key: 'copy-node', label: '复制节点', icon: <CopyOutlined />, disabled: !hasNode },
    { key: 'paste-node', label: '粘贴节点', icon: <SnippetsOutlined />, disabled: true },
    { type: 'divider' },
    { key: 'delete-node', label: '删除节点', icon: <DeleteOutlined />, danger: true, disabled: !hasNode },
    { type: 'divider' },
    { key: 'add-note', label: '添加便签', icon: <FormOutlined /> },
    { type: 'divider' },
    { key: 'view-properties', label: '查看属性', icon: <InfoCircleOutlined />, disabled: !hasNode },
    { key: 'view-logs', label: '查看日志', icon: <FileTextOutlined />, disabled: !hasNode },
  ];

  const readonlyItems: MenuProps['items'] = [
    { key: 'view-properties', label: '查看属性', icon: <InfoCircleOutlined />, disabled: !hasNode },
    { key: 'view-logs', label: '查看日志', icon: <FileTextOutlined />, disabled: !hasNode },
  ];

  const items = editMode ? nodeItems : readonlyItems;

  return (
    <Dropdown
      open
      trigger={[]}
      menu={{
        items,
        onClick: handleMenuClick,
      }}
      overlayStyle={{
        position: 'fixed',
        left: contextMenu.x,
        top: contextMenu.y,
      }}
    >
      <span />
    </Dropdown>
  );
}
