import { useState } from 'react';
import { Alert, Button, Card, Form, Input, Typography } from 'antd';
import { useNavigate } from 'react-router-dom';
import { login } from '../api/auth';

/**
 * PR-B 登录页：使用 RuoYi 原生账号登录，成功后进入学生查询。
 * PR-D 起，学生、聚合与导入域请求全部经 Java 网关注入可信身份。
 */
export default function LoginPage() {
  const navigate = useNavigate();
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const onFinish = async (values: { username: string; password: string }) => {
    setError('');
    setLoading(true);
    try {
      await login(values.username.trim(), values.password);
      navigate('/students');
    } catch (err) {
      setError(err instanceof Error ? err.message : '登录失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', padding: 24 }}>
      <Card style={{ width: 380 }}>
        <Typography.Title level={4} style={{ marginTop: 0 }}>
          校园数据平台登录
        </Typography.Title>
        <Typography.Paragraph type="secondary">
          使用校园账号登录后，学生查询与修改将经由可信网关访问。
        </Typography.Paragraph>
        {error ? <Alert type="error" message={error} style={{ marginBottom: 16 }} /> : null}
        <Form layout="vertical" onFinish={onFinish} initialValues={{ username: '', password: '' }}>
          <Form.Item
            label="账号"
            name="username"
            rules={[{ required: true, message: '请输入账号' }]}
          >
            <Input autoComplete="username" placeholder="例如 admin" />
          </Form.Item>
          <Form.Item
            label="密码"
            name="password"
            rules={[{ required: true, message: '请输入密码' }]}
          >
            <Input.Password autoComplete="current-password" />
          </Form.Item>
          <Button type="primary" htmlType="submit" block loading={loading}>
            登录
          </Button>
        </Form>
        {import.meta.env.DEV ? (
          <Typography.Paragraph type="secondary" style={{ marginTop: 16, marginBottom: 0 }}>
            开发环境默认账号：admin / admin123（仅限本地隔离环境）。
          </Typography.Paragraph>
        ) : null}
      </Card>
    </div>
  );
}
