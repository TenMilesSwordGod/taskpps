import { useEffect, useMemo, useRef, useState } from 'react';
import { Alert, App, Input, Modal } from 'antd';
import { SquareTerminal } from 'lucide-react';
import AppButton from '@/components/AppButton';
import EnvEditor from '@/components/EnvEditor';
import { useUpdateAgent } from '@/api/agents';
import type { AgentWithConfig } from '@/types';

/** 与后端 _ENV_KEY_RE 保持一致：合法环境变量名 */
const ENV_KEY_RE = /^[A-Za-z_][A-Za-z0-9_]*$/;
/** 与后端 _SHELL_RE 保持一致：shell 只允许路径/命令名安全字符 */
const SHELL_RE = /^[A-Za-z0-9_./+-]+$/;

interface ExecEnvModalProps {
  open: boolean;
  agent: AgentWithConfig | null;
  /** 仅管理员可保存；无权限时以只读方式展示（后端写接口同样校验） */
  canEdit?: boolean;
  onClose: () => void;
}

/**
 * 服务器执行环境弹窗：查看/编辑 shell 与默认环境变量，保存写入 agents/<id>.yaml。
 *
 * 设计决策（为什么独立于 AgentFormModal）：
 * - 执行环境是高频查看项（卡片信息区入口），与服务器连接配置的修改频率和
 *   关注点不同；拆开可以让普通用户只读查看，不影响管理员连接配置弹窗的复杂度。
 * - 保存走"只提交本弹窗字段"的更新接口，未触碰的 YAML 高级字段由后端保留。
 */
export default function ExecEnvModal({ open, agent, canEdit, onClose }: ExecEnvModalProps) {
  const { message } = App.useApp();
  const updateAgent = useUpdateAgent();
  const [shell, setShell] = useState('');
  const [env, setEnv] = useState<Record<string, string>>({});

  // v2 (2026-09): 只在弹窗「关→开」时回填。
  // agent 现在由列表实时派生，5s 轮询会不断产生新的对象引用；若依赖 agent 变化
  // 就回填，会周期性覆盖用户正在编辑的 shell/env。
  const wasOpenRef = useRef(false);
  useEffect(() => {
    if (open && !wasOpenRef.current && agent) {
      setShell(agent.shell ?? '');
      setEnv(agent.env ?? {});
    }
    wasOpenRef.current = open;
  }, [open, agent]);

  const invalidEnvKeys = useMemo(() => Object.keys(env).filter((k) => !ENV_KEY_RE.test(k)), [env]);
  const trimmedShell = shell.trim();
  const shellInvalid = !!trimmedShell && !SHELL_RE.test(trimmedShell);
  const envCount = Object.keys(env).length;
  // 默认工作目录（未注册项目）下的 agent 没有 project_id，写接口无法定位工作目录；
  // 该约束与新增/编辑服务器一致，这里明确提示而不是让请求 404
  const missingProject = !!agent && !agent.project_id;

  const handleSave = async () => {
    if (!agent) return;
    if (missingProject) {
      message.error('该服务器不属于已注册项目，无法通过网页保存；请先注册项目目录');
      return;
    }
    if (invalidEnvKeys.length > 0) {
      message.error(`环境变量名非法：${invalidEnvKeys.join(', ')}`);
      return;
    }
    if (shellInvalid) {
      message.error('Shell 路径只能包含字母、数字、下划线、点、斜杠、加号和短横线');
      return;
    }
    try {
      await updateAgent.mutateAsync({
        projectId: agent.project_id,
        agentId: agent.agent_id,
        // shell/env 均全量提交：空字符串/空对象表示清除，由后端决定是否从 YAML 移除
        payload: { shell: trimmedShell, env },
      });
      message.success(`执行环境已保存：${agent.agent_id}`);
      onClose();
    } catch (e: unknown) {
      message.error(e instanceof Error ? e.message : '保存执行环境失败');
    }
  };

  const readOnly = !canEdit;
  const envEntries = Object.entries(env);

  return (
    <Modal
      title={
        <div className="flex items-center gap-2">
          <SquareTerminal size={16} color="#7C7F88" />
          <span>执行环境{agent ? `：${agent.agent_id}` : ''}</span>
        </div>
      }
      open={open}
      onCancel={onClose}
      destroyOnHidden
      width={560}
      footer={
        readOnly
          ? [<AppButton key="close" onClick={onClose}>关闭</AppButton>]
          : [
              <AppButton key="cancel" onClick={onClose}>取消</AppButton>,
              <AppButton
                key="ok"
                variant="primary"
                onClick={handleSave}
                loading={updateAgent.isPending}
              >
                保存
              </AppButton>,
            ]
      }
    >
      <Alert
        type={missingProject ? 'warning' : 'info'}
        showIcon
        style={{ marginBottom: 16 }}
        message={
          <span className="text-xs">
            {missingProject
              ? '该服务器不属于已注册项目（默认 agents/ 目录），只能查看，无法通过网页保存；请先注册项目目录。'
              : <>保存到 <code>{agent?.source_file || `agents/${agent?.agent_id}.yaml`}</code>；流水线 / 任务中同名环境变量会覆盖此处配置。</>}
          </span>
        }
      />

      <div style={{ marginBottom: 16 }}>
        <div style={{ fontSize: 12, color: '#7C7F88', marginBottom: 6 }}>Shell 解释器</div>
        {readOnly ? (
          <code style={{ fontSize: 12, color: '#262626' }}>
            {trimmedShell || '默认（未配置，使用执行器内置 shell）'}
          </code>
        ) : (
          <>
            <Input
              value={shell}
              onChange={(e) => setShell(e.target.value)}
              placeholder="/bin/bash（留空使用默认）"
              style={{ fontFamily: 'JetBrains Mono, monospace' }}
              status={shellInvalid ? 'error' : undefined}
            />
            {shellInvalid ? (
              <div style={{ fontSize: 12, color: '#ef4444', marginTop: 4 }}>
                只能包含字母、数字、下划线、点、斜杠、加号和短横线（不能含空格）
              </div>
            ) : (
              <div style={{ fontSize: 12, color: '#8C8C8C', marginTop: 4 }}>
                远程 execution-agent 修改 shell 后需先「更新部署」升级 agent 才会生效
              </div>
            )}
          </>
        )}
      </div>

      <div>
        <div style={{ fontSize: 12, color: '#7C7F88', marginBottom: 6 }}>
          环境变量（{envCount} 项）
        </div>
        {readOnly ? (
          envEntries.length === 0 ? (
            <span style={{ fontSize: 12, color: '#8C8C8C' }}>未配置环境变量</span>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              {envEntries.map(([key, value]) => (
                <div key={key} style={{ display: 'flex', gap: 8, fontFamily: 'JetBrains Mono, monospace', fontSize: 12 }}>
                  <span style={{ color: '#262626', minWidth: 140, wordBreak: 'break-all' }}>{key}</span>
                  <span style={{ color: '#7C7F88', wordBreak: 'break-all' }}>{value}</span>
                </div>
              ))}
            </div>
          )
        ) : (
          <>
            <EnvEditor
              value={env}
              onChange={setEnv}
              tooltip={
                <div style={{ fontSize: 12, lineHeight: 1.6 }}>
                  执行时自动 export 到该服务器的所有命令；不支持流水线模板语法。
                </div>
              }
            />
            {/* 常驻内联错误：比只靠保存时 toast 更容易定位是哪一行的问题 */}
            {invalidEnvKeys.length > 0 && (
              <div style={{ fontSize: 12, color: '#ef4444', marginTop: 6 }}>
                环境变量名非法：{invalidEnvKeys.join(', ')}（只允许字母/数字/下划线，且不以数字开头）
              </div>
            )}
          </>
        )}
      </div>
    </Modal>
  );
}
