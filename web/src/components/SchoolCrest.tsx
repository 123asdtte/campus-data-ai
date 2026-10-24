import { useId } from 'react';

const STAR =
  'M0 -4 L1.1 -1.3 L4 -1.3 L1.8 0.6 L2.6 3.5 L0 2 L-2.6 3.5 L-1.8 0.6 L-4 -1.3 L-1.1 -1.3 Z';

export default function SchoolCrest({ className }: { className?: string }) {
  const maskId = `crest-ribbon-${useId().replace(/:/g, '')}`;

  return (
    <svg
      className={`school-crest${className ? ` ${className}` : ''}`}
      viewBox="0 0 72 64"
      width="72"
      height="64"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <defs>
        <mask id={maskId}>
          <rect width="72" height="64" fill="#fff" />
          <path
            d="M15 44c11 3.5 31 3.5 42 0l-1 8c-11 3.5-29 3.5-40 0l-1-8Z"
            fill="#000"
          />
        </mask>
      </defs>

      <g mask={`url(#${maskId})`}>
        {/* 盾牌 */}
        <path d="M16 11.5c10-3.5 30-3.5 40 0l1.2 22.2c0 10.2-7.8 17.8-21.2 23.8C22.6 51.5 14.8 43.9 14.8 33.7L16 11.5Z" />
        {/* 底部横线 */}
        <path d="M28.5 54.5h15M31.5 56.5h9" opacity="0.7" />
      </g>

      {/* 五星 */}
      <g fill="currentColor" stroke="none">
        <path d={STAR} transform="translate(36 19)" />
        <path d={STAR} transform="translate(29 22) scale(0.82)" />
        <path d={STAR} transform="translate(43 22) scale(0.82)" />
        <path d={STAR} transform="translate(23 26) scale(0.65)" />
        <path d={STAR} transform="translate(49 26) scale(0.65)" />
      </g>

      {/* 校门 */}
      <g>
        <path d="M22 32 26 28h20l4 4H22Z" />
        <path d="M24.5 30h23M22 32h28M22 43h28" strokeWidth="1.6" />
        <path d="M26 32v11M31 32v11M41 32v11M46 32v11" strokeWidth="1.6" />
        <path d="M34 43v-6h4v6" strokeWidth="1.6" />
      </g>

      {/* 飘带 */}
      <g>
        <path d="M15 44c11 3.5 31 3.5 42 0" />
        <path d="M16 52c11 3.5 29 3.5 40 0" />
        <path d="M5 42.5 15 44.5 13.5 51.5 3.5 49.5Z" />
        <path d="M67 42.5 57 44.5 58.5 51.5 68.5 49.5Z" />
        <path d="M10 45.2 9 49.2M62 45.2 63 49.2" strokeWidth="1.4" opacity="0.8" />
      </g>
    </svg>
  );
}
