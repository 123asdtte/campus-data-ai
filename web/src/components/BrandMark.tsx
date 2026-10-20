/**
 * 品牌标记：取自校徽的三个要素——校门、三台进阶弧线、以及整体竖向秩序。
 * 纯线条（1.05px 描边）、无填充，与 hairline 规范一致。
 * 在 24px 下三弧过密，故保留两弧以维持可辨识度。
 */
export default function BrandMark({ size = 24 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.05"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {/* 校门：拱形门洞 + 基座 */}
      <path d="M6.6 12.8V9.4a5.4 5.4 0 0 1 10.8 0v3.4" />
      <path d="M4.4 12.8h15.2" />
      {/* 三台进阶：两道弧线，末道更淡 */}
      <path d="M7.9 16.1c2.3 1.35 5.9 1.35 8.2 0" />
      <path d="M7.9 18.9c2.3 1.35 5.9 1.35 8.2 0" opacity="0.5" />
    </svg>
  );
}
