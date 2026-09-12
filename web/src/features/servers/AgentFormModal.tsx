import { useEffect, useState } from 'react';
import { Alert, App, Button, Form, Input, InputNumber, Modal, Select, Switch, Tooltip } from 'antd';
import { Plus, Server, Zap } from 'lucide-react';
import { useCreateAgent, useTryConnectAgent, useUpdateAgent } from '@/api/agents';
import type { AgentUpdatePayload } from '@/api/agents';
import { useCredentials } from '@/api/credentials';
import CredentialFormModal from './CredentialFormModal';
import type { AgentWithConfig, ProjectResponse } from '@/types';

interface AgentFormModalProps {
  open: boolean;
  /** 传入则为编辑模式 */
  agent?: AgentWithConfig | null;
  /** 已注册项目列表（新增时选择归属项目） */
  projects: ProjectResponse[];
  /** 新增时默认选中的项目（例如从空态引导进入） */
  defaultProjectId?: string;
  onClose: () => void;
}

const ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$/;

const TYPE_OPTIONS = [
  { value: 'ssh-username-password', label: 'SSH（用户名 + 密码/私钥凭据）' },
  { value: 'ssh-key', label: 'SSH（私钥凭据）' },
  { value: 'execution-agent', label: 'WebSocket Agent（agent 主动回连）' },
  { value: 'local', label: 'Local（本机）' },
];

/**
 * 服务器新增/编辑弹窗。
 *
 * 设计决策（为什么这么写）：
 * - 配置直接落盘到 `<项目>/agents/<id>.yaml`，弹窗顶部明示目标路径，避免"保存到哪个项目"歧义。
 * - ID 创建后不可改（YAML 文件名/任务 host 引用都依赖它），编辑时禁用并提示。
 * - 凭据下拉内嵌「新建凭据」入口，避免新增服务器时因缺凭据被迫中断流程去别的页面。
 * - 「测试连接」只对已保存的服务器开放：后端按 agent_id 读取磁盘配置，未保存配置无法测试；
 *   新增模式下禁用并说明原因，不做假按钮。
 */
export default function AgentFormModal({ open, agent, projects, defaultProjectId, onClose }: AgentFormModalProps) {
  const [form] = Form.useForm();
  const { message } = App.useApp();
  const createAgent = useCreateAgent();
  const updateAgent = useUpdateAgent();
  const tryConnect = useTryConnectAgent();
  const isEdit = !!agent;
  const projectId = Form.useWatch('project_id', form);
  const idValue = Form.useWatch('id', form);
  const type = Form.useWatch('type', form) ?? 'ssh-username-password';
  const needsSsh = type.startsWith('ssh');
  const [credentialModalOpen, setCredentialModalOpen] = useState(false);

  const { data: credentials } = useCredentials(projectId, open && needsSsh);
  const currentProject = projects.find((p) => p.id === projectId);

  useEffect(() => {
    if (!open) return;
    if (agent) {
      form.setFieldsValue({
        project_id: agent.project_id,
        id: agent.agent_id,
        name: agent.name,
        description: agent.description ?? '',
        type: agent.type || 'ssh-username-password',
        host: agent.host,
        port: agent.port || 22,
        username: agent.username || 'root',
        credential_id: agent.credential_id || undefined,
        max_parallel: agent.max_parallel || 1,
        execution_agent: agent.execution_agent ?? true,
        agent_auto_bootstrap: agent.agent_auto_bootstrap ?? true,
        // v2 (2026-09): 回连地址回填，远端不可达时用户才能在网页端修正后重新部署
        server_ws_host: agent.server_ws_host ?? '',
      });
    } else {
      form.resetFields();
      form.setFieldsValue({
        project_id: defaultProjectId || projects[0]?.id,
        type: 'ssh-username-password',
        port: 22,
        username: 'root',
        max_parallel: 1,
        execution_agent: true,
        agent_auto_bootstrap: true,
      });
    }
  }, [open, agent, defaultProjectId, projects, form]);

  const buildValues = async () => {
    const values = await form.validateFields();
    return {
      project_id: values.project_id as string,
      id: (values.id as string).trim(),
      name: values.name ?? '',
      description: values.description ?? '',
      type: values.type ?? 'ssh-username-password',
      host: needsSsh ? (values.host ?? '') : '',
      port: needsSsh ? Number(values.port ?? 22) : 22,
      username: needsSsh ? (values.username ?? '') : '',
      credential_id: needsSsh ? (values.credential_id ?? '') : '',
      max_parallel: Number(values.max_parallel ?? 1),
      execution_agent: values.execution_agent ?? true,
      agent_auto_bootstrap: values.agent_auto_bootstrap ?? true,
      // v2 (2026-09): 非 SSH 类型清空，避免切类型后残留无效的回连地址
      server_ws_host: needsSsh ? (values.server_ws_host ?? '') : '',
    };
  };

  const handleOk = async () => {
    try {
      if (isEdit && agent) {
        const values = await buildValues();
        // 编辑只提交可改字段（payload 类型即排除 project_id/id），避免误改归属与文件名
        const payload: AgentUpdatePayload = {
          name: values.name,
          description: values.description,
          type: values.type,
          host: values.host,
          port: values.port,
          username: values.username,
          credential_id: values.credential_id,
          max_parallel: values.max_parallel,
          execution_agent: values.execution_agent,
          agent_auto_bootstrap: values.agent_auto_bootstrap,
          server_ws_host: values.server_ws_host,
        };
        await updateAgent.mutateAsync({ projectId: agent.project_id, agentId: agent.agent_id, payload });
        message.success(`服务器 ${agent.agent_id} 已更新`);
      } else {
        const values = await buildValues();
        await createAgent.mutateAsync(values);
        message.success(`服务器 ${values.id} 已创建`);
      }
      onClose();
    } catch (e: unknown) {
      if (e && typeof e === 'object' && 'errorFields' in e) return;
      message.error(e instanceof Error ? e.message : '保存服务器失败');
    }
  };

  const handleTest = async () => {
    if (!agent) return;
    try {
      const result = await tryConnect.mutateAsync(agent.agent_id);
      if (result.status === 'connected') {
        message.success(`连接成功（${result.latency_ms}ms）`);
      } else {
        message.warning(`连接失败：${result.error || result.status}`);
      }
    } catch (e: unknown) {
      message.error(e instanceof Error ? e.message : '测试连接失败');
    }
  };

  return (
    <>
      <Modal
        title={
          <div className="flex items-center gap-2">
            <Server size={16} color="#7C7F88" />
            <span>{isEdit ? `编辑服务器：${agent?.agent_id}` : '新增服务器'}</span>
          </div>
        }
        open={open}
        onCancel={onClose}
        destroyOnHidden
        width={640}
        footer={[
          isEdit ? (
            <Button key="test" onClick={handleTest} loading={tryConnect.isPending} icon={<Zap size={14} />}>
              测试连接
            </Button>
          ) : (
            <Tooltip key="test" title="保存后才能测试连接（需要读取磁盘上的配置与凭据）">
              <span>
                <Button disabled icon={<Zap size={14} />}>测试连接</Button>
              </span>
            </Tooltip>
          ),
          <Button key="cancel" onClick={onClose}>取消</Button>,
          <Button
            key="ok"
            type="primary"
            onClick={handleOk}
            loading={createAgent.isPending || updateAgent.isPending}
          >
            保存
          </Button>,
        ]}
      >
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message={
            currentProject ? (
              <>
                配置将写入 <code>{currentProject.workdir}/agents/{isEdit ? agent?.agent_id : (idValue || '<id>')}.yaml</code>
              </>
            ) : (
              '请选择服务器归属的项目，配置将写入该项目的 agents/ 目录'
            )
          }
        />
        <Form form={form} layout="vertical">
          <Form.Item
            name="project_id"
            label="归属项目"
            rules={[{ required: true, message: '请选择项目' }]}
          >
            <Select
              disabled={isEdit}
              placeholder="选择项目"
              options={projects.map((p) => ({ value: p.id, label: p.name || p.workdir }))}
            />
          </Form.Item>

          <div className="grid grid-cols-2 gap-x-4">
            <Form.Item
              name="id"
              label="服务器 ID"
              rules={[
                { required: true, message: '请输入服务器 ID' },
                {
                  validator: (_rule, value: string) =>
                    !value || ID_PATTERN.test(value)
                      ? Promise.resolve()
                      : Promise.reject(new Error('只能包含字母、数字、下划线、点和短横线')),
                },
              ]}
              extra={isEdit ? 'ID 是流水线 host 引用，不可修改' : '将作为文件名保存，例如 web-01'}
            >
              <Input placeholder="web-01" disabled={isEdit} />
            </Form.Item>

            <Form.Item name="name" label="显示名称（可选）">
              <Input placeholder="测试机 A" />
            </Form.Item>
          </div>

          <Form.Item name="type" label="连接方式" rules={[{ required: true }]}>
            <Select options={TYPE_OPTIONS} />
          </Form.Item>

          {needsSsh && (
            <>
              <div className="grid grid-cols-2 gap-x-4">
                <Form.Item
                  name="host"
                  label="主机地址"
                  rules={[{ required: true, message: '请输入主机 IP 或域名' }]}
                >
                  <Input placeholder="10.0.0.1" />
                </Form.Item>
                <Form.Item
                  name="port"
                  label="SSH 端口"
                  rules={[
                    {
                      validator: (_rule, value: number) =>
                        value >= 1 && value <= 65535
                          ? Promise.resolve()
                          : Promise.reject(new Error('端口必须在 1-65535 之间')),
                    },
                  ]}
                >
                  <InputNumber min={1} max={65535} style={{ width: '100%' }} />
                </Form.Item>
              </div>

              <div className="grid grid-cols-2 gap-x-4">
                <Form.Item name="username" label="登录用户名">
                  <Input placeholder="root" autoComplete="off" />
                </Form.Item>
                <Form.Item
                  name="credential_id"
                  label="凭据"
                  extra="留空则尝试免密登录；密码/私钥在凭据中管理"
                >
                  <Select
                    allowClear
                    placeholder="选择凭据（可选）"
                    options={(credentials ?? []).map((c) => ({
                      value: c.id,
                      label: `${c.id}${c.name ? ` · ${c.name}` : ''}${c.username ? `（${c.username}）` : ''}`,
                    }))}
                    popupRender={(menu) => (
                      <>
                        {menu}
                        <div style={{ borderTop: '1px solid #F0F1F3', padding: 4 }}>
                          <Button
                            type="text"
                            size="small"
                            icon={<Plus size={13} />}
                            disabled={!projectId}
                            onMouseDown={(e) => e.preventDefault()}
                            onClick={() => setCredentialModalOpen(true)}
                          >
                            新建凭据
                          </Button>
                        </div>
                      </>
                    )}
                  />
                </Form.Item>
              </div>

              <Form.Item
                name="server_ws_host"
                label="Agent 回连地址（可选）"
                extra="agent 向本服务器建立 WebSocket 的地址。留空自动探测；若探测到的 IP（如内网地址）远端连不上，填写远端可达的地址（VPN/公网 IP）"
              >
                <Input placeholder="203.0.113.9（留空自动探测）" />
              </Form.Item>
            </>
          )}

          <Form.Item
            name="max_parallel"
            label="最大并发任务数"
            rules={[
              {
                validator: (_rule, value: number) =>
                  value >= 1 && value <= 64
                    ? Promise.resolve()
                    : Promise.reject(new Error('并发数必须在 1-64 之间')),
              },
            ]}
            extra="该服务器同时执行任务的槽位数"
          >
            <InputNumber min={1} max={64} style={{ width: 160 }} />
          </Form.Item>

          <div className="grid grid-cols-2 gap-x-4">
            <Form.Item
              name="execution_agent"
              label="优先 WebSocket 执行"
              valuePropName="checked"
              extra="上线 agent 后走常驻连接，避免每次 SSH"
            >
              <Switch />
            </Form.Item>
            <Form.Item
              name="agent_auto_bootstrap"
              label="允许自动部署 Agent"
              valuePropName="checked"
            >
              <Switch />
            </Form.Item>
          </div>

          <Form.Item name="description" label="描述（可选）">
            <Input.TextArea rows={2} placeholder="用途、机房、负责人等" />
          </Form.Item>
        </Form>
      </Modal>

      <CredentialFormModal
        open={credentialModalOpen}
        projectId={projectId ?? ''}
        onClose={() => setCredentialModalOpen(false)}
        onSaved={(newId) => form.setFieldValue('credential_id', newId)}
      />
    </>
  );
}
