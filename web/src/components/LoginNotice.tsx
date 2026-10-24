const NOTICES = [
  { title: '账号范围', desc: '学生使用学号，教职工使用工号。' },
  { title: '密码重置', desc: '忘记密码请联系所在学院或学工处。' },
  { title: '安全提醒', desc: '请勿在公共设备保存密码，使用后及时退出。' },
];

export default function LoginNotice() {
  return (
    <aside className="login-notice" aria-label="登录须知">
      <span className="login-notice-kicker">LOGIN NOTICE / 登录须知</span>
      <h3>账号与安全</h3>
      <dl>
        {NOTICES.map((item) => (
          <div key={item.title}>
            <dt>{item.title}</dt>
            <dd>{item.desc}</dd>
          </div>
        ))}
      </dl>
      <div className="login-notice-help">
        <b>无法登录？</b>
        <p>连续输错密码可能触发临时锁定。如仍无法登录，请联系平台管理员协助处理。</p>
      </div>
    </aside>
  );
}
