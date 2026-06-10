import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { pollWebLogin, getMe } from "../api/client";
import useStore from "../store/useStore";
import { useT } from "../i18n";

const IS_DEV = import.meta.env.DEV || import.meta.env.VITE_DEV_BYPASS_TELEGRAM === "true";
const BOT_USERNAME = import.meta.env.VITE_TELEGRAM_BOT_USERNAME || "QulayNavbat_bot";

const POLL_INTERVAL_MS = 2000;
const POLL_TIMEOUT_MS = 180000; // 3 minutes

// High-entropy, URL-safe nonce (hex). Used in the bot deep-link + poll handshake.
function makeNonce() {
  const a = new Uint8Array(16);
  (window.crypto || window.msCrypto).getRandomValues(a);
  return Array.from(a, (b) => b.toString(16).padStart(2, "0")).join("");
}

function BrandMark() {
  return (
    <div
      aria-hidden
      style={{
        width: 64, height: 64, borderRadius: 18,
        background: "linear-gradient(160deg, var(--brand-500), var(--brand-700))",
        display: "flex", alignItems: "center", justifyContent: "center",
        color: "#fff", fontSize: 34, fontWeight: 800, letterSpacing: "-0.04em",
        boxShadow: "var(--shadow-md)",
      }}
    >
      R
    </div>
  );
}

function ValueBullet({ icon, text }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "var(--space-3)" }}>
      <span
        aria-hidden
        style={{
          width: 32, height: 32, borderRadius: "var(--radius-sm)",
          background: "var(--brand-50)", color: "var(--brand-700)",
          display: "inline-flex", alignItems: "center", justifyContent: "center",
          fontSize: 16, flexShrink: 0,
        }}
      >
        {icon}
      </span>
      <span style={{ fontSize: "var(--text-sm)", color: "var(--gray-700)", fontWeight: 600 }}>
        {text}
      </span>
    </div>
  );
}

export default function Login() {
  const [token, setToken] = useState("");
  const [error, setError] = useState("");
  const [waiting, setWaiting] = useState(false);
  const { setAuth, lang } = useStore();
  const t = useT(lang);
  const navigate = useNavigate();

  // One nonce per page load; the deep-link and the poll share it.
  const [nonce] = useState(makeNonce);
  const tgUrl = `https://t.me/${BOT_USERNAME}?start=login_${nonce}`;
  const pollRef = useRef(null);
  const startedRef = useRef(0);

  const stopPolling = () => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  };

  // Clean up the interval if the user navigates away mid-login.
  useEffect(() => stopPolling, []);

  const beginLogin = () => {
    setError("");
    setWaiting(true);
    startedRef.current = Date.now();
    if (pollRef.current) return; // already polling — reuse it
    pollRef.current = setInterval(async () => {
      if (Date.now() - startedRef.current > POLL_TIMEOUT_MS) {
        stopPolling();
        setWaiting(false);
        setError(t("login_timeout"));
        return;
      }
      try {
        const res = await pollWebLogin(nonce);
        if (res.status === "ok") {
          stopPolling();
          setAuth(
            { id: res.user_id, name: res.name, role: res.role, language: res.language },
            res.access_token,
          );
          navigate("/");
        }
      } catch {
        /* keep polling — transient network errors are expected */
      }
    }, POLL_INTERVAL_MS);
  };

  // Dev-mode fallback: paste a JWT directly. Hidden in production builds.
  const handleDevSubmit = async (e) => {
    e.preventDefault();
    setError("");
    try {
      localStorage.setItem("access_token", token);
      const me = await getMe();
      setAuth(me, token);
      navigate("/");
    } catch {
      localStorage.removeItem("access_token");
      setError(t("invalid_token"));
    }
  };

  return (
    <div
      style={{
        display: "flex", alignItems: "center", justifyContent: "center",
        minHeight: "100vh", padding: "var(--space-6)",
      }}
    >
      <div className="card animate-in" style={{ width: "100%", maxWidth: 440, padding: "var(--space-8) var(--space-6)" }}>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", textAlign: "center", marginBottom: "var(--space-6)" }}>
          <BrandMark />
          <h1 style={{ fontSize: "var(--text-2xl)", fontWeight: 800, letterSpacing: "-0.025em", marginTop: "var(--space-4)" }}>
            Rezerv
          </h1>
          <p style={{ color: "var(--gray-500)", marginTop: "var(--space-2)", fontSize: "var(--text-sm)", lineHeight: 1.55, maxWidth: 320 }}>
            {t("login_telegram_instruction")}
          </p>
        </div>

        <div className="stack" style={{ gap: "var(--space-3)", marginBottom: "var(--space-6)" }}>
          <ValueBullet icon="📅" text={t("landing_bullet_1")} />
          <ValueBullet icon="👥" text={t("landing_bullet_2")} />
          <ValueBullet icon="📊" text={t("landing_bullet_3")} />
        </div>

        {/* Bot deep-link login: opens Telegram, then we poll until confirmed. */}
        <a
          href={tgUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="btn btn-primary btn-full"
          onClick={beginLogin}
          style={{ gap: "var(--space-2)" }}
        >
          <span aria-hidden>✈️</span> {t("login_with_telegram")}
        </a>

        {waiting ? (
          <div style={{ marginTop: "var(--space-3)", textAlign: "center" }}>
            <p className="muted" style={{ fontSize: "var(--text-sm)" }}>{t("login_waiting")}</p>
            <a
              href={tgUrl}
              target="_blank"
              rel="noopener noreferrer"
              style={{ fontSize: "var(--text-xs)", fontWeight: 600 }}
            >
              {t("login_open_telegram")}
            </a>
          </div>
        ) : (
          <p style={{ color: "var(--gray-500)", fontSize: "var(--text-xs)", textAlign: "center", lineHeight: 1.5, marginTop: "var(--space-3)" }}>
            {t("login_with_telegram_hint")}
          </p>
        )}

        {error && (
          <p style={{ color: "var(--danger)", fontSize: "var(--text-sm)", textAlign: "center", marginTop: "var(--space-3)" }}>
            {error}
          </p>
        )}

        {IS_DEV && (
          <details style={{ marginTop: "var(--space-6)", paddingTop: "var(--space-4)", borderTop: "1px solid var(--line)" }}>
            <summary
              style={{
                cursor: "pointer", fontSize: "var(--text-xs)", fontWeight: 600,
                color: "var(--gray-500)", textAlign: "center", listStyle: "none",
              }}
            >
              {t("dev_mode_notice")}
            </summary>
            <form onSubmit={handleDevSubmit} style={{ marginTop: "var(--space-3)" }}>
              <div className="form-group">
                <label htmlFor="login-token">{t("access_token")}</label>
                <input
                  id="login-token"
                  type="text"
                  placeholder={t("paste_jwt_placeholder")}
                  value={token}
                  onChange={(e) => setToken(e.target.value)}
                  autoComplete="off"
                />
              </div>
              <button type="submit" className="btn btn-secondary btn-full">{t("sign_in")}</button>
            </form>
          </details>
        )}
      </div>
    </div>
  );
}
