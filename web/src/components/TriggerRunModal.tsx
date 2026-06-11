import { useMemo } from 'react';
import { Modal, Form, Input, message } from 'antd';
import { useCreateRun } from '@/api/runs';
import { useNavigate } from 'react-router-dom';
import type { PipelineDetail } from '@/types';
import ParamsForm, { buildInitialValues, buildOverrideParams } from './ParamsForm';

interface TriggerRunModalProps {
  open: boolean;
  onClose: () => void;
  defaultPipeline?: string;
  defaultProjectId?: string | null;
  pipelineData?: PipelineDetail | null;
}

export default function TriggerRunModal({
  open,
  onClose,
  defaultPipeline,
  defaultProjectId,
  pipelineData,
}: TriggerRunModalProps) {
  const [form] = Form.useForm();
  const createRun = useCreateRun();
  const navigate = useNavigate();

  const initialValues = useMemo(() => {
    if (!pipelineData) return {};
    return buildInitialValues(pipelineData);
  }, [pipelineData]);

  const handleOk = async () => {
    try {
      const values = await form.validateFields();

      let params: Record<string, unknown> = {};
      if (pipelineData) {
        params = buildOverrideParams(values, pipelineData);
      } else {
        try {
          params = JSON.parse(values.params || '{}');
        } catch {
          message.error('params 必须是合法的 JSON');
          return;
        }
      }

      const result = await createRun.mutateAsync({
        pipeline: values.pipeline,
        params,
        project_id: defaultProjectId,
      });

      message.success('运行已创建');
      onClose();
      navigate(`/runs/${result.id}`);
    } catch {
      // 表单验证失败或 API 错误
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
        initialValues={{ pipeline: defaultPipeline || '', ...initialValues }}
      >
        <Form.Item
          name="pipeline"
          label="流水线文件"
          rules={[{ required: true, message: '请输入流水线文件名' }]}
        >
          <Input placeholder="例如: deploy.yaml" />
        </Form.Item>

        {pipelineData ? (
          <ParamsForm pipelineData={pipelineData} />
        ) : (
          <Form.Item
            name="params"
            label="参数 (JSON)"
            initialValue="{}"
          >
            <Input.TextArea
              rows={6}
              placeholder='{"config": {"timeout": 120}}'
            />
          </Form.Item>
        )}
      </Form>
    </Modal>
  );
}
