import BrandMark from './BrandMark';
import LoginGateArt from './LoginGateArt';

const STATS = [
  { value: '5,581', label: '演示学生' },
  { value: '6', label: '二级学院' },
  { value: '135', label: '标准班级' },
  { value: '04', label: '角色层级' },
];

const ROLES = [
  { no: '01', name: '学生', scope: '本人课表' },
  { no: '02', name: '辅导员', scope: '所带班级' },
  { no: '03', name: '学工处', scope: '全校学工台账' },
  { no: '04', name: '管理员', scope: '配置与审计' },
];

export default function LoginBrandPanel() {
  return (
    <section className="login-brand" aria-label="平台介绍">
      <LoginGateArt />
      <header className="login-brand-top">
        <span className="login-brand-mark"><BrandMark size={30} /></span>
        <span className="login-brand-name">
          郴州思科职业学院
          <small>数据管理平台 · DATA PLATFORM</small>
        </span>
        <span className="login-brand-local">LOCAL / 2026</span>
      </header>

      <div className="login-brand-main">
        <span className="login-kicker">CAMPUS DATA PLATFORM / UNIFIED IDENTITY</span>
        <h1>让数据有来处，<br />让权限有边界。</h1>
        <p>学生档案、课表、学籍异动与报表，按角色流转；登录后只进入你被授权的工作台。</p>
      </div>

      <div className="login-brand-stats">
        {STATS.map((item) => (
          <div key={item.label}>
            <b>{item.value}</b>
            <span>{item.label}</span>
          </div>
        ))}
      </div>

      <div className="login-brand-roles" aria-label="角色层级">
        {ROLES.map((role) => (
          <div key={role.no}>
            <span>{role.no}</span>
            <b>{role.name}</b>
            <small>{role.scope}</small>
          </div>
        ))}
      </div>

      <footer className="login-brand-foot">
        <span>本地演示环境 · 虚构数据 · 非真实人员信息</span>
        <span>网关校验 · 身份绑定 · 操作留痕</span>
      </footer>
    </section>
  );
}
