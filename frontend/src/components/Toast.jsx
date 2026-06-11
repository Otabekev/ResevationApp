import { useEffect } from "react";
import { IconCheck, IconAlert } from "./icons";

/**
 * Calm, non-blocking feedback — replaces native alert().
 * Controlled: parent holds `toast` ({ message, variant }) and clears via onClose.
 * Auto-dismisses. variant: "success" (default) | "error".
 * Bottom-centered, clear of the mobile bottom-nav and safe areas.
 */
export default function Toast({ toast, onClose, duration = 3200 }) {
  useEffect(() => {
    if (!toast) return undefined;
    const id = setTimeout(onClose, duration);
    return () => clearTimeout(id);
  }, [toast, duration, onClose]);

  if (!toast) return null;
  const { message, variant = "success" } = toast;

  return (
    <div className="toast-host">
      <div role="status" aria-live="polite" className={`toast toast-${variant}`}>
        <span className="toast-ico" aria-hidden>
          {variant === "error" ? <IconAlert size={18} /> : <IconCheck size={18} />}
        </span>
        <span>{message}</span>
      </div>
    </div>
  );
}
