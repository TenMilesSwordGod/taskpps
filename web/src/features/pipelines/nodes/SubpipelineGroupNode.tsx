import type { NodeProps } from '@xyflow/react';
import { Handle, Position } from '@xyflow/react';
import { INK, FONT_SANS } from './nodeTokens';

interface SubpipelineGroupData extends Record<string, unknown> {
  label: string;
  taskCount: number;
  /** 执行策略（sequential→SEQ / parallel→PAR），v7 起由 usePipelineGraph 传入 */
  strategy?: string;
}

/**
 * 子流水线分组容器 —— v11 安静容器
 *
 * 为什么改（v7 实体卡 → v11 安静容器）：白色投影大卡让"容器"与"内容"
 * 抢视觉层次 —— n8n 画布的层级语法是"画布 < 分组 < 节点"，分组必须比
 * 节点更安静。极浅半透底 + 细边 + 无阴影；头部从"芯片堆砌"
 * （mono 粗体 + SEQ 徽章 + tasks 药丸）收敛为一行 sans 弱文本
 * 「名称 · SEQ · N tasks」。
 *
 * 保留的既有修复（不回退）：
 * - handle id 契约（top/top-out/bottom/exit）—— usePipelineGraph 边数据依赖
 * - v11 方位随 LR 流向迁移：top/top-out 在左缘、bottom/exit 在右缘
 * - 任务数文本 #71747A ≥4.5:1（v6 对比度结论，色值升级为 n8n 副标题色）
 */
export default function SubpipelineGroupNode({ data }: NodeProps) {
  const { label, taskCount, strategy } = data as unknown as SubpipelineGroupData;
  const strategyCode = strategy === 'parallel' ? 'PAR' : 'SEQ';

  return (
    <div
      style={{
        width: '100%',
        height: '100%',
        border: `1px solid #E4E9F0`,
        borderRadius: 14,
        // 半透浅底：分组比节点安静一层，点阵网格隐约透出
        background: 'rgba(255, 255, 255, 0.55)',
        position: 'relative',
        pointerEvents: 'none',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      {/* 头部：一行 sans 弱文本（名称 · 策略 · 任务数），无芯片 */}
      <div
        style={{
          display: 'flex',
          alignItems: 'baseline',
          gap: 7,
          padding: '9px 14px 0',
          fontFamily: FONT_SANS,
          whiteSpace: 'nowrap',
          pointerEvents: 'none',
        }}
      >
        <span
          style={{
            fontSize: 12,
            fontWeight: 600,
            color: '#64748B',
            letterSpacing: 0.1,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
          }}
        >
          {label}
        </span>
        <span style={{ fontSize: 10.5, fontWeight: 500, color: INK.textSecondary, letterSpacing: 0.2 }}>
          {strategyCode} · {taskCount} tasks
        </span>
      </div>

      {/* 外部入口 —— START / 上游 group 连入（target，左缘中心） */}
      <Handle
        id="top"
        type="target"
        position={Position.Left}
        className="!w-1.5 !h-1.5 !bg-slate-400 !border-0 !-left-[3px]"
        style={{ top: '50%' }}
      />
      {/* 内部出口 —— group → 首 task（source，左缘中心同位：
        外部线进左缘、内部线从左缘流向组内首任务） */}
      <Handle
        id="top-out"
        type="source"
        position={Position.Left}
        className="!w-1.5 !h-1.5 !bg-slate-400 !border-0 !-left-[3px]"
        style={{ top: '50%' }}
      />
      {/* 外部出口 —— group → __end__ / 下游 group（source，右缘中心） */}
      <Handle
        id="bottom"
        type="source"
        position={Position.Right}
        className="!w-1.5 !h-1.5 !bg-slate-400 !border-0 !-right-[3px]"
        style={{ top: '50%' }}
      />
      {/* 内部汇聚 —— 末 task / alt/no 路径汇入（target，右缘中心同位） */}
      <Handle
        id="exit"
        type="target"
        position={Position.Right}
        className="!w-1.5 !h-1.5 !bg-slate-500 !border-0 !-right-[3px]"
        style={{ top: '50%' }}
      />
    </div>
  );
}
