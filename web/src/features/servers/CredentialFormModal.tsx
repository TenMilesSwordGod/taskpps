import { useEffect } from 'react';
import { App, Alert, Form, Input, Modal, Select } from 'antd';
import { useCreateCredential, useUpdateCredential } from '@/api/credentials';
import { CREDENTIAL_TYPE_OPTIONS } from './credentialLabels';
import type { CredentialView } from '@/types';

interface CredentialFormModalProps {
  open: boolean;
  projectId: string;
  /** 传入则为编辑，否则为新增 */
  credential?: CredentialView | null;
  onClose: () => void;
  /** 保存成功回调：AgentFormModal 用它自动选中新凭据 */
  onSaved?: (credentialId: string) => void;
}

const ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$/;

/**
 * 凭据新增/编辑弹窗。
 *
 * 设计决策（为什么这么写）：
 * - 密码是"只写字段"：编辑时后端不会回传明文，表单留空 = 不修改；输入新值才覆盖。
 * - 切换认证方式时显式发送空串清掉另一种认证字段，避免"改成密码认证但旧 key_path 还在"
 *   导致执行端仍优先用私钥的隐蔽行为。
 * - 类型只暴露 SSH 密码/私钥两类：token 类型当前无任何执行链路消费，不提供假选项。
 */
export default function CredentialFormModal({
  open,
  projectId,
  credential,
  onClose,
  onSaved,
}: CredentialFormModalProps) {
  const [form] = Form.useForm();
  const { message } = App.useApp();
  const createCredential = useCreateCredential();
  const updateCredential = useUpdateCredential();
  const isEdit = !!credential;
  const type = Form.useWatch('type', form) ?? 'ssh-username-password';

  useEffect(() => {
    if (!open) return;
    if (credential) {
      form.setFieldsValue({
        id: credential.id,
        name: credential.name,
        description: credential.description,
        type: credential.type || 'ssh-username-password',
        username: credential.username,
        key_path: credential.key_path,
        password: '',
      });
    } else {
      form.resetFields();
      form.setFieldsValue({ type: 'ssh-username-password' });
    }
  }, [open, credential, form]);

  const handleOk = async () => {
    try {
      const values = await form.validateFields();
      if (isEdit) {
        await updateCredential.mutateAsync({
          projectId,
          credentialId: credential.id,
          payload: {
            name: values.name ?? '',
            description: values.description ?? '',
            type: values.type,
            username: values.username ?? '',
            // 留空=不改；输入新值=覆盖；切换类型时清空另一种认证方式
            password: values.password ? values.password : values.type === 'ssh-key' ? '' : undefined,
            key_path: values.type === 'ssh-key' ? values.key_path : '',
          },
        });
        message.success(`凭据 ${credential.id} 已更新`);
      } else {
        const created = await createCredential.mutateAsync({
          project_id: projectId,
          id: values.id.trim(),
          name: values.name ?? '',
          description: values.description ?? '',
          type: values.type,
          username: values.username ?? '',
          password: values.type === 'ssh-key' ? undefined : values.password,
          key_path: values.type === 'ssh-key' ? values.key_path : undefined,
        });
        message.success(`凭据 ${created.id} 已创建`);
        onSaved?.(created.id);
      }
      onClose();
    } catch (e: unknown) {
      if (e && typeof e === 'object' && 'errorFields' in e) return;
      message.error(e instanceof Error ? e.message : '保存凭据失败');
    }
  };

  return (
    <Modal
      title={isEdit ? `编辑凭据：${credential?.id}` : '新增凭据'}
      open={open}
      onOk={handleOk}
      onCancel={onClose}
      confirmLoading={createCredential.isPending || updateCredential.isPending}
      destroyOnHidden
      okText="保存"
      width={560}
    >
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message={
          <>
            凭据保存在项目 <code>{projectId}</code> 的 <code>credentials/</code> 目录；
            密码加密落盘，保存后无法查看明文。
          </>
        }
      />
      <Form form={form} layout="vertical">
        <Form.Item
          name="id"
          label="凭据 ID"
          rules={[
            { required: true, message: '请输入凭据 ID' },
            {
              validator: (_rule, value: string) =>
                !value || ID_PATTERN.test(value)
                  ? Promise.resolve()
                  : Promise.reject(new Error('只能包含字母、数字、下划线、点和短横线，且以字母或数字开头')),
            },
          ]}
          extra={isEdit ? 'ID 不可修改' : '将作为文件名保存，例如 prod-ssh'}
        >
          <Input placeholder="prod-ssh" disabled={isEdit} />
        </Form.Item>

        <Form.Item name="name" label="名称（可选）">
          <Input placeholder="生产环境 SSH" />
        </Form.Item>

        <Form.Item name="type" label="认证方式" rules={[{ required: true }]}>
          <Select options={CREDENTIAL_TYPE_OPTIONS} />
        </Form.Item>

        <Form.Item name="username" label="登录用户名">
          <Input placeholder="root" autoComplete="off" />
        </Form.Item>

        {type === 'ssh-key' ? (
          <Form.Item
            name="key_path"
            label="私钥路径"
            rules={[{ required: !isEdit, message: '请输入服务器上的私钥文件路径' }]}
            extra="填 server 所在机器上的私钥文件路径（不会上传私钥内容）"
          >
            <Input placeholder="/home/deploy/.ssh/id_rsa" />
          </Form.Item>
        ) : (
          <Form.Item
            name="password"
            label={isEdit ? '密码（留空则不修改）' : '密码'}
            rules={[{ required: !isEdit, message: '请输入密码' }]}
            extra={isEdit ? '出于安全考虑不回显原密码；输入新值将覆盖' : undefined}
          >
            <Input.Password placeholder={isEdit ? '留空保持原密码' : '登录密码'} autoComplete="new-password" />
          </Form.Item>
        )}

        <Form.Item name="description" label="描述（可选）">
          <Input.TextArea rows={2} placeholder="用途说明，便于团队识别" />
        </Form.Item>
      </Form>
    </Modal>
  );
}
