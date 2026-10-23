import LoginGateArt from './LoginGateArt';

const PRINCIPLES = [
  { no: '01', title: '统一身份', desc: '使用学校统一账号登录，无需注册。' },
  { no: '02', title: '分级授权', desc: '按组织、角色与数据范围授权。' },
  { no: '03', title: '全程留痕', desc: '查询、导出与变更均可审计。' },
];

export default function LoginBrandPanel() {
  return (
    <section className="login-brand" aria-label="平台说明">
      <LoginGateArt />
      <div className="login-brand-main">
        <span className="login-kicker">CAMPUS DATA PLATFORM / 统一数据入口</span>
        <h1>让数据有来处，<br />让权限有边界。</h1>
        <p>校内师生的统一数据入口。登录后按组织与角色进入工作台，查询、导出与变更全程留痕。</p>
      </div>

      <div className="login-principles" aria-label="平台原则">
        {PRINCIPLES.map((item) => (
          <div key={item.no}>
            <span>{item.no}</span>
            <b>{item.title}</b>
            <small>{item.desc}</small>
          </div>
        ))}
      </div>
    </section>
  );
}
