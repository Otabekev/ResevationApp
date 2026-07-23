import { useEffect, useRef, useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import useStore from "../store/useStore";
import { useT } from "../i18n";
import { updateMyLanguage } from "../api/client";
import BrandMark from "./BrandMark";
import {
  IconHome, IconCalendar, IconScissors, IconUsers, IconClock, IconChart,
  IconSettings, IconShield, IconChevronDown, IconLogout, IconGlobe, IconCheck, IconSend,
  IconRefresh,
} from "./icons";
import { refreshApp } from "../pwa";

const NAV_ITEMS = [
  { path: "/", Icon: IconHome, key: "dashboard", mobile: true },
  { path: "/bookings", Icon: IconCalendar, key: "bookings", mobile: true },
  { path: "/queue", Icon: IconClock, key: "queue", mobile: true },
  { path: "/services", Icon: IconScissors, key: "services", mobile: true },
  { path: "/staff", Icon: IconUsers, key: "staff", mobile: false },
  { path: "/schedule", Icon: IconClock, key: "schedule", mobile: false },
  { path: "/analytics", Icon: IconChart, key: "analytics", mobile: true },
  { path: "/settings", Icon: IconSettings, key: "settings", mobile: true },
];

// A provider (doctor) manages only their OWN day, queue, hours, and setup — no
// owner/manager pages (Services, Staff, Analytics, Settings are hidden).
const PROVIDER_NAV_ITEMS = [
  { path: "/", Icon: IconHome, key: "my_day", mobile: true },
  { path: "/queue", Icon: IconClock, key: "queue", mobile: true },
  { path: "/my-schedule", Icon: IconCalendar, key: "my_working_hours", mobile: true },
  { path: "/my-setup", Icon: IconSettings, key: "my_setup", mobile: true },
];

// Super-admin lives in its own world: no business switcher, no owner pages.
const ADMIN_NAV_ITEMS = [
  { path: "/", Icon: IconHome, key: "overview", mobile: true },
  { path: "/admin/businesses", Icon: IconShield, key: "businesses", mobile: true },
  { path: "/admin/users", Icon: IconUsers, key: "users", mobile: true },
  { path: "/admin/bookings", Icon: IconCalendar, key: "admin_bookings", mobile: true },
  { path: "/admin/broadcast", Icon: IconSend, key: "broadcast", mobile: true },
];

const LANGS = [
  { code: "uz", label: "O‘zbekcha" },
  { code: "ru", label: "Русский" },
  { code: "en", label: "English" },
];

function LogoMark({ size = 34 }) {
  return (
    <span className="logo-mark" style={{ width: size, height: size }} aria-hidden>
      <BrandMark size={size * 0.62} />
    </span>
  );
}

function initials(name = "") {
  return name
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0].toUpperCase())
    .join("") || "R";
}

function useClickOutside(ref, onAway) {
  useEffect(() => {
    const handler = (e) => {
      if (ref.current && !ref.current.contains(e.target)) onAway();
    };
    document.addEventListener("pointerdown", handler);
    return () => document.removeEventListener("pointerdown", handler);
  }, [ref, onAway]);
}

function BusinessSwitcher() {
  const { activeBusiness, businesses, setActiveBusiness } = useStore();
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useClickOutside(ref, () => setOpen(false));

  if (!activeBusiness) return null;
  const many = businesses.length > 1;

  return (
    <div className="menu-wrap" ref={ref}>
      <button
        type="button"
        className="biz-switcher"
        onClick={() => many && setOpen((o) => !o)}
        style={{ cursor: many ? "pointer" : "default" }}
        aria-haspopup={many ? "menu" : undefined}
        aria-expanded={open}
      >
        <span className="biz-dot" style={activeBusiness.photo_url ? { padding: 0, overflow: "hidden" } : undefined}>
          {activeBusiness.photo_url
            ? <img src={activeBusiness.photo_url} alt="" style={{ width: "100%", height: "100%", objectFit: "cover" }} />
            : initials(activeBusiness.name)}
        </span>
        <span className="biz-name">{activeBusiness.name}</span>
        {many && <IconChevronDown size={15} style={{ color: "var(--gray-400)", flexShrink: 0 }} />}
      </button>
      {open && (
        <div className="menu" role="menu">
          {businesses.map((b) => (
            <button
              key={b.id}
              type="button"
              role="menuitem"
              className="menu-item"
              onClick={() => { setActiveBusiness(b); setOpen(false); }}
            >
              <span className="biz-dot" style={{ width: 24, height: 24, fontSize: 11, ...(b.photo_url ? { padding: 0, overflow: "hidden" } : {}) }}>
                {b.photo_url
                  ? <img src={b.photo_url} alt="" style={{ width: "100%", height: "100%", objectFit: "cover" }} />
                  : initials(b.name)}
              </span>
              <span className="grow ellipsis">{b.name}</span>
              {b.id === activeBusiness.id && <IconCheck size={15} style={{ color: "var(--brand-600)" }} />}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function UserMenu() {
  const { user, lang, setLang, logout } = useStore();
  const t = useT(lang);
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useClickOutside(ref, () => setOpen(false));

  const [refreshing, setRefreshing] = useState(false);

  const changeLang = (code) => {
    setLang(code);
    updateMyLanguage(code).catch(() => {}); // persist server-side; cosmetic if it fails
  };

  const handleRefresh = () => {
    // Installed PWAs have no browser reload button — this reloads (and pulls the
    // latest app version). The page reloads, so this state is just to block a
    // double-tap in the moment before it does.
    setRefreshing(true);
    refreshApp();
  };

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  return (
    <div className="menu-wrap" ref={ref}>
      <button
        type="button"
        className="avatar"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={user?.name || "Account"}
        style={{ cursor: "pointer" }}
      >
        {initials(user?.name)}
      </button>
      {open && (
        <div className="menu" role="menu">
          <div style={{ padding: "10px 12px 6px" }}>
            <div style={{ fontWeight: 750, fontSize: "var(--text-sm)" }} className="ellipsis">{user?.name}</div>
            <div style={{ fontSize: "var(--text-xs)", color: "var(--gray-500)" }}>{t(`role_${user?.role}`) || user?.role}</div>
          </div>
          <div className="menu-divider" />
          <button
            type="button"
            role="menuitem"
            className="menu-item"
            onClick={handleRefresh}
            disabled={refreshing}
          >
            <IconRefresh size={16} />
            {refreshing ? t("loading") : t("refresh")}
          </button>
          <div className="menu-divider" />
          <div className="menu-label" style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <IconGlobe size={13} /> {t("language")}
          </div>
          {LANGS.map((l) => (
            <button
              key={l.code}
              type="button"
              role="menuitem"
              className="menu-item"
              onClick={() => changeLang(l.code)}
            >
              <span className="grow">{l.label}</span>
              {lang === l.code && <IconCheck size={15} style={{ color: "var(--brand-600)" }} />}
            </button>
          ))}
          <div className="menu-divider" />
          <button type="button" role="menuitem" className="menu-item danger" onClick={handleLogout}>
            <IconLogout size={17} />
            {t("logout")}
          </button>
        </div>
      )}
    </div>
  );
}

export default function Layout({ children }) {
  const { user, lang, activeBusiness } = useStore();
  const t = useT(lang);

  const isAdmin = user?.role === "super_admin";
  // A desk-manager (secretary) can't change business settings/storefront — hide
  // the owner-only Settings page. The backend enforces this regardless of the UI.
  const isManager = !isAdmin && activeBusiness?.access_role === "manager";
  // A provider (doctor) gets a self-service dashboard: their own day/queue/hours/
  // setup only. The backend row-scopes every call regardless of the UI.
  const isProvider = !isAdmin && activeBusiness?.access_role === "provider";
  let allNav = isAdmin ? ADMIN_NAV_ITEMS : isProvider ? PROVIDER_NAV_ITEMS : NAV_ITEMS;
  if (isManager) allNav = allNav.filter((item) => item.path !== "/settings");

  return (
    <div className="layout">
      {/* Desktop sidebar */}
      <aside className="sidebar">
        <div className="sidebar-logo">
          <LogoMark />
          <span className="logo-word">
            Qulay Navbat
            <small>{t("brand_tagline")}</small>
          </span>
        </div>
        <nav className="sidebar-nav">
          {allNav.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              end={item.path === "/"}
              aria-label={t(item.key)}
              className={({ isActive }) => `nav-item${isActive ? " active" : ""}`}
            >
              <item.Icon size={19} />
              {t(item.key)}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-footer">
          <div style={{ fontSize: "var(--text-xs)", color: "rgba(255,255,255,.4)", padding: "0 6px" }}>
            © {new Date().getFullYear()} Qulay Navbat
          </div>
        </div>
      </aside>

      <div className="content-col">
        {/* Desktop topbar */}
        <header className="topbar">
          {isAdmin ? (
            <span className="biz-switcher" style={{ cursor: "default" }}>
              <IconShield size={15} style={{ color: "var(--brand-600)" }} />
              <span className="biz-name">{t("platform_admin")}</span>
            </span>
          ) : (
            <BusinessSwitcher />
          )}
          <div className="topbar-spacer" />
          <UserMenu />
        </header>

        {/* Mobile app bar */}
        <header className="appbar">
          <LogoMark size={30} />
          <span className="appbar-title grow">{isAdmin ? t("platform_admin") : "Qulay Navbat"}</span>
          <UserMenu />
        </header>

        {/* Main content */}
        <main className="main-content">
          <div className="page">{children}</div>
        </main>
      </div>

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
            <item.Icon size={21} />
            {t(item.key)}
          </NavLink>
        ))}
      </nav>
    </div>
  );
}
