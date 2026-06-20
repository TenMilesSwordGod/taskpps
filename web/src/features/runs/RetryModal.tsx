import { useMemo, useState } from 'react';
import { Modal, Spin, Switch, Tag, App, Empty } from 'antd';
import { RotateCcw, ArrowDown, GitBranch, Terminal } from 'lucide-react';
import { useDependencyTree, useRetryRun } from '@/api/runs';
import StatusTag from '@/components/StatusTag';
import type { TaskStatus } from '@/types';

interface RetryModalProps {
  open: boolean;
  runId: string;
  taskName: string;
  taskStatus?: TaskStatus;
  taskCommand?: string;
  onClose: () => void;
}

/**
 * Issue #72: 重试任务弹窗
 * - 展示原始命令（只读，不可编辑）
 * - 展示依赖树，可选择是否包含上游依赖
 * - 确认后调用 useRetryRun 触发重试
 */
export default function RetryModal({ open, runId, taskName, taskStatus, taskCommand, onClose }: RetryModalProps) {
  const { message } = App.useApp();
  const [includeUpstream, setIncludeUpstream] = useState(false);

  const { data: depTree, isLoading: depLoading } = useDependencyTree(
    open ? runId : undefined,
    open ? taskName : undefined,
  );

  const retryRun = useRetryRun();

  const upstreamTasks = useMemo(() => {
    if (!depTree?.tree) return [];
    return depTree.tree.filter((n) => n.upstream_of_target && n.name !== taskName);
  }, [depTree, taskName]);

  const tasksToRerun = useMemo(() => {
    const tasks = [taskName];
    if (includeUpstream) {
      tasks.push(...upstreamTasks.map((t) => t.name));
    }
    return tasks;
  }, [taskName, includeUpstream, upstreamTasks]);

  const handleConfirm = async () => {
    try {
      await retryRun.mutateAsync({
        runId,
        tasks: tasksToRerun,
        include_upstream: includeUpstream,
      });
      message.success(`已触发重试（${tasksToRerun.length} 个任务）`);
      onClose();
    } catch {
      message.error('重试触发失败');
    }
  };

  const handleClose = () => {
    setIncludeUpstream(false);
    onClose();
  };

  return (
    <Modal
      title={
        <div className="flex items-center gap-2">
          <RotateCcw size={16} className="text-blue-500" />
          <span>重试任务</span>
        </div>
      }
      open={open}
      onCancel={handleClose}
      onOk={handleConfirm}
      okText="确认重试"
      cancelText="取消"
      confirmLoading={retryRun.isPending}
      okButtonProps={{ icon: <RotateCcw size={14} /> }}
      destroyOnClose
      width={560}
    >
      <div className="flex flex-col gap-4 py-2">
        {/* 任务信息 */}
        <div className="flex items-center gap-3 flex-wrap">
          <span className="text-sm text-gray-500">任务</span>
          <span className="text-sm font-mono font-medium text-gray-800">{taskName}</span>
          {taskStatus && <StatusTag status={taskStatus} />}
        </div>

        {/* 原始命令（只读） */}
        {taskCommand && (
          <div>
            <div className="flex items-center gap-1.5 mb-1 text-xs text-gray-500">
              <Terminal size={12} />
              <span>原始命令（只读，按原样重跑）</span>
            </div>
            <pre className="bg-gray-50 border border-gray-200 rounded-md px-3 py-2 text-xs font-mono text-gray-700 overflow-x-auto whitespace-pre-wrap break-all">
              {taskCommand}
            </pre>
          </div>
        )}

        {/* 依赖树 */}
        {depLoading ? (
          <div className="flex items-center justify-center py-6">
            <Spin size="small" />
            <span className="ml-2 text-sm text-gray-400">加载依赖关系...</span>
          </div>
        ) : depTree && depTree.tree.length > 0 ? (
          <div>
            <div className="flex items-center gap-1.5 mb-2 text-xs text-gray-500">
              <GitBranch size={12} />
              <span>依赖关系</span>
            </div>
            <div className="border border-gray-200 rounded-md overflow-hidden">
              {depTree.tree.map((node) => {
                const isTarget = node.name === taskName;
                const isUpstream = node.upstream_of_target && !isTarget;
                return (
                  <div
                    key={node.name}
                    className="flex items-center gap-2 px-3 py-1.5 text-xs border-b border-gray-100 last:border-b-0"
                    style={{
                      paddingLeft: `${12 + node.level * 16}px`,
                      background: isTarget ? 'rgba(59,130,246,0.06)' : isUpstream && includeUpstream ? 'rgba(16,185,129,0.04)' : undefined,
                    }}
                  >
                    {isTarget ? (
                      <Tag color="blue" style={{ margin: 0, fontSize: 10, lineHeight: '16px', padding: '0 4px' }}>目标</Tag>
                    ) : isUpstream ? (
                      <Tag color={includeUpstream ? 'green' : 'default'} style={{ margin: 0, fontSize: 10, lineHeight: '16px', padding: '0 4px' }}>上游</Tag>
                    ) : (
                      <span className="inline-block w-8" />
                    )}
                    <span className={`font-mono ${isTarget ? 'font-semibold text-gray-800' : 'text-gray-600'}`}>
                      {node.name}
                    </span>
                    {isUpstream && includeUpstream && (
                      <ArrowDown size={10} className="text-emerald-500 rotate-[-90deg]" />
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        ) : (
          <Empty description="无依赖关系" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        )}

        {/* 包含上游依赖开关 */}
        {upstreamTasks.length > 0 && (
          <div className="flex items-center justify-between bg-gray-50 border border-gray-200 rounded-md px-3 py-2">
            <div className="flex flex-col">
              <span className="text-sm text-gray-700">包含上游依赖</span>
              <span className="text-xs text-gray-400">
                将同时重跑 {upstreamTasks.length} 个上游任务
              </span>
            </div>
            <Switch checked={includeUpstream} onChange={setIncludeUpstream} />
          </div>
        )}

        {/* 将重跑的任务列表 */}
        <div>
          <div className="text-xs text-gray-500 mb-1.5">将重跑以下任务：</div>
          <div className="flex flex-wrap gap-1.5">
            {tasksToRerun.map((t) => (
              <Tag
                key={t}
                color={t === taskName ? 'blue' : 'green'}
                style={{ fontFamily: 'monospace', fontSize: 11 }}
              >
                {t}
              </Tag>
            ))}
          </div>
        </div>
      </div>
    </Modal>
  );
}
