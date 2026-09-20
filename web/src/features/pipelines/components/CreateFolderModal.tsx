import { useEffect, useMemo } from 'react';
import { Modal, Form, Select, Alert, App, AutoComplete } from 'antd';
import { useProjects } from '@/api/projects';
import { usePipelines, useCreateFolder } from '@/api/pipelines';

interface CreateFolderModalProps {
  open: boolean;
  onClose: () => void;
}

/**
 * v3 (2026-09): 网页端新建流水线文件夹弹窗。
 * 空文件夹由后端目录扫描返回，创建后立即出现在列表的项目分组下。
 */
export default function CreateFolderModal({ open, onClose }: CreateFolderModalProps) {
  const [form] = Form.useForm();
  const { message } = App.useApp();

  const { data: projects } = useProjects(open);
  const { data: pipelineData } = usePipelines();

  const selectedProjectId: string | undefined = Form.useWatch('project_id', form);
  const createFolder = useCreateFolder();

  const projectOptions = useMemo(
    () => (projects ?? []).map((p) => ({ value: p.id, label: p.name || p.workdir })),
    [projects],
  );

  // 文件夹建议：避免用户手输的路径与已有目录大小写/层级不一致
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
      if (projects?.length === 1) form.setFieldsValue({ project_id: projects[0].id });
    }
  }, [open, projects, form]);

  const handleOk = async () => {
    try {
      const values = await form.validateFields();
      const folder = values.folder.trim().replace(/^\/+|\/+$/g, '');
      await createFolder.mutateAsync({ projectId: values.project_id, folder });
      message.success('文件夹已创建');
      onClose();
    } catch (e: unknown) {
      if (e && typeof e === 'object' && 'errorFields' in e) return;
      message.error(e instanceof Error ? e.message : '创建文件夹失败');
    }
  };

  return (
    <Modal
      title="新建文件夹"
      open={open}
      onOk={handleOk}
      onCancel={onClose}
      confirmLoading={createFolder.isPending}
      destroyOnHidden
      okText="创建"
      width={520}
    >
      {projectOptions.length === 0 && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 16 }}
          message="暂无可选项目，请先注册项目目录"
        />
      )}
      <Form form={form} layout="vertical">
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
          label="文件夹路径"
          rules={[
            { required: true, message: '请输入文件夹路径' },
            {
              validator: (_, value: string) => {
                const v = (value ?? '').trim().replace(/^\/+|\/+$/g, '');
                if (!v) return Promise.reject(new Error('请输入文件夹路径'));
                if (v.split('/').some((seg) => seg === '..')) {
                  return Promise.reject(new Error('文件夹路径不能包含 ..'));
                }
                return Promise.resolve();
              },
            },
          ]}
        >
          <AutoComplete
            options={folderOptions}
            placeholder="例如：deploy/prod"
            filterOption={(input, option) =>
              (option?.value ?? '').toLowerCase().includes(input.toLowerCase())
            }
          />
        </Form.Item>
      </Form>
    </Modal>
  );
}
