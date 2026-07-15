import { useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Skeleton } from 'antd';
import { useQuery } from '@tanstack/react-query';
import apiClient from '@/api/client';
import { useProject } from '@/api/projects';
import BreadcrumbSwitcher from '@/components/BreadcrumbSwitcher';
import type { BreadcrumbSwitchItem, BreadcrumbSwitchOption } from '@/components/BreadcrumbSwitcher';
import type { ProjectResponse, PipelineSummary } from '@/types';

interface PipelineBreadcrumbProps {
  projectId: string;
  projectName?: string;
  definitionId?: string;
  pipelineName?: string;
  isFileMode: boolean;
  filePath?: string;
}

/**
 * 流水线详情页专用面包屑。
 * 显示: 流水线 > {project_name} > {pipeline_name}
 * 项目名和流水线名支持悬浮浮窗切换。
 *
 * 数据加载策略：
 * - 项目名称：页面加载时通过 GET /api/projects/{projectId} 获取
 * - 浮窗项目列表 / 浮窗流水线列表：首次悬浮时按需加载，后续不再重复请求
 */
export default function PipelineBreadcrumb({
  projectId,
  projectName: propProjectName,
  definitionId,
  pipelineName: propPipelineName,
  isFileMode,
  filePath,
}: PipelineBreadcrumbProps) {
  const navigate = useNavigate();

  // 页面加载时获取项目名称（优先使用 props 传入的名称）
  const { data: project, isLoading: projectLoading } = useProject(projectId);
  const projectName = propProjectName || project?.name;

  // 悬浮浮窗数据 — 项目列表（首次 hover 时按需加载）
  const projectsLoadedRef = useRef(false);
  const {
    data: projectsData,
    refetch: refetchProjects,
    isFetching: projectsFetching,
  } = useQuery<ProjectResponse[]>({
    queryKey: ['projects', 'popover'],
    queryFn: async () => {
      const res = await apiClient.get('/api/projects/');
      return res.data;
    },
    enabled: false,
  });

  // 悬浮浮窗数据 — 当前项目流水线列表（首次 hover 时按需加载）
  const pipelinesLoadedRef = useRef(false);
  const {
    data: pipelinesData,
    refetch: refetchPipelines,
    isFetching: pipelinesFetching,
  } = useQuery<PipelineSummary[]>({
    queryKey: ['pipelines', 'popover', projectId],
    queryFn: async () => {
      const res = await apiClient.get('/api/pipelines/', { params: { project_id: projectId } });
      return (res.data as { items: PipelineSummary[] }).items ?? res.data;
    },
    enabled: false,
  });

  /** 项目浮窗打开时按需加载项目列表 */
  const handleProjectPopoverOpen = useCallback(() => {
    if (!projectsLoadedRef.current) {
      projectsLoadedRef.current = true;
      void refetchProjects();
    }
  }, [refetchProjects]);

  /** 流水线浮窗打开时按需加载流水线列表 */
  const handlePipelinePopoverOpen = useCallback(() => {
    if (!pipelinesLoadedRef.current) {
      pipelinesLoadedRef.current = true;
      void refetchPipelines();
    }
  }, [refetchPipelines]);

  // 构造项目切换选项
  const projectOptions: BreadcrumbSwitchOption[] = (projectsData ?? []).map((p) => ({
    key: p.id,
    label: p.name,
  }));

  // 构造流水线切换选项（folder 作为前缀显示）
  const pipelineOptions: BreadcrumbSwitchOption[] = (pipelinesData ?? []).map((p) => ({
    key: p.id,
    label: p.folder ? `${p.folder}/${p.name}` : p.name,
    tooltip: p.folder ? `${p.folder}/${p.name}` : p.name,
  }));

  // 面包屑项构建
  const items: BreadcrumbSwitchItem[] = [
    {
      label: '流水线',
      onClick: () => navigate('/pipelines'),
    },
    {
      label: projectName || projectId,
      options: projectOptions,
      currentKey: projectId,
      onSwitch: (key: string) => navigate(`/pipelines/${key}`),
      loading: projectsFetching,
      popoverTitle: '切换项目',
      onPopoverOpen: handleProjectPopoverOpen,
    },
  ];

  // 第三个面包屑项
  if (isFileMode) {
    // v2 (2026-07): 文件模式下不提供流水线切换，仅显示文件路径
    items.push({ label: filePath || '--' });
  } else if (definitionId) {
    items.push({
      label: propPipelineName || definitionId,
      options: pipelineOptions,
      currentKey: definitionId,
      onSwitch: (key: string) => navigate(`/pipelines/${projectId}/${key}`),
      loading: pipelinesFetching,
      popoverTitle: `当前项目: ${projectName || projectId}`,
      onPopoverOpen: handlePipelinePopoverOpen,
    });
  }

  // 项目名加载中展示骨架
  if (projectLoading && !projectName) {
    return (
      <div className="flex items-center gap-2 py-1 text-sm" data-testid="breadcrumb-loading">
        <span className="text-gray-500">流水线</span>
        <span className="text-gray-300">/</span>
        <Skeleton.Input active size="small" className="!w-20" />
      </div>
    );
  }

  return <BreadcrumbSwitcher items={items} />;
}
