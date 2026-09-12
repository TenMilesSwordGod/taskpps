import { useEffect } from 'react';
import { Modal, Form, Input, App } from 'antd';
import { useRenamePipeline, useRenameFolder } from '@/api/pipelines';

interface RenameModalProps {
  open: boolean;
  onClose: () => void;
  kind: 'pipeline' | 'folder';
  projectId: string | null;
  /** 当前文件/文件夹的相对路径（相对 pipelines/ 目录） */
  current: string;
}

/**
 * v3 (2026-09): 流水线/文件夹重命名（或移动）弹窗。
 * 设计决策：只改文件/文件夹路径，不修改 YAML 内的 name 字段——
 * name 属于流水线内容，由详情页编辑器负责。
 */
export default function RenameModal({ open, onClose, kind, projectId, current }: RenameModalProps) {
  const [form] = Form.useForm();
  const { message } = App.useApp();
  const renamePipeline = useRenamePipeline();
  const renameFolder = useRenameFolder();
  const isPipeline = kind === 'pipeline';

  useEffect(() => {
    if (open) form.setFieldsValue({ target: current });
  }, [open, current, form]);

  const handleOk = async () => {
    try {
      const values = await form.validateFields();
      let target: string = values.target.trim().replace(/^\/+|\/+$/g, '');
      if (isPipeline && !/\.ya?ml$/i.test(target)) target = `${target}.yaml`;

      if (projectId) {
        if (isPipeline) {
          await renamePipeline.mutateAsync({ projectId, file: current, newFile: target });
        } else {
          await renameFolder.mutateAsync({ projectId, folder: current, newFolder: target });
        }
        message.success(isPipeline ? '流水线已重命名' : '文件夹已重命名');
        onClose();
      }
    } catch (e: unknown) {
      if (e && typeof e === 'object' && 'errorFields' in e) return;
      message.error(e instanceof Error ? e.message : '重命名失败');
    }
  };

  return (
    <Modal
      title={isPipeline ? '重命名/移动流水线' : '重命名/移动文件夹'}
      open={open}
      onOk={handleOk}
      onCancel={onClose}
      confirmLoading={renamePipeline.isPending || renameFolder.isPending}
      destroyOnHidden
      okText="保存"
      width={520}
    >
      <Form form={form} layout="vertical">
        <Form.Item
          name="target"
          label={isPipeline ? '文件路径' : '文件夹路径'}
          extra={
            isPipeline
              ? '相对 pipelines/ 目录，例如 debug/deploy.yaml；修改路径不影响运行历史'
              : '相对 pipelines/ 目录，例如 debug/prod'
          }
          rules={[
            { required: true, message: '请输入新路径' },
            {
              validator: (_, value: string) => {
                const v = (value ?? '').trim().replace(/^\/+|\/+$/g, '');
                if (!v) return Promise.reject(new Error('请输入新路径'));
                if (v.split('/').some((seg) => seg === '..')) {
                  return Promise.reject(new Error('路径不能包含 ..'));
                }
                return Promise.resolve();
              },
            },
          ]}
        >
          <Input placeholder={isPipeline ? '例如：deploy/prod.yaml' : '例如：deploy/prod'} />
        </Form.Item>
      </Form>
    </Modal>
  );
}
