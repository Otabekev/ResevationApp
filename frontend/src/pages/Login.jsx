import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { authTelegramWidget, getMe } from "../api/client";
import useStore from "../store/useStore";
import { useT } from "../i18n";

const IS_DEV = import.meta.env.DEV || import.meta.env.VITE_DEV_BYPASS_TELEGRAM === "true";
const BOT_USERNAME = import.meta.env.VITE_TELEGRAM_BOT_USERNAME || "QulayNavbat_bot";

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
  const [widgetLoading, setWidgetLoading] = useState(false);
  const { setAuth, lang } = useStore();
  const t = useT(lang);
  const navigate = useNavigate();
  const widgetContainerRef = useRef(null);

  // ── Telegram Login Widget integration ─────────────────────────────────────
  useEffect(() => {
    // Callback Telegram invokes via data-onauth attribute.
    window.onTelegramAuth = async (tgUser) => {
      setError("");
      setWidgetLoading(true);
      try {
        const data = await authTelegramWidget(tgUser);
        setAuth(
          { id: data.user_id, name: data.name, role: data.role, language: data.language },
          data.access_token,
        );
        navigate("/");
      } catch {
        setError(t("invalid_token"));
        setWidgetLoading(false);
      }
    };

    // Inject the widget script (must be appended via DOM API — Telegram parses
    // its data-* attributes at script-load time, not lazily).
    const script = document.createElement("script");
    script.src = "https://telegram.org/js/telegram-widget.js?22";
    script.async = true;
    script.setAttribute("data-telegram-login", BOT_USERNAME);
    script.setAttribute("data-size", "large");
    script.setAttribute("data-radius", "10");
    script.setAttribute("data-onauth", "onTelegramAuth(user)");
    script.setAttribute("data-request-access", "write");
    const container = widgetContainerRef.current;
    if (container) container.appendChild(script);

    return () => {
      if (container && script.parentNode === container) container.removeChild(script);
      delete window.onTelegramAuth;
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

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

        {/* Telegram Login Widget mounts here */}
        <div
          ref={widgetContainerRef}
          style={{ display: "flex", justifyContent: "center", minHeight: 48, marginBottom: "var(--space-3)" }}
        />
        <p style={{ color: "var(--gray-500)", fontSize: "var(--text-xs)", textAlign: "center", lineHeight: 1.5 }}>
          {t("login_with_telegram_hint")}
        </p>

        {widgetLoading && (
          <p className="muted" style={{ textAlign: "center", fontSize: "var(--text-sm)", marginTop: "var(--space-3)" }}>
            {t("loading")}
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
