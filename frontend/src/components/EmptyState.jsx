/**
 * Shared empty / no-data / error placeholder.
 * Wraps the existing .empty-state design-system class so every page renders
 * the SAME structure (icon → title → subtitle → optional action).
 */
export default function EmptyState({ icon = "📭", title, subtitle, action }) {
  return (
    <div className="empty-state">
      {icon && (
        <div aria-hidden style={{ fontSize: 40, lineHeight: 1, marginBottom: "var(--space-3)", opacity: 0.65 }}>
          {icon}
        </div>
      )}
      {title && (
        <h3 style={{ fontSize: "var(--text-md)", fontWeight: 700, color: "var(--gray-700)", marginBottom: "var(--space-1)" }}>
          {title}
        </h3>
      )}
      {subtitle && (
        <p style={{ fontSize: "var(--text-sm)", color: "var(--gray-500)", maxWidth: 320, margin: "0 auto", lineHeight: 1.5 }}>
          {subtitle}
        </p>
      )}
      {action && <div style={{ marginTop: "var(--space-4)" }}>{action}</div>}
    </div>
  );
}
