import { useState } from 'react';
import { Modal, Form, Input, message } from 'antd';
import { useCreateRun } from '@/api/runs';
import { useNavigate } from 'react-router-dom';
import { useProjectId } from '@/contexts/ProjectContext';

interface TriggerRunModalProps {
  open: boolean;
  onClose: () => void;
  /** 预填充的流水线文件名 */
  defaultPipeline?: string;
}

/** 触发运行弹窗 */
export default function TriggerRunModal({ open, onClose, defaultPipeline }: TriggerRunModalProps) {
  const [form] = Form.useForm();
  const [paramsText, setParamsText] = useState('{}');
  const createRun = useCreateRun();
  const navigate = useNavigate();
  const projectId = useProjectId();

  const handleOk = async () => {
    try {
      const values = await form.validateFields();
      let params: Record<string, unknown> = {};
      try {
        params = JSON.parse(paramsText);
      } catch {
        message.error('params 必须是合法的 JSON');
        return;
      }

      const result = await createRun.mutateAsync({
        pipeline: values.pipeline,
        params,
        project_id: projectId,
      });

      message.success('运行已创建');
      onClose();
      navigate(`/runs/${result.id}`);
    } catch {
      // 表单验证失败，不做处理
    }
  };

  return (
    <Modal
      title="触发运行"
      open={open}
      onOk={handleOk}
      onCancel={onClose}
      confirmLoading={createRun.isPending}
      destroyOnClose
    >
      <Form
        form={form}
        layout="vertical"
        initialValues={{ pipeline: defaultPipeline || '' }}
      >
        <Form.Item
          name="pipeline"
          label="流水线文件"
          rules={[{ required: true, message: '请输入流水线文件名' }]}
        >
          <Input placeholder="例如: deploy.yaml" />
        </Form.Item>

        <Form.Item label="参数 (JSON)">
          <Input.TextArea
            rows={6}
            value={paramsText}
            onChange={(e) => setParamsText(e.target.value)}
            placeholder='{"key": "value"}'
          />
        </Form.Item>
      </Form>
    </Modal>
  );
}
