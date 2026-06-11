import { useEffect, useState } from "react";
import useStore from "../store/useStore";
import { useT } from "../i18n";
import { IconInstall } from "./icons";

const DISMISS_KEY = "install_dismissed_at";
const SUPPRESSION_DAYS = 7;

function isSuppressed() {
  const at = localStorage.getItem(DISMISS_KEY);
  if (!at) return false;
  const ms = Date.now() - parseInt(at, 10);
  return ms < SUPPRESSION_DAYS * 24 * 60 * 60 * 1000;
}

function isStandalone() {
  return (
    window.matchMedia?.("(display-mode: standalone)").matches ||
    window.navigator.standalone === true // iOS Safari legacy flag
  );
}

/**
 * Soft "Install Rezerv" banner shown on the Dashboard.
 * Renders only when the browser captured `beforeinstallprompt` (installable),
 * the user hasn't dismissed it in 7 days, and we're not already standalone.
 */
export default function InstallBanner() {
  const { lang } = useStore();
  const t = useT(lang);
  const [deferredPrompt, setDeferredPrompt] = useState(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (isStandalone() || isSuppressed()) return undefined;
    const onBeforeInstall = (e) => {
      e.preventDefault();
      setDeferredPrompt(e);
      setVisible(true);
    };
    window.addEventListener("beforeinstallprompt", onBeforeInstall);
    return () => window.removeEventListener("beforeinstallprompt", onBeforeInstall);
  }, []);

  if (!visible || !deferredPrompt) return null;

  const dismiss = () => {
    localStorage.setItem(DISMISS_KEY, String(Date.now()));
    setVisible(false);
  };

  const install = async () => {
    try {
      deferredPrompt.prompt();
      await deferredPrompt.userChoice;
    } catch {
      // User aborted — fine.
    } finally {
      dismiss();
    }
  };

  return (
    <div
      className="card animate-in"
      style={{
        marginBottom: "var(--space-4)",
        background: "linear-gradient(120deg, var(--brand-50), #fff 70%)",
        border: "1px solid var(--brand-100)",
        display: "flex",
        alignItems: "center",
        gap: "var(--space-3)",
        flexWrap: "wrap",
        padding: "var(--space-4)",
      }}
    >
      <span
        aria-hidden
        style={{
          width: 42, height: 42, borderRadius: 12, flexShrink: 0,
          background: "var(--brand-600)", color: "#fff",
          display: "inline-flex", alignItems: "center", justifyContent: "center",
        }}
      >
        <IconInstall size={22} />
      </span>
      <div style={{ flex: 1, minWidth: 200 }}>
        <div style={{ fontWeight: 750, fontSize: "var(--text-sm)", color: "var(--brand-800)" }}>
          {t("install_app_cta")}
        </div>
        <div style={{ fontSize: "var(--text-xs)", color: "var(--gray-600)", marginTop: 2 }}>
          {t("install_app_desc")}
        </div>
      </div>
      <div style={{ display: "flex", gap: "var(--space-2)" }}>
        <button type="button" className="btn btn-ghost btn-sm" onClick={dismiss}>
          {t("install_later")}
        </button>
        <button type="button" className="btn btn-primary btn-sm" onClick={install}>
          {t("install_app_cta")}
        </button>
      </div>
    </div>
  );
}
