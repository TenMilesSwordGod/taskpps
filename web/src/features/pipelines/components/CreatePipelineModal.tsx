import { useEffect, useMemo } from 'react';
import { Modal, Form, Input, Select, Radio, Alert, App, AutoComplete } from 'antd';
import { useNavigate } from 'react-router-dom';
import { useProjects } from '@/api/projects';
import { usePipelines, useCreatePipeline } from '@/api/pipelines';
import { buildPipelineContent, pipelineNameFromFile, type PipelineTemplateId } from './pipelineTemplates';

interface CreatePipelineModalProps {
  open: boolean;
  onClose: () => void;
}

/** 文件名允许的字符：中英文、数字、点、下划线、短横线（避免 YAML/URL 转义问题） */
const FILE_NAME_PATTERN = /^[A-Za-z0-9._\-\u4e00-\u9fa5]+$/;

/**
 * v3 (2026-09): 网页端新建流水线弹窗。
 * 交互流程：选项目 → 选/输文件夹 → 输文件名 → 选模板 → 创建后跳转编辑页。
 */
export default function CreatePipelineModal({ open, onClose }: CreatePipelineModalProps) {
  const [form] = Form.useForm();
  const { message } = App.useApp();
  const navigate = useNavigate();

  const { data: projects } = useProjects(open);
  const { data: pipelineData } = usePipelines();

  // 表单里当前选中的项目决定文件夹建议（mutation 时再传 projectId）
  const selectedProjectId: string | undefined = Form.useWatch('project_id', form);
  const createPipeline = useCreatePipeline();

  // 仅展示已注册项目：默认回退组（project_id=null）无法承载新建操作
  const projectOptions = useMemo(
    () => (projects ?? []).map((p) => ({ value: p.id, label: p.name || p.workdir })),
    [projects],
  );

  // 文件夹建议：合并已有流水线路径中的目录与后端返回的空文件夹
  const folderOptions = useMemo(() => {
    if (!selectedProjectId) return [];
    const folders = new Set<string>();
    for (const item of pipelineData?.items ?? []) {
      if (item.project_id === selectedProjectId && item.folder) folders.add(item.folder);
    }
    for (const f of pipelineData?.folders ?? []) {
      if (f.project_id === selectedProjectId && f.folder) folders.add(f.folder);
    }
    return [...folders].sort().map((value) => ({ value }));
  }, [pipelineData, selectedProjectId]);

  useEffect(() => {
    if (open) {
      form.resetFields();
      // 只有一个项目时直接选中，减少一次点击
      if (projects?.length === 1) form.setFieldsValue({ project_id: projects[0].id });
    }
  }, [open, projects, form]);

  const handleOk = async () => {
    try {
      const values = await form.validateFields();
      const folder = (values.folder ?? '').trim().replace(/^\/+|\/+$/g, '');
      const rawName: string = values.filename.trim();
      const fileName = /\.ya?ml$/i.test(rawName) ? rawName : `${rawName}.yaml`;
      const file = folder ? `${folder}/${fileName}` : fileName;
      const content = buildPipelineContent(values.template as PipelineTemplateId, pipelineNameFromFile(fileName));

      const result = await createPipeline.mutateAsync({ projectId: values.project_id, file, content });
      message.success('流水线已创建');
      onClose();
      navigate(
        result.definition_id
          ? `/pipelines/${values.project_id}/${result.definition_id}`
          : `/pipelines/${values.project_id}/_file_/${encodeURIComponent(result.file)}`,
      );
    } catch (e: unknown) {
      if (e && typeof e === 'object' && 'errorFields' in e) return;
      message.error(e instanceof Error ? e.message : '创建流水线失败');
    }
  };

  return (
    <Modal
      title="新建流水线"
      open={open}
      onOk={handleOk}
      onCancel={onClose}
      confirmLoading={createPipeline.isPending}
      destroyOnHidden
      okText="创建并编辑"
      width={560}
    >
      {projectOptions.length === 0 && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 16 }}
          message="暂无可选项目，请先注册项目目录"
        />
      )}
      <Form form={form} layout="vertical" initialValues={{ template: 'blank' }}>
        <Form.Item
          name="project_id"
          label="所属项目"
          rules={[{ required: true, message: '请选择项目' }]}
        >
          <Select
            placeholder="选择已注册项目"
            options={projectOptions}
            showSearch
            optionFilterProp="label"
            disabled={projectOptions.length === 0}
          />
        </Form.Item>

        <Form.Item
          name="folder"
          label="文件夹（可选）"
          rules={[
            {
              // 后端也会拦截穿越路径，这里提前给用户友好提示
              validator: (_, value: string) => {
                const v = (value ?? '').trim();
                if (v && v.split('/').some((seg) => seg === '..')) {
                  return Promise.reject(new Error('文件夹路径不能包含 ..'));
                }
                return Promise.resolve();
              },
            },
          ]}
        >
          <AutoComplete
            options={folderOptions}
            placeholder="例如：deploy/prod，留空则放在 pipelines/ 根目录"
            filterOption={(input, option) =>
              (option?.value ?? '').toLowerCase().includes(input.toLowerCase())
            }
          />
        </Form.Item>

        <Form.Item
          name="filename"
          label="文件名"
          rules={[
            { required: true, message: '请输入文件名' },
            {
              validator: (_, value: string) => {
                const v = (value ?? '').trim();
                if (v && !FILE_NAME_PATTERN.test(v)) {
                  return Promise.reject(new Error('仅支持中英文、数字、点、下划线和短横线'));
                }
                return Promise.resolve();
              },
            },
          ]}
        >
          <Input placeholder="例如：deploy.yaml（省略后缀时自动补 .yaml）" />
        </Form.Item>

        <Form.Item name="template" label="初始模板" rules={[{ required: true }]}>
          <Radio.Group>
            <Radio.Button value="blank">空白</Radio.Button>
            <Radio.Button value="example">示例（shell 任务）</Radio.Button>
          </Radio.Group>
        </Form.Item>
      </Form>
    </Modal>
  );
}
