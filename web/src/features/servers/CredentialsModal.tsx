import { useEffect, useState } from 'react';
import { App, Alert, Button, Empty, Modal, Popconfirm, Select, Space, Table, Tag } from 'antd';
import { KeyRound, Pencil, Plus, Trash2 } from 'lucide-react';
import { useDeleteCredential, useCredentials } from '@/api/credentials';
import { useProjects } from '@/api/projects';
import CredentialFormModal from './CredentialFormModal';
import { credentialAuthLabel, credentialTypeLabel } from './credentialLabels';
import type { CredentialView } from '@/types';

interface CredentialsModalProps {
  open: boolean;
  /** 打开时默认选中的项目（从服务器表单入口带入） */
  initialProjectId?: string;
  onClose: () => void;
}

/**
 * 凭据管理弹窗：按项目列出凭据并支持增删改（仅管理员入口可达）。
 *
 * 设计决策：
 * - 凭据归属项目目录，所以必须先选项目再操作；默认选中传入的项目，减少一次选择。
 * - 明文密码永不回传，列表只展示"密码已保存/未配置"状态，降低误以为可查看明文的预期。
 * - 删除是破坏性操作：Popconfirm 二次确认 + 被 agent 引用时后端 409 兜底并展示原因。
 */
export default function CredentialsModal({ open, initialProjectId, onClose }: CredentialsModalProps) {
  const { message } = App.useApp();
  const [projectId, setProjectId] = useState<string | undefined>(initialProjectId);
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<CredentialView | null>(null);

  const { data: projects } = useProjects(open);
  const { data: credentials, isLoading, isError, error } = useCredentials(projectId, open);
  const deleteCredential = useDeleteCredential();

  useEffect(() => {
    if (!open) return;
    if (initialProjectId) {
      setProjectId(initialProjectId);
    } else if (!projectId && projects?.length) {
      setProjectId(projects[0].id);
    }
  }, [open, initialProjectId, projects, projectId]);

  const currentProject = projects?.find((p) => p.id === projectId);

  const handleDelete = async (cred: CredentialView) => {
    try {
      await deleteCredential.mutateAsync({ projectId: projectId!, credentialId: cred.id });
      message.success(`凭据 ${cred.id} 已删除`);
    } catch (e: unknown) {
      message.error(e instanceof Error ? e.message : '删除凭据失败');
    }
  };

  return (
    <>
      <Modal
        title={
          <div className="flex items-center gap-2">
            <KeyRound size={16} color="#7C7F88" />
            <span>凭据管理</span>
          </div>
        }
        open={open}
        onCancel={onClose}
        footer={null}
        destroyOnHidden
        width={860}
      >
        <div className="flex items-center gap-2 flex-wrap" style={{ marginBottom: 12 }}>
          <span className="text-xs" style={{ color: '#7C7F88' }}>项目</span>
          <Select
            size="small"
            style={{ minWidth: 220 }}
            placeholder="选择项目"
            value={projectId}
            onChange={setProjectId}
            options={(projects ?? []).map((p) => ({ value: p.id, label: p.name || p.workdir }))}
          />
          {currentProject && (
            <span className="text-xs" style={{ color: '#9CA0AC' }}>
              保存目录：<code>{currentProject.workdir}/credentials</code>
            </span>
          )}
          <div style={{ flex: 1 }} />
          <Button
            type="primary"
            size="small"
            icon={<Plus size={14} />}
            disabled={!projectId}
            onClick={() => { setEditing(null); setFormOpen(true); }}
          >
            新增凭据
          </Button>
        </div>

        {isError ? (
          <Alert
            type="error"
            showIcon
            message="无法获取凭据列表"
            description={error instanceof Error ? error.message : '请稍后重试'}
          />
        ) : (
          <Table<CredentialView>
            rowKey="id"
            size="small"
            loading={isLoading || deleteCredential.isPending}
            dataSource={credentials ?? []}
            pagination={false}
            locale={{
              emptyText: (
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description={
                    <span style={{ color: '#7C7F88' }}>
                      暂无凭据。新增后可在服务器配置中引用。
                    </span>
                  }
                />
              ),
            }}
            columns={[
              {
                title: 'ID',
                dataIndex: 'id',
                width: 160,
                render: (id: string, record) => (
                  <div className="flex items-center gap-1.5">
                    <span style={{ color: '#121620' }}>{id}</span>
                    {record.source_file?.includes('/') && (
                      <Tag className="!m-0 !text-xs" style={{ borderRadius: 3 }} color="default">
                        {record.source_file.split('/').pop()}
                      </Tag>
                    )}
                  </div>
                ),
              },
              { title: '名称', dataIndex: 'name', width: 140, render: (v: string) => v || '—' },
              {
                title: '认证方式',
                dataIndex: 'type',
                width: 150,
                render: (v: string, record) => (
                  <div className="flex flex-col gap-0.5">
                    <span style={{ color: '#121620' }}>{credentialTypeLabel(v)}</span>
                    <span className="text-xs" style={{ color: '#9CA0AC' }}>{credentialAuthLabel(record)}</span>
                  </div>
                ),
              },
              { title: '登录用户', dataIndex: 'username', width: 110, render: (v: string) => v || '—' },
              {
                title: '操作',
                key: 'actions',
                width: 110,
                render: (_: unknown, record) => (
                  <Space size={4}>
                    <Button
                      type="link"
                      size="small"
                      icon={<Pencil size={13} />}
                      aria-label={`编辑凭据 ${record.id}`}
                      onClick={() => { setEditing(record); setFormOpen(true); }}
                    >
                      编辑
                    </Button>
                    <Popconfirm
                      title={`删除凭据 "${record.id}"？`}
                      description="删除后引用该凭据的服务器将无法认证，此操作不可恢复。"
                      okText="删除"
                      okButtonProps={{ danger: true }}
                      cancelText="取消"
                      onConfirm={() => handleDelete(record)}
                    >
                      <Button
                        type="link"
                        size="small"
                        danger
                        icon={<Trash2 size={13} />}
                        aria-label={`删除凭据 ${record.id}`}
                      >
                        删除
                      </Button>
                    </Popconfirm>
                  </Space>
                ),
              },
            ]}
          />
        )}
      </Modal>

      <CredentialFormModal
        open={formOpen}
        projectId={projectId ?? ''}
        credential={editing}
        onClose={() => setFormOpen(false)}
      />
    </>
  );
}
