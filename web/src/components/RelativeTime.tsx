import type { CSSProperties } from 'react';
import { useNow } from '@/hooks/useNow';

/** 相对时间文案：X秒前 / X分钟前 / X小时前 / X天前 */
function formatRelative(tsSec: number, nowSec: number): string {
  const diff = Math.floor(nowSec - tsSec);
  if (diff < 0) return '刚刚';
  if (diff < 60) return `${diff}秒前`;
  if (diff < 3600) return `${Math.floor(diff / 60)}分钟前`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}小时前`;
  return `${Math.floor(diff / 86400)}天前`;
}

/**
 * 相对时间展示组件（如"更新于 X秒前"）。
 * 内部独立按秒刷新，仅重渲染自身这一行文字，避免父级（卡片/页面）每秒整体重渲染造成抖动。
 */
export function RelativeTime({
  tsMs,
  prefix = '更新于',
  className,
  style,
}: {
  tsMs: number;
  prefix?: string;
  className?: string;
  style?: CSSProperties;
}) {
  const now = useNow(1000);
  if (!tsMs) return null;
  const text = formatRelative(Math.floor(tsMs / 1000), Math.floor(now / 1000));
  return (
    <span className={className} style={style} title={new Date(tsMs).toLocaleString('zh-CN')}>
      {prefix} {text}
    </span>
  );
}
