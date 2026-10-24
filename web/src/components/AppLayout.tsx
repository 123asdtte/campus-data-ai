import { Suspense } from 'react';
import { Layout, Spin } from 'antd';
import { AppstoreOutlined, CalendarOutlined, CloudUploadOutlined, DatabaseOutlined, FileTextOutlined, InboxOutlined, LogoutOutlined, RobotOutlined, SwapOutlined, TeamOutlined, UserOutlined } from '@ant-design/icons';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { getLoginUser, logout } from '../api/auth';
import { PAGE_TITLES } from '../pageTitles';
import { useSession } from '../session/SessionContext';
import SchoolCrest from './SchoolCrest';
import FloatingAssistant from './FloatingAssistant';

const { Sider, Content } = Layout;

const STAFF_NAV = [
  { to: '/', label: '总览', icon: <AppstoreOutlined /> },
  { to: '/workbench', label: '数据工作台', icon: <DatabaseOutlined /> },
  { to: '/pipeline', label: '资料库流水线', icon: <InboxOutlined /> },
  { to: '/reports', label: '报表中心', icon: <FileTextOutlined /> },
  { to: '/assistant', label: 'AI 问数', icon: <RobotOutlined /> },
  { to: '/changes', label: '学籍异动', icon: <SwapOutlined /> },
  { to: '/counselor', label: '辅导员台', icon: <UserOutlined /> },
  { to: '/students', label: '学生信息', icon: <TeamOutlined /> },
  { to: '/import', label: '数据导入', icon: <CloudUploadOutlined /> },
];

const STUDENT_NAV = [
  { to: '/my-schedule', label: '我的课表', icon: <CalendarOutlined /> },
];

function roleLabel(roles: string[]): string {
  if (roles.includes('student_portal')) return '学生';
  if (roles.includes('counselor')) return '辅导员';
  if (roles.includes('xgb')) return '学工处';
  if (roles.includes('superadmin')) return '管理员';
  return '用户';
}

export default function AppLayout() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const { session, loading, clear } = useSession();
  const roles = session?.roles ?? [];
  const isStudent = roles.includes('student_portal');
  const isCounselor = roles.includes('counselor');
  const isXgb = roles.includes('xgb');
  let nav = STAFF_NAV;
  if (isStudent) {
    nav = STUDENT_NAV;
  } else if (isCounselor) {
    nav = STAFF_NAV.filter((item) => ['/counselor', '/changes'].includes(item.to));
  } else if (isXgb) {
    nav = STAFF_NAV.filter((item) => ['/workbench', '/pipeline', '/reports', '/changes', '/counselor'].includes(item.to));
  }
  const active = nav.find((item) => (item.to === '/' ? pathname === '/' : pathname.startsWith(item.to)));
  const username = session?.user.nickName ?? getLoginUser() ?? '未知用户';
  const uid = session?.user.userName ?? '';
  const initials = username.slice(0, 1).toUpperCase();
  const role = loading ? '身份加载中' : roleLabel(roles);

  const onLogout = () => {
    clear();
    logout();
    navigate('/login', { replace: true });
  };

  return (
    <Layout className="app-shell">
      <Sider width={232} className="app-sider" theme="light">
        <div className="app-brand">
          <span className="app-brand-mark">
            <SchoolCrest />
          </span>
          <div className="app-brand-text">
            <div className="app-brand-title">郴州思科职业学院</div>
            <div className="app-brand-sub">数据管理平台 · Data Platform</div>
          </div>
        </div>

        <nav className="app-nav">
          <div className="app-nav-label">业务模块</div>
          {nav.map((item) => (
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
            <span className="app-header-title">{PAGE_TITLES[active?.to ?? ''] ?? '总览'}</span>
          </div>
          <div className="app-header-right">
            <span className="app-actor" title={uid ? `UID：${uid}` : undefined}>
              <span className="app-actor-avatar">{initials}</span>
              {username}（{role}）
            </span>
            <button type="button" className="app-nav-item" style={{ width: 'auto' }} onClick={onLogout}>
              <LogoutOutlined />
              <span>退出</span>
            </button>
          </div>
        </header>

        <Content className="app-content">
          <Suspense fallback={<div style={{ minHeight: 320, display: 'grid', placeItems: 'center' }}><Spin /></div>}>
            <Outlet />
          </Suspense>
        </Content>

        <FloatingAssistant />
      </Layout>
    </Layout>
  );
}
