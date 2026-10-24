import LoginGateArt from './LoginGateArt';
import SchoolCrest from './SchoolCrest';

export default function LoginBrandPanel() {
  return (
    <aside className="login-brand" aria-label="平台介绍">
      <span className="login-brand-glow" aria-hidden="true" />
      <LoginGateArt />
      <div className="login-brand-logo">
        <span className="login-brand-mark">
          <SchoolCrest />
        </span>
        <span className="login-brand-name">
          <b>郴州思科职业学院</b>
          <small>数据管理平台 · DATA PLATFORM</small>
        </span>
      </div>

      <div className="login-brand-main">
        <span className="login-brand-welcome">欢迎登录</span>
        <h1>校园数据管理平台</h1>
        <span className="login-brand-en">CAMPUS DATA PLATFORM</span>
        <span className="login-brand-rule" aria-hidden="true" />
        <p>统一身份 · 分级授权 · 全程留痕</p>
      </div>
    </aside>
  );
}
