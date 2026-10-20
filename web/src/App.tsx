import { Route, Routes, useNavigate } from 'react-router-dom';
import { Button, Result } from 'antd';
import AppLayout from './components/AppLayout';
import HomePage from './pages/HomePage';
import StudentsPage from './pages/StudentsPage';
import ImportPage from './pages/ImportPage';

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
      <Route path="/" element={<AppLayout />}>
        <Route index element={<HomePage />} />
        <Route path="students" element={<StudentsPage />} />
        <Route path="import" element={<ImportPage />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
