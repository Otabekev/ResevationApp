import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { pollWebLogin, getMe } from "../api/client";
import useStore from "../store/useStore";
import { useT } from "../i18n";
import { IconCalendar, IconUsers, IconChart, IconCheck, IconTelegram, IconGlobe } from "../components/icons";

const IS_DEV = import.meta.env.DEV || import.meta.env.VITE_DEV_BYPASS_TELEGRAM === "true";
const BOT_USERNAME = import.meta.env.VITE_TELEGRAM_BOT_USERNAME || "QulayNavbat_bot";

const POLL_INTERVAL_MS = 2000;
const POLL_TIMEOUT_MS = 180000; // 3 minutes

const LANGS = [
  { code: "uz", label: "UZ" },
  { code: "ru", label: "RU" },
  { code: "en", label: "EN" },
];

// High-entropy, URL-safe nonce (hex). Used in the bot deep-link + poll handshake.
function makeNonce() {
  const a = new Uint8Array(16);
  (window.crypto || window.msCrypto).getRandomValues(a);
  return Array.from(a, (b) => b.toString(16).padStart(2, "0")).join("");
}

function BrandPanel({ t }) {
  return (
    <div
      style={{
        flex: "1 1 46%",
        background:
          "radial-gradient(120% 90% at 80% -10%, rgba(114,190,170,.25), transparent 50%)," +
          "radial-gradient(100% 100% at -10% 110%, rgba(201,130,26,.18), transparent 55%)," +
          "linear-gradient(165deg, #0E2F27, #0B2620 60%)",
        color: "#fff",
        padding: "min(7vw, 72px)",
        display: "flex",
        flexDirection: "column",
        justifyContent: "space-between",
        minHeight: "100dvh",
      }}
      className="login-brand"
    >
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <span
          aria-hidden
          style={{
            width: 40, height: 40, borderRadius: 12,
            background: "linear-gradient(150deg, var(--brand-400), var(--brand-600))",
            display: "inline-flex", alignItems: "center", justifyContent: "center",
            boxShadow: "0 4px 12px rgba(0,0,0,.3), inset 0 1px 0 rgba(255,255,255,.25)",
            fontWeight: 800, fontSize: 20,
          }}
        >
          Q
        </span>
        <div>
          <div style={{ fontWeight: 800, fontSize: 20, letterSpacing: "-0.02em" }}>Qulay Navbat</div>
          <div style={{ fontSize: 10.5, fontWeight: 650, letterSpacing: ".14em", textTransform: "uppercase", color: "rgba(255,255,255,.5)" }}>
            {t("brand_tagline")}
          </div>
        </div>
      </div>

      <div>
        <h1 style={{ color: "#fff", fontSize: "clamp(26px, 3.2vw, 38px)", lineHeight: 1.15, letterSpacing: "-0.025em", maxWidth: 420 }}>
          {t("login_hero_title")}
        </h1>
        <p style={{ color: "rgba(255,255,255,.65)", marginTop: 14, fontSize: 15, lineHeight: 1.6, maxWidth: 400 }}>
          {t("login_hero_sub")}
        </p>

        <div style={{ display: "flex", flexDirection: "column", gap: 14, marginTop: 34 }}>
          {[
            [<IconCalendar size={17} key="i1" />, t("landing_bullet_1")],
            [<IconUsers size={17} key="i2" />, t("landing_bullet_2")],
            [<IconChart size={17} key="i3" />, t("landing_bullet_3")],
          ].map(([ico, text], i) => (
            <div key={i} style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <span
                aria-hidden
                style={{
                  width: 32, height: 32, borderRadius: 9, flexShrink: 0,
                  background: "rgba(114,190,170,.16)", color: "var(--brand-200)",
                  display: "inline-flex", alignItems: "center", justifyContent: "center",
                  border: "1px solid rgba(114,190,170,.22)",
                }}
              >
                {ico}
              </span>
              <span style={{ fontSize: 14.5, fontWeight: 600, color: "rgba(255,255,255,.85)" }}>{text}</span>
            </div>
          ))}
        </div>
      </div>

      <div style={{ fontSize: 12.5, color: "rgba(255,255,255,.4)" }}>
        © {new Date().getFullYear()} Qulay Navbat · Namangan
      </div>
    </div>
  );
}

export default function Login() {
  const [token, setToken] = useState("");
  const [error, setError] = useState("");
  const [waiting, setWaiting] = useState(false);
  const { setAuth, lang, setLang } = useStore();
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
            res.refresh_token,
          );
          window.location.href = "/"; // full reload so App re-hydrates businesses
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
      window.location.reload();
    } catch {
      localStorage.removeItem("access_token");
      setError(t("invalid_token"));
    }
  };

  return (
    <div style={{ display: "flex", minHeight: "100dvh" }}>
      {/* Brand side (hidden on small screens via inline media trick) */}
      {window.innerWidth >= 880 && <BrandPanel t={t} />}

      {/* Form side */}
      <div
        style={{
          flex: "1 1 54%",
          display: "flex", alignItems: "center", justifyContent: "center",
          padding: "var(--space-6)", position: "relative",
        }}
      >
        {/* Language pills */}
        <div
          style={{
            position: "absolute", top: "calc(env(safe-area-inset-top) + 18px)", right: 18,
            display: "flex", gap: 4, padding: 3,
            background: "var(--gray-100)", borderRadius: "var(--radius-full)",
            border: "1px solid var(--line-soft)",
          }}
        >
          <span style={{ display: "inline-flex", alignItems: "center", paddingLeft: 8, color: "var(--gray-400)" }}>
            <IconGlobe size={14} />
          </span>
          {LANGS.map((l) => (
            <button
              key={l.code}
              type="button"
              onClick={() => setLang(l.code)}
              style={{
                padding: "5px 10px", borderRadius: 999, fontSize: 12, fontWeight: 750,
                background: lang === l.code ? "var(--surface)" : "transparent",
                color: lang === l.code ? "var(--gray-900)" : "var(--gray-500)",
                boxShadow: lang === l.code ? "var(--shadow-xs)" : "none",
              }}
            >
              {l.label}
            </button>
          ))}
        </div>

        <div className="animate-in" style={{ width: "100%", maxWidth: 400 }}>
          {/* Compact brand header for mobile (brand panel hidden) */}
          {window.innerWidth < 880 && (
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", marginBottom: "var(--space-6)" }}>
              <span
                aria-hidden
                style={{
                  width: 58, height: 58, borderRadius: 16,
                  background: "linear-gradient(150deg, var(--brand-400), var(--brand-600))",
                  display: "flex", alignItems: "center", justifyContent: "center",
                  color: "#fff", fontSize: 30, fontWeight: 800,
                  boxShadow: "var(--shadow-md)",
                }}
              >
                Q
              </span>
              <h1 style={{ fontSize: "var(--text-xl)", marginTop: 12 }}>Qulay Navbat</h1>
              <p style={{ color: "var(--gray-500)", fontSize: "var(--text-sm)", marginTop: 4, textAlign: "center" }}>
                {t("login_hero_sub")}
              </p>
            </div>
          )}

          <div className="card" style={{ padding: "var(--space-6)" }}>
            <div className="eyebrow" style={{ marginBottom: 6 }}>{t("login_for_owners")}</div>
            <h2 style={{ fontSize: "var(--text-lg)", marginBottom: 6 }}>{t("sign_in")}</h2>
            <p style={{ color: "var(--gray-500)", fontSize: "var(--text-sm)", lineHeight: 1.55, marginBottom: "var(--space-5)" }}>
              {t("login_telegram_instruction")}
            </p>

            <a
              href={tgUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="btn btn-primary btn-full"
              onClick={beginLogin}
              style={{ minHeight: 48 }}
            >
              <IconTelegram size={19} />
              {t("login_with_telegram")}
            </a>

            {waiting ? (
              <div
                style={{
                  marginTop: "var(--space-4)", padding: "var(--space-3) var(--space-4)",
                  background: "var(--brand-50)", border: "1px solid var(--brand-100)",
                  borderRadius: "var(--radius-sm)",
                  display: "flex", alignItems: "center", gap: 12,
                }}
              >
                <span
                  aria-hidden
                  style={{
                    width: 18, height: 18, borderRadius: "50%", flexShrink: 0,
                    border: "2.5px solid var(--brand-200)", borderTopColor: "var(--brand-600)",
                    animation: "spin 0.9s linear infinite",
                  }}
                />
                <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
                <div>
                  <div style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: "var(--brand-800)" }}>
                    {t("login_waiting")}
                  </div>
                  <a href={tgUrl} target="_blank" rel="noopener noreferrer" style={{ fontSize: "var(--text-xs)", fontWeight: 650 }}>
                    {t("login_open_telegram")}
                  </a>
                </div>
              </div>
            ) : (
              <p style={{ color: "var(--gray-400)", fontSize: "var(--text-xs)", textAlign: "center", lineHeight: 1.5, marginTop: "var(--space-3)" }}>
                {t("login_with_telegram_hint")}
              </p>
            )}

            {error && <p className="form-error" style={{ textAlign: "center", marginTop: "var(--space-3)" }}>{error}</p>}

            {IS_DEV && (
              <details style={{ marginTop: "var(--space-5)", paddingTop: "var(--space-4)", borderTop: "1px solid var(--line-soft)" }}>
                <summary
                  style={{
                    cursor: "pointer", fontSize: "var(--text-xs)", fontWeight: 650,
                    color: "var(--gray-400)", textAlign: "center", listStyle: "none",
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

          <p style={{ textAlign: "center", fontSize: "var(--text-xs)", color: "var(--gray-400)", marginTop: "var(--space-4)" }}>
            {t("login_customers_note")}
          </p>
        </div>
      </div>
    </div>
  );
}
