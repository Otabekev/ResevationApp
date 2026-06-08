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

// Native language names so a user always recognises their own language.
const LANGS = [
  { code: "uz", label: "O‘zbekcha" },
  { code: "ru", label: "Русский" },
  { code: "en", label: "English" },
];

function LanguageSwitcher({ className }) {
  const { lang, setLang } = useStore();
  return (
    <div className={`lang-switcher ${className || ""}`}>
      <span aria-hidden className="lang-switcher-icon">🌐</span>
      <select
        aria-label="Language"
        value={lang}
        onChange={(e) => setLang(e.target.value)}
      >
        {LANGS.map((l) => (
          <option key={l.code} value={l.code}>{l.label}</option>
        ))}
      </select>
    </div>
  );
}

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
              aria-label={t(item.key)}
              title={t(item.key)}
              className={({ isActive }) => `nav-item${isActive ? " active" : ""}`}
            >
              <span aria-hidden>{item.icon}</span>
              {t(item.key)}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-footer">
          <LanguageSwitcher className="lang-switcher-desktop" />
          {user?.name && <div className="sidebar-user">{user.name}</div>}
        </div>
      </aside>

      {/* Mobile floating language control (sidebar is hidden under 768px) */}
      <LanguageSwitcher className="lang-switcher-mobile" />

      {/* Main content */}
      <main className="main-content">{children}</main>

      {/* Mobile bottom nav */}
      <nav className="bottom-nav">
        {allNav.filter((item) => item.mobile).map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            end={item.path === "/"}
            aria-label={t(item.key)}
            className={({ isActive }) => `bottom-nav-item${isActive ? " active" : ""}`}
          >
            <span aria-hidden>{item.icon}</span>
            {t(item.key)}
          </NavLink>
        ))}
      </nav>
    </div>
  );
}
