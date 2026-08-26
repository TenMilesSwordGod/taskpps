import { memo } from 'react';
import { Handle, Position } from '@xyflow/react';
import { Tooltip } from 'antd';
import type { TaskYAML, TaskStatus } from '@/types';
import { useAppStore } from '@/stores/appStore';
import {
  NODE_SIZE,
  INK,
  CARD_SHADOW,
  CARD_SHADOW_ELEVATED,
  STATUS_COLOR,
  STATUS_BADGE,
  STATUS_BADGE_BG,
  STATUS_LABEL,
  TYPE_ICON,
  TYPE_ICON_BG,
  TYPE_LABEL,
  FONT_MONO,
  FONT_SANS,
} from './nodeTokens';
import { inferTaskType, summarizeTask } from './taskVisual';

// v7 (2026-08): inferTaskType/summarizeTask/tintOf 抽至 taskVisual.ts 共享
// （编辑模式 EditorTaskNode 同步使用，消除双实现漂移）

/**
 * 运行中边框脉冲（v5: 蓝色系，蓝=进行中业界惯例；v11 沿用）
 */
const pulseStyle = `
@keyframes task-border-pulse {
  0%, 100% { border-color: #3B82F6; box-shadow: 0 0 0 2px rgba(59,130,246,0.15); }
  50% { border-color: #93C5FD; box-shadow: 0 0 0 4px rgba(59,130,246,0.07); }
}
`;

interface TaskNodeData {
  task: TaskYAML;
  subpipelineName: string;
  status?: TaskStatus;
  order?: number;
  [key: string]: unknown;
}

/**
 * 任务节点 —— v11 n8n 卡片（视觉世界替换，用户反馈"像 AI 生成的"）
 *
 * 与 v7-v10 的关键差异：
 * - 图标块内是白色 glyph 图标（TYPE_ICON），不再是三字母文字码
 *   （文字码是"AI 生成感"的最大来源；n8n 图标块永远是服务 glyph）
 * - 状态走 n8n 执行态语汇：边框着色 + 右上角圆形徽章（✓/✗/…），
 *   取代"背景软染 + 左缘色条"（同时消除 >1px 彩色 border-left）
 * - cancelled 双通道：灰色实边框 + 虚线外环（色弱可辨，延续 v6 结论）
 * - handles 左入右出（LR 水平流向，与 dagre rankdir=LR 配套）
 */
function TaskNodeComponent({ data, id }: { data: TaskNodeData; id: string }) {
  const { task, status } = data;
  const taskType = inferTaskType(task);
  const summary = summarizeTask(task);
  const selectedNodeId = useAppStore((s) => s.selectedNodeId);
  const setSelectedNodeId = useAppStore((s) => s.setSelectedNodeId);
  const isSelected = selectedNodeId === id;
  const isRunning = status === 'running';
  const isCancelled = status === 'cancelled';
  const IconGlyph = TYPE_ICON[taskType];
  // pending 与无状态同样静默（默认态零噪音）；其余状态边框着色
  const statusBorder =
    status && status !== 'pending' ? STATUS_COLOR[status] : undefined;
  const BadgeGlyph = status ? STATUS_BADGE[status] : undefined;

  const borderColor = isSelected ? INK.accent : statusBorder ?? INK.border;

  return (
    <>
      {isRunning && <style>{pulseStyle}</style>}

      {/* v11: 端口点隐藏由 PipelineGraph 的 .wf-viewer 作用域 CSS 统一处理；
          handle 左入右出（LR） */}
      <Handle
        type="target"
        position={Position.Left}
        className="!w-1.5 !h-1.5 !bg-slate-300 !border-0 !-left-[3px]"
      />

      <Tooltip
        title={
          <span style={{ fontFamily: FONT_MONO, fontSize: 11 }}>
            {task.name} · {TYPE_LABEL[taskType]}
            {summary ? ` · ${summary}` : ''}
            {status ? ` · ${STATUS_LABEL[status]}` : ''}
          </span>
        }
      >
        <div
          data-testid="task-card"
          onClick={(e) => {
            e.stopPropagation();
            setSelectedNodeId(id);
          }}
          className="relative flex items-center bg-white cursor-pointer select-none"
          style={{
            width: NODE_SIZE.TASK_W,
            height: NODE_SIZE.TASK_H,
            border: `1.5px solid ${borderColor}`,
            // cancelled 双通道：虚线边框（颜色之外的第二辨识通道）
            borderStyle: isCancelled && !isSelected ? 'dashed' : 'solid',
            borderRadius: 10,
            backgroundColor: INK.card,
            boxShadow: isSelected
              ? `0 0 0 2px ${INK.accent}55, ${CARD_SHADOW_ELEVATED}`
              : CARD_SHADOW,
            animation: isRunning ? 'task-border-pulse 1.6s ease-in-out infinite' : undefined,
            padding: '0 12px 0 10px',
            gap: 10,
          }}
        >
          {/* 左侧类型图标块：石墨实底 + 白色 glyph（v11.1: 去类型色，统一石墨） */}
          <div
            aria-hidden
            style={{
              width: 36,
              height: 36,
              borderRadius: 8,
              backgroundColor: TYPE_ICON_BG,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
            }}
          >
            <IconGlyph style={{ fontSize: 17, color: '#FFFFFF' }} />
          </div>

          {/* 右侧两行：任务名（sans）+ 命令摘要（mono，代码语义） */}
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'center',
              minWidth: 0,
              gap: 2,
            }}
          >
            <span
              style={{
                fontFamily: FONT_SANS,
                fontSize: 13,
                fontWeight: 600,
                color: INK.textPrimary,
                letterSpacing: -0.1,
                lineHeight: 1.25,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}
            >
              {task.name}
            </span>
            {summary && (
              <span
                style={{
                  fontFamily: FONT_MONO,
                  fontSize: 10.5,
                  color: INK.textSecondary,
                  lineHeight: 1.2,
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                  maxWidth: NODE_SIZE.TASK_W - 36 - 34,
                }}
              >
                {summary}
              </span>
            )}
          </div>

          {/* 状态角标：右上角圆形徽章（n8n 执行态语汇），白描边压在卡片角上 */}
          {BadgeGlyph && (
            <span
              aria-label={STATUS_LABEL[status]}
              role="img"
              style={{
                position: 'absolute',
                top: -7,
                right: -7,
                width: 17,
                height: 17,
                borderRadius: '50%',
                backgroundColor: STATUS_BADGE_BG[status!],
                border: '1.5px solid #FFFFFF',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                boxShadow: '0 1px 2px rgba(15, 23, 42, 0.18)',
              }}
            >
              <BadgeGlyph style={{ fontSize: 9, color: '#FFFFFF' }} />
            </span>
          )}
        </div>
      </Tooltip>

      <Handle
        type="source"
        position={Position.Right}
        className="!w-1.5 !h-1.5 !bg-slate-300 !border-0 !-right-[3px]"
      />
    </>
  );
}

export default memo(TaskNodeComponent);
