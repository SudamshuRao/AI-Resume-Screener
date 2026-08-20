import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

const LOG = "[AuthPage]";
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const RESEND_COOLDOWN = 60; // seconds

const FEATURES = [
  { icon: "📊", title: "Gap Analysis",     desc: "See exactly where your skills stand against the job." },
  { icon: "✏️",  title: "Tailored Bullets", desc: "AI rewrites your resume bullets to match the JD."    },
  { icon: "✉️",  title: "Cover Letter",     desc: "Personalized cover letter generated in seconds."     },
  { icon: "🎤", title: "Interview Prep",   desc: "Likely questions with model answers, tailored to the JD." },
];

export default function AuthPage() {
  const { requestOtp, verifyOtp } = useAuth();
  const navigate = useNavigate();

  // "email" step or "otp" step
  const [step, setStep]       = useState("email");
  const [email, setEmail]     = useState("");
  const [emailErr, setEmailErr] = useState("");

  // OTP digits — 6 separate inputs
  const [digits, setDigits]   = useState(["", "", "", "", "", ""]);
  const inputRefs             = useRef([]);

  const [error, setError]     = useState("");
  const [loading, setLoading] = useState(false);
  const [cooldown, setCooldown] = useState(0);
  const [displayOtp, setDisplayOtp] = useState("");

  // Countdown timer for resend
  useEffect(() => {
    if (cooldown <= 0) return;
    const id = setTimeout(() => setCooldown((c) => c - 1), 1000);
    return () => clearTimeout(id);
  }, [cooldown]);

  // ── Step 1: request OTP ────────────────────────────────────────────────
  const handleSendOtp = async (e) => {
    e.preventDefault();
    setError("");
    const trimmed = email.trim();
    if (!EMAIL_RE.test(trimmed)) {
      setEmailErr("Enter a valid email address.");
      return;
    }
    setEmailErr("");
    setLoading(true);
    try {
      const otp = await requestOtp(trimmed);
      console.log(`${LOG} OTP requested`);
      if (otp) setDisplayOtp(otp);
      setStep("otp");
      setCooldown(RESEND_COOLDOWN);
      setTimeout(() => inputRefs.current[0]?.focus(), 50);
    } catch (err) {
      const msg = err.response?.data?.detail || "Failed to send OTP. Please try again.";
      console.error(`${LOG} OTP request failed:`, msg);
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  // ── Step 2: verify OTP ─────────────────────────────────────────────────
  const handleVerify = async (e, otpOverride) => {
    e?.preventDefault();
    setError("");
    const otp = otpOverride ?? digits.join("");
    if (otp.length < 6) {
      setError("Please enter the full 6-digit code.");
      return;
    }
    setLoading(true);
    try {
      await verifyOtp(email.trim(), otp);
      console.log(`${LOG} Signed in — navigating to /tracker`);
      navigate("/tracker");
    } catch (err) {
      const msg = err.response?.data?.detail || "Invalid or expired code. Please try again.";
      console.error(`${LOG} OTP verify failed:`, msg);
      setError(msg);
      setDigits(["", "", "", "", "", ""]);
      setTimeout(() => inputRefs.current[0]?.focus(), 50);
    } finally {
      setLoading(false);
    }
  };

  // ── Digit input handling ───────────────────────────────────────────────
  const onDigitChange = (idx, val) => {
    // accept only digits
    const ch = val.replace(/\D/g, "").slice(-1);
    const next = [...digits];
    next[idx] = ch;
    setDigits(next);
    setError("");
    if (ch && idx < 5) inputRefs.current[idx + 1]?.focus();
    // auto-submit when last digit filled — pass otp directly to avoid stale state
    if (ch && idx === 5 && next.every(d => d)) {
      setTimeout(() => handleVerify(null, next.join("")), 0);
    }
  };

  const onDigitKeyDown = (idx, e) => {
    if (e.key === "Backspace" && !digits[idx] && idx > 0) {
      inputRefs.current[idx - 1]?.focus();
    }
  };

  const onDigitPaste = (e) => {
    const pasted = e.clipboardData.getData("text").replace(/\D/g, "").slice(0, 6);
    if (!pasted) return;
    e.preventDefault();
    const next = [...digits];
    pasted.split("").forEach((ch, i) => { next[i] = ch; });
    setDigits(next);
    const focusIdx = Math.min(pasted.length, 5);
    inputRefs.current[focusIdx]?.focus();
    if (pasted.length === 6) setTimeout(() => handleVerify(null, pasted), 0);
  };

  const handleResend = async () => {
    if (cooldown > 0) return;
    setError("");
    setDigits(["", "", "", "", "", ""]);
    setLoading(true);
    try {
      const otp = await requestOtp(email.trim());
      if (otp) setDisplayOtp(otp);
      setCooldown(RESEND_COOLDOWN);
      setTimeout(() => inputRefs.current[0]?.focus(), 50);
    } catch (err) {
      setError("Failed to resend. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  // ── Render ─────────────────────────────────────────────────────────────
  return (
    <div className="auth-layout">
      {/* Left brand panel */}
      <div className="auth-brand">
        <div className="auth-brand-inner">
          <div className="auth-logo">HireIQ</div>
          <p className="auth-tagline">Your AI-powered career intelligence system.</p>
          <ul className="auth-features">
            {FEATURES.map((f) => (
              <li key={f.title}>
                <span className="feat-icon">{f.icon}</span>
                <div>
                  <strong>{f.title}</strong>
                  <p>{f.desc}</p>
                </div>
              </li>
            ))}
          </ul>
        </div>
      </div>

      {/* Right form panel */}
      <div className="auth-form-panel">
        <div className="auth-card">

          {step === "email" ? (
            <>
              <h2>Sign in to HireIQ</h2>
              <p className="auth-sub">Enter your email and we'll send you a sign-in code.</p>

              <form onSubmit={handleSendOtp} className="auth-form" noValidate>
                <div className="auth-field">
                  <label>Email</label>
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => { setEmail(e.target.value); setEmailErr(""); }}
                    placeholder="you@example.com"
                    autoComplete="email"
                    autoFocus
                    className={emailErr ? "input--invalid" : ""}
                  />
                  {emailErr && <span className="field-error">{emailErr}</span>}
                </div>

                {error && <p className="auth-error">{error}</p>}

                <button type="submit" className="auth-submit" disabled={loading}>
                  {loading ? "Sending…" : "Send sign-in code"}
                </button>
              </form>
            </>
          ) : (
            <>
              <h2>Check your email</h2>
              <p className="auth-sub">
                We sent a 6-digit code to <strong>{email}</strong>. Enter it below to sign in.
                <br />
                <button
                  className="auth-switch-btn"
                  style={{ marginTop: 4 }}
                  onClick={() => { setStep("email"); setError(""); setDigits(["","","","","",""]); }}
                >
                  Change email
                </button>
              </p>

              {displayOtp && (
                <div style={{
                  background: "rgba(99,102,241,0.12)",
                  border: "1px solid rgba(99,102,241,0.4)",
                  borderRadius: 10,
                  padding: "14px 20px",
                  marginBottom: 20,
                  textAlign: "center",
                }}>
                  <div style={{ fontSize: 12, color: "var(--muted)", marginBottom: 6 }}>Your sign-in code</div>
                  <div style={{ fontSize: 36, fontWeight: 700, letterSpacing: 10, color: "var(--text)" }}>
                    {displayOtp}
                  </div>
                </div>
              )}

              <form onSubmit={handleVerify} className="auth-form" noValidate>
                <div className="otp-inputs">
                  {digits.map((d, i) => (
                    <input
                      key={i}
                      ref={(el) => (inputRefs.current[i] = el)}
                      type="text"
                      inputMode="numeric"
                      maxLength={1}
                      value={d}
                      onChange={(e) => onDigitChange(i, e.target.value)}
                      onKeyDown={(e) => onDigitKeyDown(i, e)}
                      onPaste={onDigitPaste}
                      className={`otp-digit${error ? " input--invalid" : ""}`}
                    />
                  ))}
                </div>

                {error && <p className="auth-error">{error}</p>}

                <button type="submit" className="auth-submit" disabled={loading}>
                  {loading ? "Verifying…" : "Verify & Sign In"}
                </button>
              </form>

              <p className="auth-switch" style={{ marginTop: 16 }}>
                Didn't receive it?{" "}
                {cooldown > 0 ? (
                  <span style={{ color: "var(--muted)" }}>Resend in {cooldown}s</span>
                ) : (
                  <button className="auth-switch-btn" onClick={handleResend} disabled={loading}>
                    Resend code
                  </button>
                )}
              </p>
            </>
          )}

        </div>
      </div>
    </div>
  );
}