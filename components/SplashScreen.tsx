
import { useEffect } from "react";

type SplashScreenProps = {
  onComplete: () => void;
};

export default function SplashScreen({
  onComplete,
}: SplashScreenProps) {
  useEffect(() => {
    const timer = window.setTimeout(onComplete, 2400);
    return () => window.clearTimeout(timer);
  }, [onComplete]);

  return (
    <main style={styles.screen}>
      <div style={styles.glow} />

      <div style={styles.content}>
        <div style={styles.logo}>
          <svg
            width="68"
            height="68"
            viewBox="0 0 64 64"
            fill="none"
            aria-label="SentinelAI shield logo"
          >
            <path
              d="M32 4 53 12V28C53 42 44 52 32 60 20 52 11 42 11 28V12L32 4Z"
              stroke="#53F5E0"
              strokeWidth="2.5"
            />
            <path
              d="M22 32 29 39 43 24"
              stroke="#53F5E0"
              strokeWidth="3.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </div>

        <h1 style={styles.title}>
          SENTINEL<span style={{ color: "#53F5E0" }}>AI</span>
        </h1>

        <p style={styles.subtitle}>
          INTELLIGENT THREAT DETECTION
        </p>

        <div style={styles.loader}>
          <div style={styles.loaderBar} />
        </div>

        <p style={styles.status}>INITIALIZING SECURE ENVIRONMENT</p>
      </div>

      <p style={styles.footer}>SECURITY • INTELLIGENCE • TRUST</p>
    </main>
  );
}

const styles: Record<string, React.CSSProperties> = {
  screen: {
    minHeight: "100vh",
    background: "#070B14",
    color: "#F3F7FC",
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    position: "relative",
    overflow: "hidden",
    fontFamily: "Inter, Arial, sans-serif",
  },
  glow: {
    position: "absolute",
    width: 340,
    height: 340,
    borderRadius: "50%",
    background: "rgba(40, 225, 208, 0.09)",
    filter: "blur(85px)",
  },
  content: {
    zIndex: 1,
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    animation: "sentinelAppear 800ms ease-out",
  },
  logo: {
    width: 112,
    height: 112,
    display: "grid",
    placeItems: "center",
    border: "1px solid rgba(83,245,224,0.3)",
    borderRadius: 28,
    background: "rgba(15, 29, 40, 0.9)",
    boxShadow: "0 0 55px rgba(83,245,224,0.12)",
  },
  title: {
    fontSize: "clamp(30px, 6vw, 42px)",
    letterSpacing: "5px",
    margin: "28px 0 10px",
    fontWeight: 800,
  },
  subtitle: {
    fontSize: 11,
    letterSpacing: 3,
    color: "#8795A9",
  },
  loader: {
    width: 180,
    height: 3,
    background: "#202A38",
    borderRadius: 8,
    marginTop: 38,
    overflow: "hidden",
  },
  loaderBar: {
    height: "100%",
    width: "100%",
    background: "#53F5E0",
    transformOrigin: "left",
    animation: "sentinelLoad 2.2s ease-in-out forwards",
  },
  status: {
    marginTop: 16,
    color: "#718197",
    fontSize: 9,
    letterSpacing: 2,
  },
  footer: {
    position: "absolute",
    bottom: 24,
    color: "#586579",
    fontSize: 9,
    letterSpacing: 2,
  },
};
