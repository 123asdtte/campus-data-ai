import { Layout } from 'antd';
import { AppstoreOutlined, CloudUploadOutlined, DatabaseOutlined, FileTextOutlined, FormOutlined, InboxOutlined, LogoutOutlined, SwapOutlined, TeamOutlined, UserOutlined } from '@ant-design/icons';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { getLoginUser, logout } from '../api/auth';
import BrandMark from './BrandMark';

const { Sider, Content } = Layout;

const NAV = [
  { to: '/', label: '总览', icon: <AppstoreOutlined /> },
  { to: '/workbench', label: '数据工作台', icon: <DatabaseOutlined /> },
  { to: '/pipeline', label: '资料库流水线', icon: <InboxOutlined /> },
  { to: '/reports', label: '报表中心', icon: <FileTextOutlined /> },
  { to: '/changes', label: '学籍异动', icon: <SwapOutlined /> },
  { to: '/counselor', label: '辅导员台', icon: <UserOutlined /> },
  { to: '/portal', label: '学生自助', icon: <FormOutlined /> },
  { to: '/students', label: '学生信息', icon: <TeamOutlined /> },
  { to: '/import', label: '数据导入', icon: <CloudUploadOutlined /> },
];

const TITLE: Record<string, string> = {
  '/': '总览',
  '/students': '学生信息',
  '/import': '数据导入',
  '/workbench': '数据工作台',
  '/pipeline': '资料库流水线',
  '/reports': '报表中心',
  '/changes': '学籍异动',
  '/counselor': '辅导员工作台',
  '/portal': '学生自助填报',
};

export default function AppLayout() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const active = NAV.find((item) => (item.to === '/' ? pathname === '/' : pathname.startsWith(item.to)));
  // 显示的是网关登录账号，不再使用前端自填的 X-Actor 展示名
  const username = getLoginUser() ?? '未知用户';
  const initials = username.slice(0, 1).toUpperCase();

  const onLogout = () => {
    logout();
    navigate('/login', { replace: true });
  };

  return (
    <Layout className="app-shell">
      <Sider width={232} className="app-sider" theme="light">
        <div className="app-brand">
          <span className="app-brand-mark">
            <BrandMark size={24} />
          </span>
          <div className="app-brand-text">
            <div className="app-brand-title">郴州思科职业学院</div>
            <div className="app-brand-sub">数据管理平台 · Data Platform</div>
          </div>
        </div>

        <nav className="app-nav">
          <div className="app-nav-label">业务模块</div>
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/'}
              className={({ isActive }) => `app-nav-item${isActive ? ' is-active' : ''}`}
            >
              {item.icon}
              <span>{item.label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="app-sider-footer">
          <div className="app-env">
            <span className="app-env-dot" />
            本地测试 · 虚构数据
          </div>
        </div>
      </Sider>

      <Layout>
        <header className="app-header">
          <div className="app-header-left">
            <span className="app-crumb">数据管理</span>
            <span className="app-crumb-sep">/</span>
            <span className="app-header-title">{TITLE[active?.to ?? ''] ?? '总览'}</span>
          </div>
          <div className="app-header-right">
            <span className="app-actor">
              <span className="app-actor-avatar">{initials}</span>
              {username}（已登录）
            </span>
            <button type="button" className="app-nav-item" style={{ width: 'auto' }} onClick={onLogout}>
              <LogoutOutlined />
              <span>退出</span>
            </button>
          </div>
        </header>

        <Content className="app-content">
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}
