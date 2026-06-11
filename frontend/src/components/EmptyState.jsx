import { IconNote } from "./icons";

/**
 * Shared empty / no-data / error placeholder.
 * `icon` accepts a rendered element (an SVG icon from ./icons); legacy emoji
 * strings still render for any stragglers.
 */
export default function EmptyState({ icon, title, subtitle, action }) {
  return (
    <div className="empty-state animate-in">
      <div className="empty-ico" aria-hidden>
        {icon && typeof icon !== "string" ? (
          icon
        ) : icon ? (
          <span style={{ fontSize: 26 }}>{icon}</span>
        ) : (
          <IconNote size={26} />
        )}
      </div>
      {title && <h3 className="empty-title">{title}</h3>}
      {subtitle && <p className="empty-sub">{subtitle}</p>}
      {action && <div style={{ marginTop: "var(--space-5)" }}>{action}</div>}
    </div>
  );
}
