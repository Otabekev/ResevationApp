import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { getMe } from "../api/client";
import useStore from "../store/useStore";
import { useT } from "../i18n";

const IS_DEV = import.meta.env.DEV || import.meta.env.VITE_DEV_BYPASS_TELEGRAM === "true";

function BrandMark() {
  return (
    <div
      aria-hidden
      style={{
        width: 56, height: 56, borderRadius: 16,
        background: "linear-gradient(160deg, var(--brand-500), var(--brand-700))",
        display: "flex", alignItems: "center", justifyContent: "center",
        color: "#fff", fontSize: 30, fontWeight: 800, letterSpacing: "-0.04em",
        boxShadow: "var(--shadow-md)",
      }}
    >
      R
    </div>
  );
}

export default function Login() {
  const [token, setToken] = useState("");
  const [error, setError] = useState("");
  const { setAuth, lang } = useStore();
  const t = useT(lang);
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
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
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", minHeight: "100vh", padding: "var(--space-6)" }}>
      <div className="card animate-in" style={{ width: "100%", maxWidth: 380, padding: "var(--space-6)" }}>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", textAlign: "center", marginBottom: "var(--space-6)" }}>
          <BrandMark />
          <h1 style={{ fontSize: "var(--text-2xl)", fontWeight: 800, letterSpacing: "-0.025em", marginTop: "var(--space-4)" }}>Rezerv</h1>
          <p style={{ color: "var(--gray-500)", marginTop: "var(--space-2)", fontSize: "var(--text-sm)", lineHeight: 1.5 }}>
            {t("login_telegram_instruction")}
          </p>
        </div>

        {IS_DEV && (
          <form onSubmit={handleSubmit}>
            <div
              style={{
                fontSize: "var(--text-xs)", fontWeight: 600, color: "var(--brand-700)", background: "var(--brand-50)",
                borderRadius: "var(--radius-sm)", padding: "var(--space-2) var(--space-3)", marginBottom: "var(--space-4)", textAlign: "center",
              }}
            >
              {t("dev_mode_notice")}
            </div>
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
            {error && <p style={{ color: "var(--danger)", fontSize: "var(--text-sm)", marginBottom: "var(--space-3)" }}>{error}</p>}
            <button type="submit" className="btn btn-primary btn-full">{t("sign_in")}</button>
          </form>
        )}

        {!IS_DEV && error && <p style={{ color: "var(--danger)", fontSize: "var(--text-sm)" }}>{error}</p>}
      </div>
    </div>
  );
}
