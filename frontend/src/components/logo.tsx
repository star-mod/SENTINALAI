type LogoMarkProps = {
  size?: number;
  title?: string;
};

/** SentinelAI mark: a shield with a watchful eye. Pure SVG, no image file needed. */
export default function LogoMark({ size = 48, title = "SentinelAI logo" }: LogoMarkProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" fill="none" role="img" aria-label={title}>
      <path
        d="M32 3 57 11V30C57 45 46 55 32 61 18 55 7 45 7 30V11L32 3Z"
        fill="#0B1B3A"
        stroke="#2E9BFF"
        strokeWidth="4"
        strokeLinejoin="round"
      />
      <path d="M13 32C20 21 44 21 51 32 44 43 20 43 13 32Z" fill="#F2F7FF" />
      <circle cx="32" cy="32" r="8" fill="#2E8BFF" />
      <circle cx="29.5" cy="29.5" r="2.6" fill="#CFE6FF" />
    </svg>
  );
}
