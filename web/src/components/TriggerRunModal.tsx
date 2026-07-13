import { useEffect } from 'react';
import { Modal, Form, Input, message, Spin } from 'antd';
import { useCreateRun } from '@/api/runs';
import { useNavigate } from 'react-router-dom';
import { usePipelineById } from '@/api/pipelines';
import { useAgentsWithConfig } from '@/api/agents';
import type { PipelineDetail } from '@/types';
import ParamsForm, { buildInitialValues, buildOverrideParams } from './ParamsForm';

interface TriggerRunModalProps {
  open: boolean;
  onClose: () => void;
  defaultDefinitionId?: string;
  defaultProjectId?: string | null;
  pipelineData?: PipelineDetail | null;
}

export default function TriggerRunModal({
  open,
  onClose,
  defaultDefinitionId,
  defaultProjectId,
  pipelineData,
}: TriggerRunModalProps) {
  const [form] = Form.useForm();
  const createRun = useCreateRun();
  const navigate = useNavigate();

  const shouldFetch = !pipelineData && !!defaultDefinitionId;
  const { data: fetchedPipeline, isLoading: isFetching } = usePipelineById(
    shouldFetch ? defaultDefinitionId : undefined,
  );
  const effectivePipeline = pipelineData || fetchedPipeline || null;

  const { data: agents } = useAgentsWithConfig(open);

  useEffect(() => {
    if (open && effectivePipeline) {
      form.resetFields();
      form.setFieldsValue({
        ...buildInitialValues(effectivePipeline),
      });
    }
  }, [open, effectivePipeline, form]);

  const handleOk = async () => {
    try {
      const values = await form.validateFields();
      const params = effectivePipeline
        ? buildOverrideParams(values, effectivePipeline)
        : {};

      const result = await createRun.mutateAsync({
        definition_id: defaultDefinitionId || values.definition_id,
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
      destroyOnHidden
      width={800}
    >
      <Form
        form={form}
        layout="vertical"
      >
        {!defaultDefinitionId && (
          <Form.Item
            name="definition_id"
            label="流水线 ID"
            rules={[{ required: true, message: '请输入流水线 ID' }]}
          >
            <Input placeholder="例如: a1b2c3d4e5f6" />
          </Form.Item>
        )}

        {shouldFetch && isFetching ? (
          <div style={{ textAlign: 'center', padding: 24 }}>
            <Spin tip="加载流水线参数...">
              <div style={{ padding: 20 }} />
            </Spin>
          </div>
        ) : effectivePipeline ? (
          <ParamsForm pipelineData={effectivePipeline} agents={agents} />
        ) : null}
      </Form>
    </Modal>
  );
}
