import { useEffect, useState, type FormEvent } from "react";

/* ---------- Logo ---------- */
function LogoMark({ size = 48 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" fill="none" role="img" aria-label="SentinelAI logo">
      <path d="M32 3 57 11V30C57 45 46 55 32 61 18 55 7 45 7 30V11L32 3Z" fill="#0B1B3A" stroke="#2E9BFF" strokeWidth="4" strokeLinejoin="round" />
      <path d="M13 32C20 21 44 21 51 32 44 43 20 43 13 32Z" fill="#F2F7FF" />
      <circle cx="32" cy="32" r="8" fill="#2E8BFF" />
      <circle cx="29.5" cy="29.5" r="2.6" fill="#CFE6FF" />
    </svg>
  );
}

/* ---------- Splash (logo screen) ---------- */
export function SplashScreen({ onComplete }: { onComplete: () => void }) {
  useEffect(() => {
    const timer = window.setTimeout(onComplete, 2400);
    return () => window.clearTimeout(timer);
  }, [onComplete]);

  return (
    <main style={styles.screen}>
      <div style={styles.glow} />
      <div style={styles.content}>
        <div style={styles.logo}>
          <LogoMark size={76} />
        </div>
        <h1 style={styles.title}>
          SENTINEL<span style={{ color: "#53F5E0" }}>AI</span>
        </h1>
        <p style={styles.subtitle}>INTELLIGENT THREAT DETECTION</p>
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
  screen: { minHeight: "100vh", background: "#070B14", color: "#F3F7FC", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", position: "relative", overflow: "hidden", fontFamily: "Inter, Arial, sans-serif" },
  glow: { position: "absolute", width: 340, height: 340, borderRadius: "50%", background: "rgba(40, 225, 208, 0.09)", filter: "blur(85px)" },
  content: { zIndex: 1, display: "flex", flexDirection: "column", alignItems: "center", animation: "sentinelAppear 800ms ease-out" },
  logo: { width: 112, height: 112, display: "grid", placeItems: "center", border: "1px solid rgba(83,245,224,0.3)", borderRadius: 28, background: "rgba(15, 29, 40, 0.9)", boxShadow: "0 0 55px rgba(83,245,224,0.12)" },
  title: { fontSize: "clamp(30px, 6vw, 42px)", letterSpacing: "5px", margin: "28px 0 10px", fontWeight: 800 },
  subtitle: { fontSize: 11, letterSpacing: 3, color: "#8795A9" },
  loader: { width: 180, height: 3, background: "#202A38", borderRadius: 8, marginTop: 38, overflow: "hidden" },
  loaderBar: { height: "100%", width: "100%", background: "#53F5E0", transformOrigin: "left", animation: "sentinelLoad 2.2s ease-in-out forwards" },
  status: { marginTop: 16, color: "#718197", fontSize: 9, letterSpacing: 2 },
  footer: { position: "absolute", bottom: 24, color: "#586579", fontSize: 9, letterSpacing: 2 },
};

/* ---------- Login ---------- */
const API_BASE = (import.meta.env.VITE_API_URL as string | undefined) || "http://localhost:8000";
const OFFLINE_DEMO = import.meta.env.VITE_USE_MOCK === "true";

export function Login({ onLogin }: { onLogin: () => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    if (!username.trim() || !password) {
      setError("Enter your username and password to continue.");
      return;
    }
    if (OFFLINE_DEMO) {
      onLogin();
      return;
    }
    setLoading(true);
    try {
      const response = await fetch(`${API_BASE}/api/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: username.trim(), password }),
      });
      if (response.status === 401) {
        setError("Invalid username or password.");
        return;
      }
      if (!response.ok) {
        setError(`Sign-in failed (error ${response.status}). Please try again.`);
        return;
      }
      onLogin();
    } catch {
      setError("Cannot reach the server. Check your connection and try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="sl-page">
      <style>{loginCss}</style>
      <div className="sl-card">
        <section className="sl-left">
          <div className="sl-brand">
            <LogoMark size={40} />
            <span>SENTINEL<b>AI</b></span>
          </div>
          <h1 className="sl-title">Sign in</h1>
          <p className="sl-sub">Access is for authorized SentinelAI operators only.</p>

          <form onSubmit={handleSubmit} noValidate>
            <label className="sl-label" htmlFor="sl-user">Username</label>
            <input id="sl-user" className="sl-input" type="text" autoComplete="username" placeholder="Enter your username" value={username} onChange={(e) => setUsername(e.target.value)} />

            <label className="sl-label" htmlFor="sl-pass">Password</label>
            <div className="sl-pass">
              <input id="sl-pass" className="sl-input sl-input-pass" type={showPassword ? "text" : "password"} autoComplete="current-password" placeholder="Enter your password" value={password} onChange={(e) => setPassword(e.target.value)} />
              <button type="button" className="sl-eye" onClick={() => setShowPassword(!showPassword)} aria-label={showPassword ? "Hide password" : "Show password"}>
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  {showPassword ? (
                    <>
                      <path d="M3 3l18 18" />
                      <path d="M10.6 6.1A10.9 10.9 0 0 1 12 6c6 0 9.5 6 9.5 6a17 17 0 0 1-3.2 3.9" />
                      <path d="M6.6 6.7C4 8.4 2.5 12 2.5 12S6 18 12 18c1.6 0 3-.4 4.2-1" />
                    </>
                  ) : (
                    <>
                      <path d="M2.5 12S6 6 12 6s9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z" />
                      <circle cx="12" cy="12" r="3" />
                    </>
                  )}
                </svg>
              </button>
            </div>

            <p className="sl-error" role="alert" aria-live="polite">{error}</p>
            <button type="submit" className="sl-submit" disabled={loading}>
              {loading ? "Signing in..." : "Sign in"}
            </button>
          </form>

          <div className="sl-divider"><span /><small>PROTECTED WORKSPACE</small><span /></div>
          <p className="sl-note">No facial recognition. Authorized, prerecorded feeds only. A human reviews every alert.</p>
        </section>

        <section className="sl-right" aria-hidden="true">
          <svg viewBox="0 0 600 720" preserveAspectRatio="xMidYMid slice" className="sl-art">
            <defs>
              <radialGradient id="sl-bg" cx="50%" cy="46%" r="70%">
                <stop offset="0" stopColor="#0F3E86" />
                <stop offset="0.55" stopColor="#081B3F" />
                <stop offset="1" stopColor="#040A18" />
              </radialGradient>
              <radialGradient id="sl-core" cx="50%" cy="50%" r="50%">
                <stop offset="0" stopColor="#2EE6D6" stopOpacity="0.55" />
                <stop offset="1" stopColor="#2EE6D6" stopOpacity="0" />
              </radialGradient>
              <linearGradient id="sl-sweep" x1="0" y1="0" x2="1" y2="0">
                <stop offset="0" stopColor="#35A7FF" stopOpacity="0" />
                <stop offset="1" stopColor="#35A7FF" stopOpacity="0.38" />
              </linearGradient>
              <filter id="sl-glow" x="-50%" y="-50%" width="200%" height="200%">
                <feGaussianBlur stdDeviation="9" />
              </filter>
            </defs>
            <rect width="600" height="720" fill="url(#sl-bg)" />
            <g fill="none" stroke="#4FA8FF" strokeLinecap="round" strokeDasharray="1 7" strokeWidth="2.4" opacity="0.5">
              {[80, 125, 170, 215, 260, 305, 350, 395].map((r) => (
                <circle key={r} cx="300" cy="350" r={r} />
              ))}
            </g>
            <g stroke="#4FA8FF" strokeWidth="1" opacity="0.18">
              {Array.from({ length: 12 }).map((_, i) => {
                const a = (i * Math.PI) / 6;
                return <line key={i} x1={300 + Math.cos(a) * 90} y1={350 + Math.sin(a) * 90} x2={300 + Math.cos(a) * 420} y2={350 + Math.sin(a) * 420} />;
              })}
            </g>
            <g className="sl-sweep">
              <path d="M300 350 L300 -70 A420 420 0 0 1 598 53 Z" fill="url(#sl-sweep)" />
            </g>
            <circle cx="300" cy="350" r="150" fill="url(#sl-core)" />
            <g filter="url(#sl-glow)" opacity="0.7">
              <circle cx="300" cy="350" r="70" fill="#2E9BFF" />
            </g>
            <svg x="190" y="240" width="220" height="220" viewBox="0 0 64 64">
              <path d="M32 3 57 11V30C57 45 46 55 32 61 18 55 7 45 7 30V11L32 3Z" fill="#0B1B3A" stroke="#35B6FF" strokeWidth="2.6" strokeLinejoin="round" />
              <path d="M13 32C20 21 44 21 51 32 44 43 20 43 13 32Z" fill="#F2F7FF" />
              <circle cx="32" cy="32" r="8" fill="#2E8BFF" />
              <circle cx="29.5" cy="29.5" r="2.6" fill="#CFE6FF" />
            </svg>
          </svg>
          <div className="sl-tag">
            <p>INTELLIGENCE. BEFORE THE THREAT.</p>
            <h2>Stay ahead of every <span>threat.</span></h2>
            <small>Real-time detection, evidence and response in one control room.</small>
          </div>
        </section>
      </div>
    </main>
  );
}

const loginCss = `
.sl-page{min-height:100vh;display:grid;place-items:center;padding:clamp(12px,3vw,40px);box-sizing:border-box;background:#D9F0FF;font-family:Inter,Arial,sans-serif;color:#F3F7FC}
.sl-card{width:min(1120px,100%);min-height:min(660px,92vh);display:grid;grid-template-columns:1fr 1fr;border-radius:28px;overflow:hidden;background:#060B1A;box-shadow:0 30px 80px rgba(8,36,80,.28);border:4px solid #fff}
.sl-left{position:relative;padding:clamp(28px,5vw,56px);display:flex;flex-direction:column;justify-content:center;box-sizing:border-box;background:radial-gradient(420px 360px at 22% 18%,rgba(24,226,208,.55),rgba(24,226,208,0) 70%),radial-gradient(520px 420px at 70% 100%,rgba(21,72,255,.55),rgba(21,72,255,0) 70%),#070C1E}
.sl-brand{display:flex;align-items:center;gap:12px;font-weight:800;letter-spacing:2px;font-size:15px;margin-bottom:clamp(22px,5vh,44px)}
.sl-brand b{color:#53F5E0}
.sl-title{font-size:clamp(34px,4vw,46px);margin:0 0 10px;letter-spacing:-1px}
.sl-sub{margin:0 0 28px;color:#B8C6DA;font-size:14px}
.sl-label{display:block;font-size:14px;font-weight:600;margin:0 0 8px 4px;color:#EAF1FB}
.sl-input{width:100%;box-sizing:border-box;border:2px solid transparent;border-radius:12px;background:#F4F8FF;color:#0A1428;padding:14px;font-size:14px;margin-bottom:18px;outline:none}
.sl-input::placeholder{color:#6A7890}
.sl-input:focus{border-color:#53F5E0;box-shadow:0 0 0 3px rgba(83,245,224,.25)}
.sl-pass{position:relative}
.sl-input-pass{padding-right:52px}
.sl-eye{position:absolute;right:6px;top:4px;width:42px;height:42px;border:0;background:transparent;color:#4B5B75;cursor:pointer;border-radius:10px}
.sl-eye:hover{color:#0A1428}
.sl-error{min-height:20px;margin:0 0 10px 4px;color:#FF9A9A;font-size:13px}
.sl-submit{width:100%;border:0;border-radius:999px;padding:15px;font-size:15px;font-weight:700;color:#fff;cursor:pointer;background:linear-gradient(180deg,#2C52FF,#1237FF);box-shadow:0 10px 30px rgba(18,55,255,.4)}
.sl-submit:disabled{opacity:.7;cursor:wait}
.sl-divider{display:flex;align-items:center;gap:14px;margin:30px 0 14px;color:#8FA0B8;font-size:10px;letter-spacing:1.6px}
.sl-divider span{flex:1;height:1px;background:rgba(160,185,220,.35)}
.sl-note{margin:0;text-align:center;font-size:12px;color:#93A3BA;line-height:1.6}
.sl-right{position:relative;border-left:1px solid rgba(120,170,255,.25);overflow:hidden;min-height:340px}
.sl-art{position:absolute;inset:0;width:100%;height:100%}
.sl-sweep{transform-origin:300px 350px;animation:sl-spin 9s linear infinite}
@keyframes sl-spin{to{transform:rotate(360deg)}}
.sl-tag{position:absolute;left:0;right:0;bottom:0;padding:28px clamp(22px,3vw,40px);background:linear-gradient(180deg,rgba(4,10,24,0),rgba(4,10,24,.9))}
.sl-tag p{margin:0 0 8px;color:#53F5E0;font-size:10px;letter-spacing:2.4px;font-weight:700}
.sl-tag h2{margin:0 0 8px;font-size:clamp(22px,2.4vw,30px);letter-spacing:-.5px}
.sl-tag h2 span{color:#53F5E0}
.sl-tag small{color:#A9B9CE;font-size:12px}
@media (max-width:860px){.sl-card{grid-template-columns:1fr;min-height:0}.sl-right{display:none}}
@media (prefers-reduced-motion:reduce){.sl-sweep{animation:none}}
`;
