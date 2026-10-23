import { useState } from 'react';
import { Alert, Button, Form, Input, Modal, Tag } from 'antd';
import { ArrowRightOutlined, LockOutlined, SafetyCertificateOutlined, UserOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { login } from '../api/auth';
import { useSession } from '../session/SessionContext';
import LoginBrandPanel from '../components/LoginBrandPanel';

interface DemoAccount {
  role: string;
  username: string;
  password: string;
  note: string;
  color: string;
}

const DEMO_ACCOUNTS: DemoAccount[] = [
  { role: '学生', username: 'SK-2026-000001', password: 'Demo@2026', note: '本人课表 + 课表问答', color: 'green' },
  { role: '辅导员', username: 'counselor01', password: 'Demo@2026', note: '所带班级 / 本班异动', color: 'blue' },
  { role: '学工处', username: 'xgb01', password: 'Demo@2026', note: '工作台 / 报表 / 异动台账', color: 'orange' },
  { role: '管理员', username: 'admin', password: 'admin123', note: '全部页面 / 全局问数', color: 'purple' },
];

export default function LoginPage() {
  const navigate = useNavigate();
  const { refresh } = useSession();
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [demoOpen, setDemoOpen] = useState(false);
  const [form] = Form.useForm<{ username: string; password: string }>();
  const isLocalDemo = typeof window !== 'undefined' && ['127.0.0.1', 'localhost'].includes(window.location.hostname);

  const onFinish = async (values: { username: string; password: string }) => {
    setError('');
    setLoading(true);
    try {
      await login(values.username.trim(), values.password);
      const session = await refresh();
      if (!session) throw new Error('登录成功但读取身份失败，请重试');
      const target = session.roles.includes('student_portal')
        ? '/my-schedule'
        : session.roles.includes('counselor')
          ? '/counselor'
          : session.roles.includes('xgb')
            ? '/workbench'
            : '/';
      navigate(target);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '登录失败');
    } finally {
      setLoading(false);
    }
  };

  const fillDemo = (account: DemoAccount) => {
    form.setFieldsValue({ username: account.username, password: account.password });
    setDemoOpen(false);
  };

  return (
    <div className="login-shell">
      <LoginBrandPanel />

      <main className="login-panel">
        <div className="login-env">
          <span className="login-env-dot" />
          {isLocalDemo ? 'LOCAL DEMO / 本地演示' : 'CAMPUS / 校内授权'}
        </div>

        <div className="login-form-wrap">
          <header className="login-form-head">
            <span className="login-eyebrow">UNIFIED IDENTITY / 统一身份认证</span>
            <h2>登录数据平台</h2>
            <p>使用学校分配的账号登录。系统会按账号角色进入对应工作台，前端不能自行选择身份。</p>
          </header>

          {error ? (
            <div className="login-error" role="alert">
              <Alert type="error" showIcon message={error} />
            </div>
          ) : null}

          <Form
            form={form}
            layout="vertical"
            requiredMark={false}
            onFinish={onFinish}
            className="login-form"
            initialValues={{ username: '', password: '' }}
          >
            <Form.Item
              label="账号"
              name="username"
              rules={[{ required: true, message: '请输入账号' }]}
            >
              <Input
                size="large"
                autoComplete="username"
                prefix={<UserOutlined />}
                placeholder="学号 / 工号 / 管理员账号"
              />
            </Form.Item>
            <Form.Item
              label="密码"
              name="password"
              rules={[{ required: true, message: '请输入密码' }]}
            >
              <Input.Password
                size="large"
                autoComplete="current-password"
                prefix={<LockOutlined />}
                placeholder="请输入密码"
              />
            </Form.Item>

            <div className="login-helper">
              忘记密码？请联系辅导员或学工处重置（短信找回已停用）。
            </div>

            <Button className="login-submit" type="primary" htmlType="submit" size="large" block loading={loading}>
              登录 <ArrowRightOutlined />
            </Button>
          </Form>

          <div className="login-demo-line">
            <span>本地演示账号</span>
            {isLocalDemo ? (
              <button type="button" className="login-demo-trigger" onClick={() => setDemoOpen(true)}>
                查看角色账号
              </button>
            ) : (
              <span>账号由学校统一发放</span>
            )}
          </div>

          <div className="login-security">
            <SafetyCertificateOutlined />
            <span>账号由网关校验 · 角色由组织绑定 · 访问与导出留痕</span>
          </div>

          <footer className="login-form-foot">
            <span>郴州思科职业学院 · 数据管理平台</span>
            <span>仅限校内授权人员使用</span>
          </footer>
        </div>
      </main>

      <Modal
        open={demoOpen}
        title="本地演示账号"
        footer={null}
        onCancel={() => setDemoOpen(false)}
        width={620}
        centered
        className="login-demo-modal"
      >
        <p className="login-demo-note">
          仅用于本地虚构数据演示；正式环境不显示此入口，也不得使用这些共享密码。账号角色由网关绑定，登录后不能切换。
        </p>
        <div className="login-demo-list">
          {DEMO_ACCOUNTS.map((account) => (
            <div className="login-demo-item" key={account.username}>
              <Tag color={account.color}>{account.role}</Tag>
              <div>
                <b>{account.username}</b>
                <small>{account.note}</small>
              </div>
              <code>{account.password}</code>
              <Button size="small" onClick={() => fillDemo(account)}>填入</Button>
            </div>
          ))}
        </div>
      </Modal>
    </div>
  );
}
