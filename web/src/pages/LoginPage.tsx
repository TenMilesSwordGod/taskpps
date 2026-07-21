import { useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Form, Input, Button, Checkbox, Tabs, App } from 'antd';
import type { CSSProperties } from 'react';
import TaskPpsLogo from '@/components/TaskPpsLogo';
import { useLogin, useRegister } from '@/api/auth';
import type { RegisterRequest, LoginRequest } from '@/api/auth';

/**
 * 登录/注册页（issue #204）。
 *
 * 设计参考 .debug/issue_204/design-spec.md：
 * - 全屏 #F6F6F8 背景，居中 400px 卡片（hairline 边框 + 12px 圆角）。
 * - Tabs 切换登录/注册（line 风格，选中下划线 #3D5BFF）。
 * - 登录表单：用户名 + 密码；注册表单：用户名 + 昵称 + 密码（评论5要求，无邮箱）。
 * - 登录成功 → 跳转 redirect 或 /dashboard；注册成功 → 切登录 Tab + 预填用户名。
 */

/** 卡片样式（design-tokens loginCard） */
const cardStyle: CSSProperties = {
  width: 'min(400px, calc(100vw - 32px))',
  padding: 32,
  background: '#FFFFFF',
  border: '1px solid #E3E4E8',
  borderRadius: 12,
  boxShadow: 'rgba(1, 24, 33, 0.05) 0px 0px 0px 1px',
};

/** 全屏背景容器 */
const wrapperStyle: CSSProperties = {
  minHeight: '100vh',
  background: '#F6F6F8',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
};

/** 品牌区样式 */
const brandStyle: CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'center',
  marginBottom: 24,
};

/** 用户名正则：字母/数字/下划线/连字符，3-32 位 */
const USERNAME_PATTERN = /^[a-zA-Z0-9_-]+$/;

export default function LoginPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { message } = App.useApp();
  const [activeTab, setActiveTab] = useState<'login' | 'register'>('login');
  // 注册成功后预填到登录表单的用户名
  const [prefillUsername, setPrefillUsername] = useState('');

  const loginMutation = useLogin();
  const registerMutation = useRegister();

  /** 安全跳转：只允许站内路径（防开放重定向） */
  const safeRedirect = () => {
    const redirect = searchParams.get('redirect');
    if (redirect && redirect.startsWith('/')) {
      navigate(redirect, { replace: true });
    } else {
      navigate('/dashboard', { replace: true });
    }
  };

  /** 登录提交 */
  const onLogin = async (values: LoginRequest) => {
    try {
      await loginMutation.mutateAsync(values);
      message.success('登录成功');
      safeRedirect();
    } catch (err: unknown) {
      // 401 统一显示「用户名或密码错误」（防枚举），其他错误显示后端 detail
      const status = (err as { response?: { status?: number } })?.response?.status;
      if (status === 401) {
        message.error('用户名或密码错误');
      } else {
        const msg = (err as Error)?.message || '登录失败';
        message.error(msg);
      }
    }
  };

  /** 注册提交 */
  const onRegister = async (values: RegisterRequest) => {
    try {
      await registerMutation.mutateAsync(values);
      message.success('注册成功，请登录');
      // 注册成功不自动登录（spec 明确）：切登录 Tab + 预填用户名
      setPrefillUsername(values.username);
      setActiveTab('login');
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status;
      if (status === 409) {
        message.error('该用户名已被注册');
      } else {
        const msg = (err as Error)?.message || '注册失败';
        message.error(msg);
      }
    }
  };

  return (
    <div style={wrapperStyle}>
      <div style={cardStyle}>
        {/* 品牌区 */}
        <div style={brandStyle}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
            <TaskPpsLogo size={32} />
            <span style={{ fontSize: 20, fontWeight: 500, color: '#121620' }}>TaskPPS</span>
          </div>
          <span style={{ fontSize: 13, color: '#7C7F88' }}>
            {activeTab === 'login' ? '登录以继续' : '创建你的账号'}
          </span>
        </div>

        <Tabs
          activeKey={activeTab}
          onChange={(key) => setActiveTab(key as 'login' | 'register')}
          centered
          items={[
            {
              key: 'login',
              label: '登录',
              children: (
                <LoginForm
                  onSubmit={onLogin}
                  loading={loginMutation.isPending}
                  prefillUsername={prefillUsername}
                />
              ),
            },
            {
              key: 'register',
              label: '注册',
              children: <RegisterForm onSubmit={onRegister} loading={registerMutation.isPending} />,
            },
          ]}
        />
      </div>
    </div>
  );
}

// ---------- 登录表单 ----------

interface LoginFormProps {
  onSubmit: (values: LoginRequest) => void;
  loading: boolean;
  prefillUsername: string;
}

function LoginForm({ onSubmit, loading, prefillUsername }: LoginFormProps) {
  const [form] = Form.useForm<LoginRequest>();

  // 注册成功后预填用户名到登录表单
  if (prefillUsername && form.getFieldValue('username') !== prefillUsername) {
    form.setFieldsValue({ username: prefillUsername });
  }

  return (
    <Form<LoginRequest>
      form={form}
      layout="vertical"
      onFinish={onSubmit}
      autoComplete="off"
      style={{ marginTop: 8 }}
    >
      <Form.Item
        name="username"
        label="用户名"
        rules={[
          { required: true, message: '请输入用户名' },
          { min: 3, max: 32, message: '长度 3-32 位' },
          { pattern: USERNAME_PATTERN, message: '仅支持字母、数字、下划线、连字符' },
        ]}
      >
        <Input placeholder="请输入用户名" autoFocus />
      </Form.Item>
      <Form.Item
        name="password"
        label="密码"
        rules={[
          { required: true, message: '请输入密码' },
          { min: 6, max: 64, message: '长度 6-64 位' },
        ]}
      >
        <Input.Password placeholder="请输入密码" />
      </Form.Item>
      <Form.Item name="remember_me" valuePropName="checked" style={{ marginBottom: 12 }}>
        <Checkbox>30天不用免登录</Checkbox>
      </Form.Item>
      <Button type="primary" htmlType="submit" block loading={loading}>
        登录
      </Button>
    </Form>
  );
}

// ---------- 注册表单 ----------

interface RegisterFormProps {
  onSubmit: (values: RegisterRequest) => void;
  loading: boolean;
}

function RegisterForm({ onSubmit, loading }: RegisterFormProps) {
  return (
    <Form<RegisterRequest>
      layout="vertical"
      onFinish={onSubmit}
      autoComplete="off"
      style={{ marginTop: 8 }}
    >
      <Form.Item
        name="username"
        label="用户名"
        rules={[
          { required: true, message: '请输入用户名' },
          { min: 3, max: 32, message: '长度 3-32 位' },
          { pattern: USERNAME_PATTERN, message: '仅支持字母、数字、下划线、连字符' },
        ]}
      >
        <Input placeholder="字母/数字/下划线，3-32 位" />
      </Form.Item>
      <Form.Item
        name="nickname"
        label="昵称"
        rules={[
          { required: true, message: '请输入昵称' },
          { min: 1, max: 32, message: '长度 1-32 位' },
        ]}
      >
        <Input placeholder="显示给他人的名字" />
      </Form.Item>
      <Form.Item
        name="password"
        label="密码"
        rules={[
          { required: true, message: '请输入密码' },
          { min: 6, max: 64, message: '长度 6-64 位' },
        ]}
      >
        <Input.Password placeholder="至少 6 位" />
      </Form.Item>
      <Button type="primary" htmlType="submit" block loading={loading} style={{ marginTop: 8 }}>
        注册
      </Button>
    </Form>
  );
}
