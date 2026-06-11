import { useEffect } from 'react';
import { Modal, Form, Input, message, Spin } from 'antd';
import { useCreateRun } from '@/api/runs';
import { useNavigate } from 'react-router-dom';
import { usePipeline } from '@/api/pipelines';
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

  const shouldFetch = !pipelineData && !!defaultPipeline;
  const { data: fetchedPipeline, isLoading: isFetching } = usePipeline(
    shouldFetch ? defaultPipeline : undefined,
  );
  const effectivePipeline = pipelineData || fetchedPipeline || null;

  useEffect(() => {
    if (open && effectivePipeline) {
      form.resetFields();
      form.setFieldsValue({
        pipeline: defaultPipeline || '',
        ...buildInitialValues(effectivePipeline),
      });
    }
  }, [open, effectivePipeline, form, defaultPipeline]);

  const handleOk = async () => {
    try {
      const values = await form.validateFields();
      const params = effectivePipeline
        ? buildOverrideParams(values, effectivePipeline)
        : {};

      const result = await createRun.mutateAsync({
        pipeline: values.pipeline,
        params,
        project_id: defaultProjectId,
      });

      message.success('运行已创建');
      onClose();
      navigate(`/runs/${result.id}`);
    } catch (e: unknown) {
      if (e && typeof e === 'object' && 'errorFields' in e) {
        return;
      }
      const msg = e instanceof Error ? e.message : '创建运行失败';
      message.error(msg);
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

        {shouldFetch && isFetching ? (
          <div style={{ textAlign: 'center', padding: 24 }}>
            <Spin tip="加载流水线参数..." />
          </div>
        ) : effectivePipeline ? (
          <ParamsForm pipelineData={effectivePipeline} />
        ) : null}
      </Form>
    </Modal>
  );
}
