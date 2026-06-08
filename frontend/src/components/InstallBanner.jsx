import { useEffect, useState } from "react";
import useStore from "../store/useStore";
import { useT } from "../i18n";

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
    // iOS Safari's legacy flag
    window.navigator.standalone === true
  );
}

/**
 * Soft "Install Rezerv" banner shown on the Dashboard.
 *
 * Only renders when:
 *   • Chrome/Edge captured `beforeinstallprompt` (PWA is installable)
 *   • User hasn't dismissed within the last 7 days
 *   • App isn't already running in standalone mode
 *
 * iOS Safari doesn't fire `beforeinstallprompt`, so this banner is Android/desktop
 * Chrome only — iOS users install via Share → Add to Home Screen, which is
 * documented in the README/help but not surfaced here (scope cut for v1).
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
        background: "var(--brand-50)",
        border: "1px solid var(--brand-100)",
        display: "flex",
        alignItems: "center",
        gap: "var(--space-3)",
        flexWrap: "wrap",
      }}
    >
      <span aria-hidden style={{ fontSize: 28, lineHeight: 1 }}>📲</span>
      <div style={{ flex: 1, minWidth: 200 }}>
        <div style={{ fontWeight: 700, fontSize: "var(--text-sm)", color: "var(--brand-800)" }}>
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
