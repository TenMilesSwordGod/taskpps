import { useRef, useState, useCallback, useEffect } from 'react';
import { Popover, Skeleton, Input } from 'antd';
import { SearchOutlined } from '@ant-design/icons';
import type { ReactNode } from 'react';

/** 面包屑切换选项 */
export interface BreadcrumbSwitchOption {
  key: string;
  label: string;
  /** 悬浮文字提示（用于截断项） */
  tooltip?: string;
}

/** 单个面包屑项 */
export interface BreadcrumbSwitchItem {
  label: string;
  /** 点击跳转链接 */
  href?: string;
  /** 点击回调 */
  onClick?: () => void;
  /** 悬浮浮窗内选项列表（有此项时触发悬浮浮窗） */
  options?: BreadcrumbSwitchOption[];
  /** 当前选中项的 key */
  currentKey?: string;
  /** 切换回调 */
  onSwitch?: (key: string) => void;
  /** 选项列表是否加载中 */
  loading?: boolean;
  /** 浮窗标题文本 */
  popoverTitle?: string;
  /** 浮窗打开时的回调（用于按需加载数据） */
  onPopoverOpen?: () => void;
}

interface BreadcrumbSwitcherProps {
  items: BreadcrumbSwitchItem[];
}

/**
 * 面包屑悬浮切换组件。
 * 渲染面包屑样式项列表；有 options 的项悬停 300ms 后弹出浮窗，
 * 选择后触发 onSwitch，同时在浮窗内支持搜索过滤。
 */
export default function BreadcrumbSwitcher({ items }: BreadcrumbSwitcherProps) {
  return (
    <nav aria-label="面包屑" className="flex items-center text-sm text-gray-500 -ml-1">
      {items.map((item, idx) => (
        <BreadcrumbItem key={idx} item={item} isLast={idx === items.length - 1} />
      ))}
    </nav>
  );
}

/** 单个面包屑项 */
function BreadcrumbItem({
  item,
  isLast,
}: {
  item: BreadcrumbSwitchItem;
  isLast: boolean;
}) {
  const { label, href, onClick, onSwitch, options, loading } = item;

  // 无浮窗切换能力（无 onSwitch 且无有效 options）→ 普通链接或纯文本
  // v1 (2026-07): onSwitch/loading 存在时即使 options 为空也要渲染为 hover 项
  // loading 态需要 hover 能力以展示骨架
  if (!onSwitch && !loading && (!options || options.length === 0)) {
    const commonClass =
      'px-1 py-0.5 rounded transition-colors' +
      (href || onClick ? ' hover:bg-blue-50 hover:text-blue-600 cursor-pointer' : '');

    const inner = href ? (
      <a className={commonClass} href={href}>
        {label}
      </a>
    ) : onClick ? (
      <span className={commonClass} onClick={onClick}>
        {label}
      </span>
    ) : (
      <span className={`${commonClass}${isLast ? ' text-gray-800 font-medium' : ''}`}>{label}</span>
    );

    return (
      <span className="flex items-center">
        {inner}
        {!isLast && <span className="mx-1 text-gray-300">/</span>}
      </span>
    );
  }

  // 有浮窗选项 → 悬浮切换
  return (
    <BreadcrumbHoverItem item={item} isLast={isLast} />
  );
}

/** 带悬浮浮窗的面包屑项 */
function BreadcrumbHoverItem({
  item,
  isLast,
}: {
  item: BreadcrumbSwitchItem;
  isLast: boolean;
}) {
  const { label, options, currentKey, onSwitch, loading, popoverTitle, onPopoverOpen } = item;
  const [open, setOpen] = useState(false);
  const [searchText, setSearchText] = useState('');
  const [visibleCount, setVisibleCount] = useState(20);
  const leaveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const popoverRef = useRef<HTMLDivElement>(null);
  // 仅在首次打开时触发回调（后续 hover 不再重复请求）
  const openedRef = useRef(false);

  const filtered = searchText.trim()
    ? options!.filter((o) => o.label.toLowerCase().includes(searchText.toLowerCase()))
    : options!;

  const visible = filtered.slice(0, visibleCount);
  const hasMore = visibleCount < filtered.length;

  /** 滚动时加载更多 */
  const handleScroll = useCallback(
    (e: React.UIEvent<HTMLDivElement>) => {
      if (!hasMore) return;
      const target = e.currentTarget;
      if (target.scrollHeight - target.scrollTop - target.clientHeight < 30) {
        setVisibleCount((prev) => prev + 20);
      }
    },
    [hasMore],
  );

  /** 选项切换 */
  const handleSelect = useCallback(
    (key: string) => {
      onSwitch?.(key);
      setOpen(false);
    },
    [onSwitch],
  );

  /** 清理离开定时器 */
  const clearLeaveTimer = useCallback(() => {
    if (leaveTimerRef.current) {
      clearTimeout(leaveTimerRef.current);
      leaveTimerRef.current = null;
    }
  }, []);

  // 关闭时重置搜索和分页（延迟，等动画结束）
  useEffect(() => {
    if (!open) {
      const t = setTimeout(() => {
        setSearchText('');
        setVisibleCount(20);
      }, 200);
      return () => clearTimeout(t);
    }
  }, [open]);

  // 标题行（搜索框，或加载骨架）
  const header: ReactNode = loading ? (
    <Skeleton active paragraph={{ rows: 6 }} title={false} />
  ) : (
    <div className="flex flex-col gap-2 min-w-[200px]" data-testid="popover-content">
      {popoverTitle && (
        <div className="text-xs text-gray-400 truncate">{popoverTitle}</div>
      )}
      <Input
        size="small"
        prefix={<SearchOutlined />}
        placeholder="搜索..."
        value={searchText}
        onChange={(e) => {
          setSearchText(e.target.value);
          setVisibleCount(20);
        }}
        allowClear
        data-testid="popover-search"
      />
      <div
        className="max-h-[320px] overflow-y-auto"
        onScroll={handleScroll}
        data-testid="popover-list"
      >
        {visible.length === 0 ? (
          <div className="text-gray-400 text-center py-2" data-testid="popover-empty">
            无匹配结果
          </div>
        ) : (
          visible.map((opt) => (
            <div
              key={opt.key}
              data-testid={`popover-option-${opt.key}`}
              className={`flex items-center gap-2 px-2 py-1 cursor-pointer rounded text-sm transition-colors hover:bg-blue-50 ${
                opt.key === currentKey ? 'bg-blue-50 text-blue-600' : ''
              }`}
              onClick={() => handleSelect(opt.key)}
              title={opt.tooltip || opt.label}
            >
              <span
                className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                  opt.key === currentKey ? 'bg-blue-500' : 'bg-transparent'
                }`}
                data-testid={`dot-${opt.key}`}
              />
              <span className="truncate">{opt.label}</span>
            </div>
          ))
        )}
        {hasMore && (
          <div className="text-center text-xs text-gray-400 py-1">
            滚动加载更多 ({visibleCount}/{filtered.length})
          </div>
        )}
      </div>
      <div className="text-xs text-gray-400 pt-1 border-t border-gray-100">
        共 {filtered.length} 项
        {searchText && ` (筛选自 ${options!.length})`}
      </div>
    </div>
  );

  return (
    <span className="flex items-center">
      <Popover
        content={<div ref={popoverRef}>{header}</div>}
        trigger={['hover']}
        mouseEnterDelay={0.3}
        mouseLeaveDelay={0.15}
        open={open}
        onOpenChange={(v) => {
          clearLeaveTimer();
          setOpen(v);
          if (v && !openedRef.current && onPopoverOpen) {
            openedRef.current = true;
            onPopoverOpen();
          }
        }}
        placement="bottomLeft"
        overlayStyle={{ maxWidth: 360 }}
        destroyOnHidden
      >
        <span
          className="px-1 py-0.5 rounded transition-colors hover:bg-blue-50 hover:text-blue-600 cursor-pointer underline decoration-dotted"
          data-testid={`crumb-hover-${label}`}
        >
          {label}
        </span>
      </Popover>
      {!isLast && <span className="mx-1 text-gray-300">/</span>}
    </span>
  );
}
