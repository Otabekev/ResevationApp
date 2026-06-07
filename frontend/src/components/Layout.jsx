import { NavLink } from "react-router-dom";
import useStore from "../store/useStore";
import { useT } from "../i18n";

const NAV_ITEMS = [
  { path: "/", icon: "🏠", key: "dashboard", mobile: true },
  { path: "/bookings", icon: "📅", key: "bookings", mobile: true },
  { path: "/services", icon: "✂️", key: "services", mobile: true },
  { path: "/staff", icon: "👥", key: "staff", mobile: true },
  { path: "/schedule", icon: "🗓️", key: "schedule", mobile: false },
  { path: "/analytics", icon: "📊", key: "analytics", mobile: false },
  { path: "/settings", icon: "⚙️", key: "settings", mobile: true },
];

export default function Layout({ children }) {
  const { user, lang } = useStore();
  const t = useT(lang);

  const allNav = user?.role === "super_admin"
    ? [...NAV_ITEMS, { path: "/admin", icon: "🛡️", key: "admin" }]
    : NAV_ITEMS;

  return (
    <div className="layout">
      {/* Desktop sidebar */}
      <aside className="sidebar">
        <div className="sidebar-logo">
          <span
            aria-hidden
            style={{
              width: 30, height: 30, borderRadius: 9, flexShrink: 0,
              background: "linear-gradient(160deg, var(--brand-400), var(--brand-600))",
              display: "inline-flex", alignItems: "center", justifyContent: "center",
              fontSize: 17, fontWeight: 800, letterSpacing: "-0.04em", color: "#fff",
            }}
          >
            R
          </span>
          Rezerv
        </div>
        <nav className="sidebar-nav">
          {allNav.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              end={item.path === "/"}
              className={({ isActive }) => `nav-item${isActive ? " active" : ""}`}
            >
              <span>{item.icon}</span>
              {t(item.key)}
            </NavLink>
          ))}
        </nav>
        <div style={{ padding: "16px", fontSize: 13, color: "#6b7280" }}>
          {user?.name}
        </div>
      </aside>

      {/* Main content */}
      <main className="main-content">{children}</main>

      {/* Mobile bottom nav */}
      <nav className="bottom-nav">
        {allNav.filter((item) => item.mobile).map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            end={item.path === "/"}
            className={({ isActive }) => `bottom-nav-item${isActive ? " active" : ""}`}
          >
            <span>{item.icon}</span>
            {t(item.key)}
          </NavLink>
        ))}
      </nav>
    </div>
  );
}
