
import { useState, type FormEvent } from "react";

type LoginProps = {
  onLogin: () => void;
};

export default function Login({ onLogin }: LoginProps) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");

    if (!email.trim() || !password) {
      setError("Enter your email and password to continue.");
      return;
    }

    // UI prototype only. Connect backend authentication here.
    setError("Authentication is not connected yet.");
  }

  return (
    <main style={s.page}>
      <div style={s.glow} />

      <nav style={s.nav}>
        <div style={s.brand}>
          <div style={s.miniLogo}>
            <svg width="25" height="25" viewBox="0 0 64 64" fill="none">
              <path
                d="M32 4 53 12V28C53 42 44 52 32 60 20 52 11 42 11 28V12L32 4Z"
                stroke="#53F5E0"
                strokeWidth="4"
              />
              <path
                d="M22 32 29 39 43 24"
                stroke="#53F5E0"
                strokeWidth="5"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </div>
          <span>SENTINEL<span style={{ color: "#53F5E0" }}>AI</span></span>
        </div>
        <div style={s.secureLabel}>
          <span style={s.dot} /> SECURE ACCESS
        </div>
      </nav>

      <section style={s.layout}>
        <div style={s.intro}>
          <p style={s.eyebrow}>INTELLIGENCE. BEFORE THE THREAT.</p>
          <h1 style={s.headline}>
            Stay ahead
            <br />
            of every <span style={s.accent}>threat.</span>
          </h1>
          <p style={s.description}>
            Your unified command center for intelligent threat
            detection, incident monitoring, and security response.
          </p>

          <div style={s.features}>
            <div style={s.feature}>
              <span style={s.featureIcon}>◈</span>
              <div>
                <strong>Real-time monitoring</strong>
                <p>Stay informed as incidents unfold.</p>
              </div>
            </div>
            <div style={s.feature}>
              <span style={s.featureIcon}>⌁</span>
              <div>
                <strong>AI-powered intelligence</strong>
                <p>Turn security signals into insights.</p>
              </div>
            </div>
          </div>
        </div>

        <form style={s.card} onSubmit={handleSubmit}>
          <div style={s.cardIcon}>↗</div>
          <h2 style={s.cardTitle}>Welcome back</h2>
          <p style={s.cardSubtitle}>
            Sign in to your SentinelAI workspace.
          </p>

          <label style={s.label} htmlFor="email">Email address</label>
          <input
            id="email"
            type="email"
            autoComplete="email"
            placeholder="you@company.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            style={s.input}
            required
          />

          <div style={s.passwordHeader}>
            <label style={s.label} htmlFor="password">Password</label>
          </div>
          <div style={s.passwordBox}>
            <input
              id="password"
              type={showPassword ? "text" : "password"}
              autoComplete="current-password"
              placeholder="Enter your password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              style={s.passwordInput}
              required
            />
            <button
              type="button"
              onClick={() => setShowPassword(!showPassword)}
              style={s.showButton}
            >
              {showPassword ? "Hide" : "Show"}
            </button>
          </div>

          {error && <p role="alert" style={s.error}>{error}</p>}

          <button type="submit" style={s.submit}>
            Sign in <span>→</span>
          </button>

          <div style={s.divider}>
            <span />
            <small>PROTECTED WORKSPACE</small>
            <span />
          </div>

          <p style={s.privacy}>
            Access is intended for authorized SentinelAI users.
          </p>
        </form>
      </section>

      <footer style={s.footer}>
        <span>© SentinelAI</span>
        <span>Built for a safer digital world.</span>
      </footer>
    </main>
  );
}

const s: Record<string, React.CSSProperties> = {
  page: {
    minHeight: "100vh",
    background: "#070B14",
    color: "#F3F7FC",
    fontFamily: "Inter, Arial, sans-serif",
    position: "relative",
    overflow: "hidden",
    display: "flex",
    flexDirection: "column",
  },
  glow: {
    position: "absolute",
    width: 450,
    height: 450,
    top: "15%",
    left: "12%",
    borderRadius: "50%",
    background: "rgba(36, 213, 198, 0.055)",
    filter: "blur(100px)",
    pointerEvents: "none",
  },
  nav: {
    position: "relative",
    zIndex: 1,
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    padding: "24px clamp(20px, 6vw, 84px)",
    borderBottom: "1px solid #1A2230",
  },
  brand: {
    display: "flex",
    alignItems: "center",
    gap: 12,
    fontWeight: 800,
    letterSpacing: 2,
    fontSize: 18,
  },
  miniLogo: {
    width: 42,
    height: 42,
    display: "grid",
    placeItems: "center",
    borderRadius: 12,
    background: "#101C27",
    border: "1px solid #24413F",
  },
  secureLabel: {
    display: "flex",
    alignItems: "center",
    gap: 9,
    color: "#9AA8B9",
    fontSize: 10,
    letterSpacing: 1.5,
  },
  dot: {
    width: 7,
    height: 7,
    background: "#53F5E0",
    borderRadius: "50%",
    boxShadow: "0 0 10px #53F5E0",
  },
  layout: {
    position: "relative",
    zIndex: 1,
    flex: 1,
    width: "min(1120px, 100%)",
    boxSizing: "border-box",
    margin: "0 auto",
    padding: "64px 28px",
    display: "grid",
    gridTemplateColumns: "1fr minmax(300px, 410px)",
    alignItems: "center",
    gap: 70,
  },
  intro: { maxWidth: 520 },
  eyebrow: {
    color: "#53F5E0",
    fontSize: 10,
    letterSpacing: 2.5,
    fontWeight: 700,
  },
  headline: {
    fontSize: "clamp(42px, 5.5vw, 66px)",
    lineHeight: 1.08,
    letterSpacing: -2,
    margin: "22px 0",
  },
  accent: { color: "#53F5E0" },
  description: {
    color: "#96A4B8",
    lineHeight: 1.8,
    fontSize: 15,
    maxWidth: 440,
  },
  features: {
    display: "grid",
    gap: 24,
    marginTop: 42,
  },
  feature: { display: "flex", gap: 16, alignItems: "center" },
  featureIcon: {
    width: 42,
    height: 42,
    display: "grid",
    placeItems: "center",
    border: "1px solid #253C42",
    background: "#101B26",
    color: "#53F5E0",
    borderRadius: 12,
    fontSize: 22,
  },
  featureText: {},
  card: {
    width: "100%",
    boxSizing: "border-box",
    background: "rgba(15, 21, 33, 0.96)",
    border: "1px solid #273141",
    borderRadius: 20,
    padding: "34px clamp(22px, 3vw, 36px)",
    boxShadow: "0 25px 80px rgba(0,0,0,0.22)",
  },
  cardIcon: {
    width: 44,
    height: 44,
    borderRadius: 13,
    display: "grid",
    placeItems: "center",
    color: "#53F5E0",
    background: "#102A2D",
    fontSize: 25,
  },
  cardTitle: { fontSize: 27, margin: "24px 0 8px" },
  cardSubtitle: { color: "#93A0B2", fontSize: 13, marginBottom: 30 },
  label: {
    display: "block",
    color: "#DCE4EF",
    fontSize: 12,
    fontWeight: 600,
    marginBottom: 10,
  },
  input: {
    width: "100%",
    boxSizing: "border-box",
    background: "#0A101B",
    color: "#F3F7FC",
    border: "1px solid #303A4B",
    borderRadius: 10,
    padding: "14px 13px",
    fontSize: 13,
    outlineColor: "#53F5E0",
    marginBottom: 22,
  },
  passwordHeader: { display: "flex", justifyContent: "space-between" },
  passwordBox: {
    display: "flex",
    alignItems: "center",
    background: "#0A101B",
    border: "1px solid #303A4B",
    borderRadius: 10,
    marginBottom: 18,
  },
  passwordInput: {
    flex: 1,
    minWidth: 0,
    background: "transparent",
    color: "#F3F7FC",
    border: 0,
    padding: "14px 13px",
    fontSize: 13,
    outline: "none",
  },
  showButton: {
    border: 0,
    background: "transparent",
    color: "#53F5E0",
    cursor: "pointer",
    padding: "10px 13px",
    fontSize: 12,
  },
  error: { color: "#FF9A9A", fontSize: 12, lineHeight: 1.5 },
  submit: {
    width: "100%",
    display: "flex",
    justifyContent: "center",
    gap: 12,
    alignItems: "center",
    background: "#53F5E0",
    color: "#071414",
    border: 0,
    borderRadius: 10,
    padding: 15,
    fontSize: 14,
    fontWeight: 800,
    cursor: "pointer",
    marginTop: 4,
  },
  divider: {
    display: "flex",
    alignItems: "center",
    gap: 12,
    marginTop: 28,
    color: "#6F7D90",
    fontSize: 9,
    letterSpacing: 1.3,
  },
  privacy: {
    textAlign: "center",
    fontSize: 11,
    color: "#778599",
    lineHeight: 1.6,
    marginTop: 18,
  },
  footer: {
    position: "relative",
    display: "flex",
    justifyContent: "space-between",
    gap: 16,
    padding: "20px clamp(20px, 6vw, 84px)",
    borderTop: "1px solid #1A2230",
    color: "#778599",
    fontSize: 11,
  },
};
