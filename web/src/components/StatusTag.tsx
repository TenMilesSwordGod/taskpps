import { Tag } from 'antd';
import type { RunStatus, TaskStatus } from '@/types';

type StatusType = RunStatus | TaskStatus;

/** 状态颜色映射 */
const STATUS_COLOR_MAP: Record<StatusType, string> = {
  pending: 'default',
  running: 'processing',
  success: 'success',
  failed: 'error',
  cancelled: 'warning',
  partial: 'purple',
  skipped: 'gold',
};

/** 状态中文标签 */
const STATUS_LABEL_MAP: Record<StatusType, string> = {
  pending: '等待中',
  running: '运行中',
  success: '成功',
  failed: '失败',
  cancelled: '已取消',
  partial: '部分完成',
  skipped: '已跳过',
};

interface StatusTagProps {
  status: StatusType;
}

/** 状态标签组件 */
export default function StatusTag({ status }: StatusTagProps) {
  return (
    <Tag color={STATUS_COLOR_MAP[status]}>
      {STATUS_LABEL_MAP[status]}
    </Tag>
  );
}
