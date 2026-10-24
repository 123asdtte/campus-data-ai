import { useEffect, useRef, useState } from 'react';
import { Alert, Button, Checkbox, Form, Input, Modal } from 'antd';
import { LockOutlined, UserOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import LoginBrandPanel from '../components/LoginBrandPanel';
import LoginDataArt from '../components/LoginDataArt';
import { login, consumeExpiredNotice, SESSION_EXPIRED_EVENT } from '../api/auth';
import { useSession } from '../session/SessionContext';

const REMEMBER_KEY = 'campus.login.username';

interface LoginValues {
  username: string;
  password: string;
  remember?: boolean;
}

export default function LoginPage() {
  const navigate = useNavigate();
  const { session, refresh } = useSession();
  const [initialUser] = useState(() => window.localStorage.getItem(REMEMBER_KEY) ?? '');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const frameRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const frame = frameRef.current;
    if (!frame) return;
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const finePointer = window.matchMedia('(pointer: fine)').matches;
    if (reduceMotion || !finePointer) return;

    let raf = 0;
    let x = 0;
    let y = 0;
    const apply = () => {
      raf = 0;
      frame.style.setProperty('--parallax-x', `${(x * -10).toFixed(1)}px`);
      frame.style.setProperty('--parallax-y', `${(y * -8).toFixed(1)}px`);
    };
    const onMove = (event: PointerEvent) => {
      x = event.clientX / window.innerWidth - 0.5;
      y = event.clientY / window.innerHeight - 0.5;
      if (!raf) raf = window.requestAnimationFrame(apply);
    };
    const reset = () => {
      x = 0;
      y = 0;
      if (!raf) raf = window.requestAnimationFrame(apply);
    };

    window.addEventListener('pointermove', onMove, { passive: true });
    document.documentElement.addEventListener('pointerleave', reset);
    window.addEventListener('blur', reset);
    return () => {
      window.removeEventListener('pointermove', onMove);
      document.documentElement.removeEventListener('pointerleave', reset);
      window.removeEventListener('blur', reset);
      if (raf) window.cancelAnimationFrame(raf);
    };
  }, []);

  useEffect(() => {
    if (consumeExpiredNotice()) setError('登录状态已失效，请重新登录');
    const onExpired = () => setError('登录状态已失效，请重新登录');
    window.addEventListener(SESSION_EXPIRED_EVENT, onExpired);
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, onExpired);
  }, []);

  useEffect(() => {
    if (!session) return;
    const target = session.roles.includes('student_portal')
      ? '/my-schedule'
      : session.roles.includes('counselor')
        ? '/counselor'
        : session.roles.includes('xgb')
          ? '/workbench'
          : '/';
    navigate(target, { replace: true });
  }, [session, navigate]);

  const onFinish = async (values: LoginValues) => {
    const username = values.username.trim();
    setError('');
    setLoading(true);
    try {
      await login(username, values.password);
      const session = await refresh();
      if (!session) throw new Error('登录成功但读取身份失败，请重试');
      if (values.remember) window.localStorage.setItem(REMEMBER_KEY, username);
      else window.localStorage.removeItem(REMEMBER_KEY);
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
      <div className="login-frame" ref={frameRef}>
        <LoginBrandPanel />

        <main className="login-right">
          <div className="login-right-meta">
            <button type="button" className="login-help-link" onClick={() => setHelpOpen(true)}>
              使用帮助
            </button>
            <i aria-hidden="true" />
            <span>统一身份认证平台</span>
          </div>

          <section className="login-card" aria-labelledby="login-title">
            <span className="login-card-fold-top" aria-hidden="true" />
            <span className="login-card-fold-bottom" aria-hidden="true" />

            <div className="login-card-body">
              <div className="login-card-tabs">
                <h2 id="login-title" className="login-tab">账号登录</h2>
                <span className="login-tab-note">统一身份认证</span>
              </div>

              <p className="login-card-sub">使用学校统一账号登录，系统将按角色进入工作台。</p>

              {error ? (
                <div className="login-error">
                  <Alert type="error" showIcon message={error} />
                </div>
              ) : null}

              <Form
                layout="vertical"
                requiredMark={false}
                onFinish={onFinish}
                className="login-form"
                initialValues={{
                  username: initialUser,
                  password: '',
                  remember: Boolean(initialUser),
                }}
              >
                <Form.Item
                  name="username"
                  rules={[{ required: true, message: '请输入账号' }]}
                >
                  <Input
                    size="large"
                    autoComplete="username"
                    aria-label="账号"
                    prefix={<UserOutlined />}
                    placeholder="请输入学号或工号"
                  />
                </Form.Item>
                <Form.Item
                  name="password"
                  rules={[{ required: true, message: '请输入密码' }]}
                >
                  <Input.Password
                    size="large"
                    autoComplete="current-password"
                    aria-label="密码"
                    prefix={<LockOutlined />}
                    placeholder="请输入密码"
                  />
                </Form.Item>

                <div className="login-options">
                  <Form.Item name="remember" valuePropName="checked" noStyle>
                    <Checkbox>记住账号</Checkbox>
                  </Form.Item>
                  <button type="button" className="login-forgot" onClick={() => setHelpOpen(true)}>
                    忘记密码？
                  </button>
                </div>

                <Button className="login-submit" type="primary" htmlType="submit" size="large" block loading={loading}>
                  登录
                </Button>
              </Form>
            </div>
          </section>

          <div className="login-data-art-wrap" aria-hidden="true">
            <span className="login-art-halo" />
            <span className="login-art-ring" />
            <span className="login-art-particle login-art-particle-a" />
            <span className="login-art-particle login-art-particle-b" />
            <span className="login-art-particle login-art-particle-c" />
            <LoginDataArt />
          </div>
        </main>
      </div>

      <footer className="login-footer">
        <span>© {new Date().getFullYear()} 郴州思科职业学院 · 数据管理平台</span>
        <span>仅限校内授权人员使用</span>
      </footer>

      <Modal
        open={helpOpen}
        title="登录帮助"
        footer={null}
        centered
        width={440}
        onCancel={() => setHelpOpen(false)}
      >
        <div className="login-help">
          <p><b>账号</b><span>学生使用学号，教职工使用工号。</span></p>
          <p><b>密码</b><span>忘记密码请联系所在学院或学工处重置。</span></p>
          <p><b>安全</b><span>请勿在公共设备保存密码，使用后及时退出。</span></p>
        </div>
      </Modal>
    </div>
  );
}
