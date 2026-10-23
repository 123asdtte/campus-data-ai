import React from 'react';
import ReactDOM from 'react-dom/client';
import { App as AntdApp, ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import { BrowserRouter } from 'react-router-dom';
import App from './App';
import './styles.css';
import './login.css';

ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
  <React.StrictMode>
    <ConfigProvider
      locale={zhCN}
      theme={{
        token: {
          colorPrimary: '#2563eb',
          colorInfo: '#2563eb',
          colorSuccess: '#16a34a',
          colorWarning: '#d97706',
          colorError: '#dc2626',
          colorText: '#18181b',
          colorTextSecondary: '#71717a',
          colorBorder: '#e4e4e7',
          colorBorderSecondary: '#f1f1f3',
          colorBgLayout: '#f7f7f8',
          borderRadius: 8,
          borderRadiusLG: 12,
          controlHeight: 34,
          fontSize: 13,
          fontFamily:
            "ui-sans-serif, system-ui, -apple-system, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif",
          boxShadow: '0 1px 2px rgba(24,24,27,0.04)',
          wireframe: false,
        },
        components: {
          Layout: { headerBg: '#ffffff', siderBg: '#ffffff', bodyBg: '#f7f7f8' },
          Table: { headerBg: '#fafafa', rowHoverBg: '#fafafa', borderColor: '#e4e4e7' },
          Button: { primaryShadow: 'none', defaultShadow: 'none' },
        },
      }}
    >
      <AntdApp>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </AntdApp>
    </ConfigProvider>
  </React.StrictMode>,
);
