import { useState } from 'react';
import { Alert, Button, Form, Input } from 'antd';
import { LockOutlined, SafetyCertificateOutlined, UserOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import BrandMark from '../components/BrandMark';
import LoginBrandPanel from '../components/LoginBrandPanel';
import { login } from '../api/auth';
import { useSession } from '../session/SessionContext';

export default function LoginPage() {
  const navigate = useNavigate();
  const { refresh } = useSession();
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

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
      setError(reason instanceof Error ? reason.message : '登录失败，请稍后重试。');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-shell">
      <div className="login-frame">
        <header className="login-header">
          <div className="login-lockup">
            <span className="login-lockup-mark"><BrandMark size={30} /></span>
            <span className="login-lockup-text">
              <b>郴州思科职业学院</b>
              <small>数据管理平台 · DATA PLATFORM</small>
            </span>
          </div>
          <div className="login-header-meta">
            <SafetyCertificateOutlined />
            <span>统一身份认证</span>
            <i aria-hidden="true" />
            <span className="login-header-en">UNIFIED IDENTITY</span>
          </div>
        </header>

        <div className="login-body">
          <LoginBrandPanel />

          <main className="login-panel">
            <div className="login-form-wrap">
              <header className="login-form-head">
                <span className="login-eyebrow">ACCOUNT SIGN-IN / 账号登录</span>
                <h2>统一身份登录</h2>
                <p>使用学校统一账号登录，系统将按账号角色进入工作台。</p>
              </header>

              {error ? (
                <div className="login-error" role="alert">
                  <Alert type="error" showIcon message={error} />
                </div>
              ) : null}

              <Form
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
                    placeholder="请输入学号或工号"
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

                <div className="login-helper">忘记密码请联系所在学院或学工处重置。</div>

                <Button className="login-submit" type="primary" htmlType="submit" size="large" block loading={loading}>
                  登录
                </Button>
              </Form>

              <div className="login-security">
                <SafetyCertificateOutlined />
                <span>账号由统一身份平台校验 · 访问与导出操作留痕</span>
              </div>
            </div>
          </main>
        </div>

        <footer className="login-footer">
          <span>© {new Date().getFullYear()} 郴州思科职业学院 · 数据管理平台</span>
          <span>仅限校内授权人员使用 · 推荐使用 Chrome / Edge 浏览器</span>
        </footer>
      </div>
    </div>
  );
}
