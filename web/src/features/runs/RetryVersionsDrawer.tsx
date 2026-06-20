import { useState } from 'react';
import { Drawer, Spin, Tag, Button, Empty, Modal, App, Tooltip } from 'antd';
import { History, Clock, Eye, Star, FileText } from 'lucide-react';
import dayjs from 'dayjs';
import { useRetryVersions, useSelectRetryReport, useRetryLogs } from '@/api/runs';
import StatusTag from '@/components/StatusTag';

interface RetryVersionsDrawerProps {
  open: boolean;
  runId: string;
  taskName: string;
  onClose: () => void;
}

function fmtDur(start: string | null, end: string | null): string {
  if (!start || !end) return '-';
  const ms = dayjs(end).diff(dayjs(start));
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s`;
  return `${Math.floor(s / 60)}m${s % 60}s`;
}

/**
 * Issue #72: 重试版本管理抽屉
 * - 展示任务的原始执行 (v0) 和所有重试版本
 * - 可选择某个版本作为"最终报告"
 * - 可查看每个版本的日志
 */
export default function RetryVersionsDrawer({ open, runId, taskName, onClose }: RetryVersionsDrawerProps) {
  const { message } = App.useApp();
  const [logRetryId, setLogRetryId] = useState<string | null>(null);

  const { data: versionsData, isLoading } = useRetryVersions(open ? runId : undefined);
  const selectReport = useSelectRetryReport();

  // 日志查看（仅重试版本使用 useRetryLogs，v0 原始版本的日志通过 SSE/主日志查看）
  const { data: logData, isLoading: logLoading } = useRetryLogs(
    logRetryId ? runId : undefined,
    logRetryId ?? undefined,
  );

  const retryList = versionsData?.task_retries?.[taskName] ?? [];
  const selectedRetryId = versionsData?.selected?.[taskName] ?? null;

  const handleSelect = async (retryId: string) => {
    try {
      await selectReport.mutateAsync({
        runId,
        retryId,
        taskName,
        selectedRetryId: retryId,
      });
      message.success('已设为最终版本');
    } catch {
      message.error('设置失败');
    }
  };

  return (
    <>
      <Drawer
        title={
          <div className="flex items-center gap-2">
            <History size={16} className="text-purple-500" />
            <span>版本历史</span>
            <span className="text-xs font-mono text-gray-400 truncate max-w-200px">{taskName}</span>
          </div>
        }
        open={open}
        onClose={onClose}
        width={480}
        destroyOnClose
      >
        {isLoading ? (
          <div className="flex items-center justify-center py-12">
            <Spin size="small" />
          </div>
        ) : retryList.length === 0 ? (
          <Empty description="暂无版本数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        ) : (
          <div className="flex flex-col gap-3">
            {retryList
              .slice()
              .sort((a, b) => b.retry_version - a.retry_version)
              .map((retry) => {
                const isOriginal = retry.retry_version === 0;
                // v0 原始版本：selectedRetryId 为 null 时选中；重试版本：id 匹配时选中
                const isSelected = isOriginal
                  ? selectedRetryId === null
                  : selectedRetryId === retry.id;
                const isFailed = retry.status === 'failed';
                const isRunning = retry.status === 'running';

                return (
                  <div
                    key={retry.id}
                    className={`rounded-lg border-2 px-3 py-2.5 transition-colors cursor-default ${
                      isSelected
                        ? 'border-blue-400 bg-blue-50'
                        : isFailed
                          ? 'border-red-200 bg-red-50/30'
                          : 'border-gray-200 bg-white hover:border-gray-300'
                    }`}
                  >
                    {/* 版本头 */}
                    <div className="flex items-center justify-between mb-1.5">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-semibold text-gray-800">
                          {isOriginal ? '原始版本' : `v${retry.retry_version}`}
                        </span>
                        <StatusTag status={retry.status} error={retry.error} />
                        {isSelected && (
                          <Tag color="blue" style={{ margin: 0, fontSize: 10, lineHeight: '18px', padding: '0 6px', display: 'inline-flex', alignItems: 'center', gap: 2 }}>
                            <Star size={10} /> 当前版本
                          </Tag>
                        )}
                        {isOriginal && (
                          <Tag style={{ margin: 0, fontSize: 10, lineHeight: '18px', padding: '0 6px', background: '#f3f4f6', color: '#6b7280', border: '1px solid #e5e7eb' }}>
                            首次执行
                          </Tag>
                        )}
                      </div>
                      {isRunning && <Spin size="small" />}
                    </div>

                    {/* 时间 + 耗时 */}
                    <div className="flex items-center gap-3 text-xs text-gray-400 mb-2">
                      {retry.started_at && (
                        <span className="flex items-center gap-1">
                          <Clock size={11} />
                          {dayjs(retry.started_at).format('MM-DD HH:mm:ss')}
                        </span>
                      )}
                      <span>{fmtDur(retry.started_at, retry.finished_at)}</span>
                      {retry.exit_code != null && (
                        <span className={retry.exit_code === 0 ? 'text-emerald-500' : 'text-red-500'}>
                          Exit {retry.exit_code}
                        </span>
                      )}
                    </div>

                    {/* 命令预览 */}
                    {retry.command && (
                      <div className="bg-gray-50 border border-gray-100 rounded px-2 py-1 mb-2 text-xs font-mono text-gray-500 overflow-hidden text-ellipsis whitespace-nowrap">
                        {retry.command}
                      </div>
                    )}

                    {/* 错误信息 */}
                    {retry.error && (
                      <div className="text-xs text-red-400 mb-2 truncate" title={retry.error}>
                        {retry.error}
                      </div>
                    )}

                    {/* 操作按钮 */}
                    <div className="flex items-center gap-2">
                      {!isSelected && retry.status !== 'running' && retry.status !== 'pending' && (
                        <Tooltip title={isOriginal ? '切回原始版本作为最终报告' : '将此版本设为最终报告'}>
                          <Button
                            size="small"
                            type="text"
                            icon={<Star size={13} />}
                            onClick={() => handleSelect(retry.id)}
                            loading={selectReport.isPending}
                          >
                            设为最终版本
                          </Button>
                        </Tooltip>
                      )}
                      {/* 重试版本通过 useRetryLogs 查看日志；v0 原始版本日志通过主日志查看 */}
                      {!isOriginal && (
                        <Button
                          size="small"
                          type="text"
                          icon={<Eye size={13} />}
                          onClick={() => setLogRetryId(retry.id)}
                        >
                          查看日志
                        </Button>
                      )}
                    </div>
                  </div>
                );
              })}
          </div>
        )}
      </Drawer>

      {/* 日志查看 Modal */}
      <Modal
        title={
          <div className="flex items-center gap-2">
            <FileText size={16} className="text-gray-500" />
            <span>重试日志</span>
            {logRetryId && (
              <span className="text-xs font-mono text-gray-400">
                {retryList.find((r) => r.id === logRetryId)?.task_name}
              </span>
            )}
          </div>
        }
        open={logRetryId !== null}
        onCancel={() => setLogRetryId(null)}
        footer={null}
        width={800}
        destroyOnClose
      >
        {logLoading ? (
          <div className="flex items-center justify-center py-8">
            <Spin size="small" />
          </div>
        ) : logData?.exists ? (
          <pre
            className="bg-gray-900 text-gray-100 rounded-lg p-4 text-xs font-mono overflow-auto"
            style={{ maxHeight: '60vh', whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}
          >
            {logData.content || '(空日志)'}
          </pre>
        ) : (
          <Empty description="日志文件不存在" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        )}
      </Modal>
    </>
  );
}
