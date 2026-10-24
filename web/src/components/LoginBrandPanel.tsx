const PRINCIPLES = [
  { no: '01', title: '统一账号', desc: '学号、工号统一认证。' },
  { no: '02', title: '分级授权', desc: '按组织与角色进入工作台。' },
  { no: '03', title: '全程留痕', desc: '查询、导出与变更可审计。' },
];

export default function LoginBrandPanel() {
  return (
    <section className="login-intro" aria-label="平台说明">
      <span className="login-kicker">CAMPUS DATA PLATFORM / 数据管理平台</span>
      <h1>统一身份，<br />分级授权。</h1>
      <p>校内师生的统一数据入口。<br />登录后按组织与角色进入相应工作台，查询、导出与变更全程留痕。</p>

      <div className="login-principles">
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
