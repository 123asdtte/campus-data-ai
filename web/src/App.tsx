import { lazy } from 'react';
import type { ReactNode } from 'react';
import { Navigate, Route, Routes, useNavigate } from 'react-router-dom';
import { Button, Result, Spin } from 'antd';
import AppLayout from './components/AppLayout';
import { SessionProvider, useSession } from './session/SessionContext';
import LoginPage from './pages/LoginPage';
import { isLoggedIn } from './api/auth';

// 业务页按路由拆包：登录页保持同步加载，其余页面首次进入时再拉取。
const HomePage = lazy(() => import('./pages/HomePage'));
const StudentsPage = lazy(() => import('./pages/StudentsPage'));
const ImportPage = lazy(() => import('./pages/ImportPage'));
const WorkbenchPage = lazy(() => import('./pages/WorkbenchPage'));
const ReportsPage = lazy(() => import('./pages/ReportsPage'));
const ChangesPage = lazy(() => import('./pages/ChangesPage'));
const CounselorPage = lazy(() => import('./pages/CounselorPage'));
const StudentPortalPage = lazy(() => import('./pages/StudentPortalPage'));
const PipelinePage = lazy(() => import('./pages/PipelinePage'));
const AssistantPage = lazy(() => import('./pages/AssistantPage'));
const StudentSchedulePage = lazy(() => import('./pages/StudentSchedulePage'));

/**
 * PR-D 登录守门：所有业务页面必须持有网关 token。
 * 未登录时直接跳转登录页，页面不再走匿名 `/api` 旧入口。
 */
function RequireLogin({ children }: { children: ReactNode }) {
  if (!isLoggedIn()) {
    return <Navigate to="/login" replace />;
  }
  return <>{children}</>;
}

function homeFor(roles: string[]): string {
  if (roles.includes('student_portal')) return '/my-schedule';
  if (roles.includes('counselor')) return '/counselor';
  if (roles.includes('xgb')) return '/workbench';
  return '/';
}

function RequireRoles({ allow, children }: { allow: string[]; children: ReactNode }) {
  const { session, loading } = useSession();
  if (loading) {
    return (
      <div style={{ minHeight: 320, display: 'grid', placeItems: 'center' }}>
        <Spin />
      </div>
    );
  }
  if (!session) {
    return <Navigate to="/login" replace />;
  }
  if (!allow.some((role) => session.roles.includes(role))) {
    return <Navigate to={homeFor(session.roles)} replace />;
  }
  return <>{children}</>;
}

function StaffHome() {
  const { session, loading } = useSession();
  if (loading) {
    return (
      <div style={{ minHeight: 320, display: 'grid', placeItems: 'center' }}>
        <Spin />
      </div>
    );
  }
  if (!session) return <Navigate to="/login" replace />;
  if (session.roles.includes('student_portal')) return <Navigate to="/my-schedule" replace />;
  if (session.roles.includes('counselor')) return <Navigate to="/counselor" replace />;
  if (session.roles.includes('xgb')) return <Navigate to="/workbench" replace />;
  return <HomePage />;
}

function NotFound() {
  const navigate = useNavigate();
  return (
    <Result
      status="404"
      title="页面不存在"
      subTitle="该地址没有对应页面，请从左侧菜单进入。"
      extra={
        <Button type="primary" onClick={() => navigate('/')}>
          返回首页
        </Button>
      }
    />
  );
}

const STAFF = ['xgb', 'superadmin'];
const ADMIN_ONLY = ['superadmin'];
const COUNSELOR_OR_STAFF = ['counselor', 'xgb', 'superadmin'];

export default function App() {
  return (
    <SessionProvider>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/"
          element={
            <RequireLogin>
              <AppLayout />
            </RequireLogin>
          }
        >
          <Route index element={<StaffHome />} />
          <Route path="my-schedule" element={<RequireRoles allow={['student_portal']}><StudentSchedulePage /></RequireRoles>} />
          <Route path="students" element={<RequireRoles allow={ADMIN_ONLY}><StudentsPage /></RequireRoles>} />
          <Route path="import" element={<RequireRoles allow={ADMIN_ONLY}><ImportPage /></RequireRoles>} />
          <Route path="workbench" element={<RequireRoles allow={STAFF}><WorkbenchPage /></RequireRoles>} />
          <Route path="pipeline" element={<RequireRoles allow={STAFF}><PipelinePage /></RequireRoles>} />
          <Route path="reports" element={<RequireRoles allow={STAFF}><ReportsPage /></RequireRoles>} />
          <Route path="changes" element={<RequireRoles allow={COUNSELOR_OR_STAFF}><ChangesPage /></RequireRoles>} />
          <Route path="counselor" element={<RequireRoles allow={COUNSELOR_OR_STAFF}><CounselorPage /></RequireRoles>} />
          <Route path="portal" element={<RequireRoles allow={['superadmin']}><StudentPortalPage /></RequireRoles>} />
          <Route path="assistant" element={<RequireRoles allow={['superadmin']}><AssistantPage /></RequireRoles>} />
          <Route path="*" element={<RequireRoles allow={COUNSELOR_OR_STAFF}><NotFound /></RequireRoles>} />
        </Route>
      </Routes>
    </SessionProvider>
  );
}
