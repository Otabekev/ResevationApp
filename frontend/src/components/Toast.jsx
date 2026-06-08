import { useEffect } from "react";

/**
 * Calm, non-blocking feedback — replaces native alert().
 * Controlled: parent holds `toast` ({ message, variant }) and clears via onClose.
 * Auto-dismisses. variant: "success" (default) | "error".
 * Positioned top-center, clear of the mobile bottom-nav and safe areas.
 */
export default function Toast({ toast, onClose, duration = 3200 }) {
  useEffect(() => {
    if (!toast) return undefined;
    const id = setTimeout(onClose, duration);
    return () => clearTimeout(id);
  }, [toast, duration, onClose]);

  if (!toast) return null;
  const { message, variant = "success" } = toast;
  const accent = variant === "error" ? "var(--danger)" : "var(--success)";

  return (
    <div
      role="status"
      aria-live="polite"
      style={{
        position: "fixed",
        top: "calc(env(safe-area-inset-top) + var(--space-4))",
        left: "50%",
        transform: "translateX(-50%)",
        zIndex: 400,
        display: "flex",
        alignItems: "center",
        gap: "var(--space-2)",
        maxWidth: "calc(100vw - var(--space-8))",
        padding: "var(--space-3) var(--space-4)",
        background: "var(--surface)",
        border: "1px solid var(--line)",
        borderLeft: `3px solid ${accent}`,
        borderRadius: "var(--radius-md)",
        boxShadow: "var(--shadow-lg)",
        fontSize: "var(--text-sm)",
        fontWeight: 650,
        color: "var(--gray-800)",
        animation: "fade-in-up var(--dur-slow) var(--ease-out)",
      }}
    >
      <span aria-hidden style={{ color: accent, fontWeight: 800 }}>
        {variant === "error" ? "!" : "✓"}
      </span>
      <span>{message}</span>
    </div>
  );
}
