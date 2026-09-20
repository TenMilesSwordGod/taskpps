import { useEffect } from 'react';
import { Modal, Form, Input, Alert, App } from 'antd';
import { useRegisterProject } from '@/api/projects';

interface RegisterProjectModalProps {
  open: boolean;
  onClose: () => void;
}

/**
 * v3 (2026-09): 网页端注册项目目录弹窗。
 * 设计决策：workdir 是 server 所在机器上的路径（浏览器无法浏览服务器文件系统），
 * 后端会严格校验目录存在并自动创建 pipelines/，因此这里只做必填校验。
 */
export default function RegisterProjectModal({ open, onClose }: RegisterProjectModalProps) {
  const [form] = Form.useForm();
  const { message } = App.useApp();
  const registerProject = useRegisterProject();

  useEffect(() => {
    if (open) form.resetFields();
  }, [open, form]);

  const handleOk = async () => {
    try {
      const values = await form.validateFields();
      const project = await registerProject.mutateAsync({
        workdir: values.workdir.trim(),
        name: (values.name ?? '').trim(),
      });
      message.success(`项目已注册：${project.name || project.workdir}`);
      onClose();
    } catch (e: unknown) {
      if (e && typeof e === 'object' && 'errorFields' in e) return;
      message.error(e instanceof Error ? e.message : '注册项目失败');
    }
  };

  return (
    <Modal
      title="注册项目目录"
      open={open}
      onOk={handleOk}
      onCancel={onClose}
      confirmLoading={registerProject.isPending}
      destroyOnHidden
      okText="注册"
      width={560}
    >
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message="目录路径指 server 所在机器上的路径；注册后会自动创建 pipelines/ 子目录"
      />
      <Form form={form} layout="vertical">
        <Form.Item
          name="workdir"
          label="项目目录（绝对路径）"
          rules={[{ required: true, message: '请输入项目目录路径' }]}
          extra="例如：/home/user/projects/my-app"
        >
          <Input placeholder="/path/to/your/project" />
        </Form.Item>

        <Form.Item name="name" label="项目名称（可选）">
          <Input placeholder="留空则显示为目录名" />
        </Form.Item>
      </Form>
    </Modal>
  );
}
