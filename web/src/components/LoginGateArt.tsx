export default function LoginGateArt() {
  return (
    <svg
      className="login-gate-art"
      viewBox="0 0 760 620"
      fill="none"
      aria-hidden="true"
      focusable="false"
    >
      <g stroke="currentColor" strokeWidth="1.1" strokeLinecap="round" strokeLinejoin="round">
        {/* 校门：拱形门洞、基座与台阶 */}
        <path d="M96 500V268c0-96 76-174 170-174s170 78 170 174v232" />
        <path d="M148 500V272c0-66 53-120 118-120s118 54 118 120v228" />
        <path d="M62 500h430" />
        <path d="M210 500v-98h112v98" />
        <path d="M238 500v-54h56v54" />
        <path d="M92 268h348" />
        {/* 进阶弧线与台阶 */}
        <path d="M128 536c62 22 148 22 210 0" opacity="0.6" />
        <path d="M106 568c82 26 184 26 266 0" opacity="0.4" />
        <path d="M266 126v-38M247 107h38" />
        {/* 右侧数据刻度与轨迹 */}
        <circle cx="538" cy="238" r="86" opacity="0.65" />
        <circle cx="538" cy="238" r="4" fill="currentColor" stroke="none" />
        <path d="M538 152v-26M538 350v-26M452 238h-26M650 238h-26" opacity="0.5" />
        <path d="M470 96c56 24 104 72 130 132" opacity="0.45" />
        <path d="M500 64c76 32 142 98 174 182" opacity="0.25" />
        {/* 台账线 */}
        <path d="M470 400h214M470 424h168M470 448h196M470 472h132" opacity="0.45" />
        <path d="M470 400v72" opacity="0.6" />
        <path d="M704 400v72" opacity="0.6" />
      </g>
    </svg>
  );
}
