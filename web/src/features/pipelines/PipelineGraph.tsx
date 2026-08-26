import { useCallback, useEffect, useRef } from 'react';
import {
  ReactFlow,
  useReactFlow,
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  Panel,
  type NodeMouseHandler,
  type Node,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import TaskNode from './nodes/TaskNode';
import SubpipelineGroupNode from './nodes/SubpipelineGroupNode';
import PostTaskNode from './nodes/PostTaskNode';
import { StartNode, EndNode } from './nodes/StartEndNode';
import DecisionNode from './nodes/DecisionNode';
import EdgeLegend from './nodes/EdgeLegend';
import { usePipelineGraph } from './hooks/usePipelineGraph';
import { useAppStore } from '@/stores/appStore';
import { STATUS_COLOR, INK } from './nodes/nodeTokens';
import type { PipelineDetail, TaskStatus } from '@/types';

/** Start/End 节点包装组件 */
function StartEndNodeWrapper(props: { data: { variant: 'start' | 'end'; [key: string]: unknown } }) {
  return props.data.variant === 'start'
    ? <StartNode data={props.data as { variant: 'start' }} />
    : <EndNode data={props.data as { variant: 'end' }} />;
}

// v6 (2026-08): critique P2 — handle 点击热区扩展。
// 实测全部 handle 渲染尺寸仅 ~4.2×4.2px（远低于 24px 可点下限）；
// ::after 负 inset 在不改变视觉小点的前提下扩大命中区域（标准技巧）
// v10 (2026-08): n8n 化 —— 查看模式是只读画布，端口点全部隐藏（n8n 画布无端口点），
// 边仍锚定在原 handle 位置；作用域限定 .wf-viewer，不影响编辑模式画布
const handleHotzoneStyle = `
.wf-viewer .react-flow__handle { opacity: 0 !important; }
.react-flow__handle::after {
  content: '';
  position: absolute;
  inset: -9px;
}
`;

/** 注册自定义节点类型 */
const nodeTypes = {
  taskNode: TaskNode,
  subpipelineGroup: SubpipelineGroupNode,
  postTask: PostTaskNode,
  startEnd: StartEndNodeWrapper,
  decisionNode: DecisionNode,
};

/** MiniMap 节点颜色 —— v11.1: 石墨中性（与画布节点一致；仅状态时用语义色）
 * 为什么不用类型色：全 CMD 流水线的小地图会变成一片绿块（用户反馈"绿色很丑"）
 */
function miniMapNodeColor(node: Node): string {
  if (node.type === 'startEnd') {
    return '#343A43';
  }
  if (node.type === 'decisionNode') return '#C6CCD8';
  if (node.type === 'subpipelineGroup') return '#C6CCD8';
  if (node.type === 'postTask') return '#C6CCD8';
  if (node.type === 'taskNode') {
    const status = node.data?.status as TaskStatus | undefined;
    if (status) return STATUS_COLOR[status];
    return '#343A43';
  }
  return '#C6CCD8';
}

interface PipelineGraphProps {
  pipeline: PipelineDetail | undefined;
  taskStatuses?: Record<string, TaskStatus>;
  /** 外部传入的当前任务 ID（用于同步树形选择） */
  selectedTaskId?: string | null;
  /** 点击节点回调 */
  onNodeClick?: (taskId: string) => void;
}

/** DAG 画布组件，封装 ReactFlow */
export default function PipelineGraph({ pipeline, taskStatuses, selectedTaskId, onNodeClick }: PipelineGraphProps) {
  const { nodes, edges } = usePipelineGraph({ pipeline, taskStatuses });
  const setSelectedNodeId = useAppStore((s) => s.setSelectedNodeId);
  const wrapperRef = useRef<HTMLDivElement>(null);

  const handleNodeClick: NodeMouseHandler = useCallback(
    (_, node) => {
      if (node.type === 'taskNode' || node.type === 'subpipelineGroup') {
        setSelectedNodeId(node.id);
        onNodeClick?.(node.id);
      }
    },
    [setSelectedNodeId, onNodeClick],
  );

  const onPaneClick = useCallback(() => {
    setSelectedNodeId(null);
    onNodeClick?.('');
  }, [setSelectedNodeId, onNodeClick]);

  // 同步外部选中状态到 store
  const syncedNodes = selectedTaskId !== undefined
    ? nodes.map((n) => ({ ...n, selected: n.id === selectedTaskId }))
    : nodes;

  return (
    <div
      ref={wrapperRef}
      className="wf-viewer"
      style={{
        width: '100%',
        height: '100%',
        backgroundColor: INK.canvas,
      }}
    >
      <style>{handleHotzoneStyle}</style>
      <ReactFlow
        nodes={syncedNodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodeClick={handleNodeClick}
        onPaneClick={onPaneClick}
        fitView
        fitViewOptions={{ padding: 0.3, includeHiddenNodes: false }}
        minZoom={0.1}
        maxZoom={2}
        proOptions={{ hideAttribution: true }}
        // v11 (2026-08): bezier 曲线（'default'）—— LR 流向下控制点水平伸展，
        // 画出 n8n 标志性的顺流曲线；仅兜底未显式指定 type 的边
        defaultEdgeOptions={{ type: 'default' }}
      >
        {/* 点状网格背景 —— v11 (2026-08): n8n 画布语汇（gap=20 与编辑器画布一致） */}
        <Background
          variant={BackgroundVariant.Dots}
          gap={20}
          size={1.2}
          color="#D3DAE4"
        />
        <Controls
          className="!bg-white/90 !backdrop-blur-sm !shadow-none !border !border-[#E4E9F0] !rounded-lg !overflow-hidden"
          showInteractive={false}
        />
          {/* v7.1: 画布容器尺寸变化时重新适应（打开 YAML 面板占 40% 宽后
              视口变窄，不重新 fitView 会裁掉右侧节点 —— 部署环境实测问题）。
              useReactFlow 必须在 ReactFlow 内部使用（error #001 教训） */}
          <FitOnResize />
          {/* v6 (2026-08): 边线型图例（左下角，可折叠）。
              marginBottom 让出同位 React Flow Controls 的空间，避免遮挡缩放按钮 */}
          <Panel position="bottom-left" style={{ marginBottom: 104 }}>
            <EdgeLegend />
          </Panel>
          <MiniMap
          // v11: 收敛尺寸 + 白底细边（大块彩色 minimap 是画布角落的噪音源）
          style={{ width: 176, height: 120 }}
          nodeStrokeWidth={2}
          nodeColor={miniMapNodeColor}
          nodeStrokeColor="#fff"
          maskColor="rgba(246, 248, 250, 0.78)"
          className="!shadow-none !border !border-[#E4E9F0] !rounded-lg !overflow-hidden !bg-white/90"
          position="bottom-right"
          zoomable
          pannable
        />
      </ReactFlow>
    </div>
  );
}

/** v7.1: 容器尺寸变化时自动 fitView（必须在 ReactFlow 内部渲染） */
function FitOnResize() {
  const { fitView } = useReactFlow();
  const sizeRef = useRef<{ w: number; h: number } | null>(null);
  useEffect(() => {
    // 观察画布 wrapper（.react-flow 的父级由 RF 内部管理，这里观察自身容器）
    const el = document.querySelector('.react-flow');
    if (!el || typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver((entries) => {
      const { width, height } = entries[0].contentRect;
      const prev = sizeRef.current;
      // 仅在尺寸真正变化时触发（首次挂载不重复 fitView，RF 已有初始 fitView）
      if (prev && (Math.abs(prev.w - width) > 1 || Math.abs(prev.h - height) > 1)) {
        fitView({ padding: 0.3, duration: 300 });
      }
      sizeRef.current = { w: width, h: height };
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [fitView]);
  return null;
}
