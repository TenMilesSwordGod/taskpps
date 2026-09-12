import type { CredentialView } from '@/types';

/**
 * 凭据类型展示映射。
 *
 * 设计决策：后端只在 SSH 执行链路消费 username/password/key_path，
 * 表单这里也只暴露真实可用的两类，避免出现"token 类型保存后无人消费"的假能力。
 */
export const CREDENTIAL_TYPE_OPTIONS = [
  { value: 'ssh-username-password', label: 'SSH 用户名 + 密码' },
  { value: 'ssh-key', label: 'SSH 私钥（服务器上的 key_path）' },
];

export function credentialTypeLabel(type: string): string {
  return CREDENTIAL_TYPE_OPTIONS.find((o) => o.value === type)?.label ?? (type || '未指定');
}

export function credentialAuthLabel(cred: CredentialView): string {
  if (cred.key_path) return `私钥 ${cred.key_path}`;
  if (cred.has_password) return '密码已保存';
  return '未配置认证信息';
}
