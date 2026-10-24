export default function LoginDataArt() {
  return (
    <svg className="login-data-art" viewBox="0 0 520 460" fill="none" aria-hidden="true" focusable="false">
      <ellipse cx="260" cy="404" rx="190" ry="20" fill="#e6f0f9" opacity="0.55" />
      <ellipse cx="260" cy="270" rx="235" ry="105" stroke="#c6d9e9" strokeWidth="1" opacity="0.55" />
      <ellipse cx="260" cy="270" rx="180" ry="78" stroke="#d4e3ef" strokeWidth="1" opacity="0.5" />
      <path d="M260 108v304" stroke="#c6d9e9" strokeWidth="1" strokeDasharray="3 7" opacity="0.5" />

      <g strokeLinecap="round" strokeLinejoin="round">
        {/* 底层 */}
        <path d="M60 300v18l200 100v-18L60 300z" fill="#e7f2fa" stroke="#aac6dd" strokeWidth="1.2" />
        <path d="M460 300v18L260 418v-18l200-100z" fill="#d8e9f5" stroke="#aac6dd" strokeWidth="1.2" />
        <path d="M60 300 260 200l200 100-200 100z" fill="#f6fbff" stroke="#aac6dd" strokeWidth="1.2" />

        {/* 中层 */}
        <path d="M95 250v16l165 83v-16L95 250z" fill="#e9f4fc" stroke="#9dbdd8" strokeWidth="1.2" />
        <path d="M425 250v16l-165 83v-16l165-83z" fill="#dcecf8" stroke="#9dbdd8" strokeWidth="1.2" />
        <path d="M95 250 260 167l165 83-165 83z" fill="#f3f9fe" stroke="#9dbdd8" strokeWidth="1.2" />

        {/* 顶层 */}
        <path d="M130 200v16l130 65v-16L130 200z" fill="#e6f2fb" stroke="#8fb4d2" strokeWidth="1.2" />
        <path d="M390 200v16l-130 65v-16l130-65z" fill="#d7e9f6" stroke="#8fb4d2" strokeWidth="1.2" />
        <path d="M130 200 260 135l130 65-130 65z" fill="#f0f8fe" stroke="#8fb4d2" strokeWidth="1.2" />

        {/* 节点 */}
        <circle cx="260" cy="200" r="4" fill="#2f6fa3" stroke="#fff" strokeWidth="1.5" />
        <circle cx="260" cy="250" r="3.5" fill="#fff" stroke="#2f6fa3" strokeWidth="1.2" />
        <circle cx="260" cy="300" r="3.5" fill="#fff" stroke="#2f6fa3" strokeWidth="1.2" />
        <circle cx="60" cy="300" r="3" fill="#fff" stroke="#8fb4d2" strokeWidth="1.2" />
        <circle cx="460" cy="300" r="3" fill="#fff" stroke="#8fb4d2" strokeWidth="1.2" />
        <circle cx="130" cy="200" r="2.5" fill="#fff" stroke="#8fb4d2" strokeWidth="1" />
        <circle cx="390" cy="200" r="2.5" fill="#fff" stroke="#8fb4d2" strokeWidth="1" />

        {/* 悬浮记录卡 */}
        <g transform="translate(344 72) rotate(7)">
          <rect width="116" height="78" rx="10" fill="#fff" stroke="#c6d9e9" strokeWidth="1.2" />
          <rect x="14" y="16" width="52" height="5" rx="2.5" fill="#d7e9f6" />
          <rect x="14" y="30" width="80" height="4" rx="2" fill="#e7f2fa" />
          <rect x="14" y="41" width="66" height="4" rx="2" fill="#e7f2fa" />
          <rect x="14" y="52" width="42" height="4" rx="2" fill="#e7f2fa" />
          <circle cx="98" cy="18" r="4" fill="#2f6fa3" />
        </g>

        {/* 粒子与轨道节点 */}
        <circle cx="440" cy="52" r="2" fill="#b9cee2" />
        <circle cx="78" cy="112" r="2.5" fill="#c6d9e9" />
        <circle cx="480" cy="372" r="2" fill="#c6d9e9" />
        <circle cx="468" cy="210" r="2" fill="#c6d9e9" />
        <circle cx="495" cy="270" r="3" fill="#2f6fa3" opacity="0.7" />
        <circle cx="25" cy="270" r="3" fill="#2f6fa3" opacity="0.5" />
      </g>
    </svg>
  );
}
