import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { getMe } from "../api/client";
import useStore from "../store/useStore";

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
  const { setAuth } = useStore();
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
      setError("Invalid token");
    }
  };

  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", minHeight: "100vh", padding: 24 }}>
      <div className="card animate-in" style={{ width: "100%", maxWidth: 380, padding: 28 }}>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", textAlign: "center", marginBottom: 24 }}>
          <BrandMark />
          <h1 style={{ fontSize: 26, fontWeight: 800, letterSpacing: "-0.025em", marginTop: 16 }}>Rezerv</h1>
          <p style={{ color: "var(--gray-500)", marginTop: 6, fontSize: 14, lineHeight: 1.5 }}>
            Open this app from your Telegram bot to sign in.
          </p>
        </div>

        {IS_DEV && (
          <form onSubmit={handleSubmit}>
            <div
              style={{
                fontSize: 12, fontWeight: 600, color: "var(--brand-700)", background: "var(--brand-50)",
                borderRadius: 8, padding: "8px 12px", marginBottom: 16, textAlign: "center",
              }}
            >
              Dev mode — paste a JWT to test
            </div>
            <div className="form-group">
              <label>Access token</label>
              <input
                type="text"
                placeholder="Paste your JWT…"
                value={token}
                onChange={(e) => setToken(e.target.value)}
                autoComplete="off"
              />
            </div>
            {error && <p style={{ color: "var(--danger)", fontSize: 13, marginBottom: 12 }}>{error}</p>}
            <button type="submit" className="btn btn-primary btn-full">Sign in</button>
          </form>
        )}

        {!IS_DEV && error && <p style={{ color: "var(--danger)", fontSize: 13 }}>{error}</p>}
      </div>
    </div>
  );
}
