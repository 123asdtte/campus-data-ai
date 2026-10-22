import type { ReactNode } from 'react';
import { Navigate, Route, Routes, useNavigate } from 'react-router-dom';
import { Button, Result } from 'antd';
import AppLayout from './components/AppLayout';
import HomePage from './pages/HomePage';
import StudentsPage from './pages/StudentsPage';
import ImportPage from './pages/ImportPage';
import LoginPage from './pages/LoginPage';
import { isLoggedIn } from './api/auth';

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

function NotFound() {
  const navigate = useNavigate();
  return (
    <Result
      status="404"
      title="页面不存在"
      subTitle="该地址没有对应页面，请从左侧菜单进入。"
      extra={
        <Button type="primary" onClick={() => navigate('/students')}>
          返回学生查询
        </Button>
      }
    />
  );
}

export default function App() {
  return (
    <Routes>
      {/* 登录页独立于主布局，避免侧边栏干扰 */}
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/"
        element={
          <RequireLogin>
            <AppLayout />
          </RequireLogin>
        }
      >
        <Route index element={<HomePage />} />
        <Route path="students" element={<StudentsPage />} />
        <Route path="import" element={<ImportPage />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
