import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getBookings, getAnalytics } from "../api/client";
import useStore from "../store/useStore";
import { useT } from "../i18n";
import InstallBanner from "../components/InstallBanner";
import EmptyState from "../components/EmptyState";
import dayjs from "dayjs";
import {
  IconSparkle, IconCalendar, IconCheck, IconBan, IconClock,
  IconUsers, IconChart, IconStore, IconChevronRight, IconPlus, IconShield,
} from "../components/icons";

const STATUS_BADGE = {
  pending: "badge-pending",
  confirmed: "badge-confirmed",
  completed: "badge-completed",
  cancelled_by_customer: "badge-cancelled_by_customer",
  cancelled_by_business: "badge-cancelled_by_business",
  no_show: "badge-no_show",
};

function DashboardSkeleton() {
  return (
    <div>
      <div className="page-header"><div className="skeleton" style={{ width: 200, height: 28 }} /></div>
      <div className="stats-grid">
        {Array.from({ length: 4 }).map((_, i) => (
          <div className="stat-card" key={i}>
            <div className="skeleton" style={{ width: 34, height: 34, borderRadius: 10, marginBottom: 10 }} />
            <div className="skeleton" style={{ width: 48, height: 28, marginBottom: 6 }} />
            <div className="skeleton skeleton-text" style={{ width: 64 }} />
          </div>
        ))}
      </div>
      <div className="card">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="skeleton skeleton-text" style={{ width: `${80 - i * 8}%`, height: 16, margin: "14px 0" }} />
        ))}
      </div>
    </div>
  );
}

function greetingKey() {
  const h = new Date().getHours();
  if (h < 12) return "greeting_morning";
  if (h < 18) return "greeting_day";
  return "greeting_evening";
}

export default function Dashboard() {
  const { lang, user, activeBusiness, businesses } = useStore();
  const t = useT(lang);
  const [todayBookings, setTodayBookings] = useState([]);
  const [analytics, setAnalytics] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!activeBusiness) {
      setLoading(false);
      return;
    }
    let alive = true;
    const load = async () => {
      setLoading(true);
      try {
        const today = dayjs().format("YYYY-MM-DD");
        const [bookings, stats] = await Promise.all([
          getBookings(activeBusiness.id, { booking_date: today }),
          getAnalytics(activeBusiness.id, 7),
        ]);
        if (!alive) return;
        setTodayBookings(bookings);
        setAnalytics(stats);
      } catch (e) {
        console.error(e);
      } finally {
        if (alive) setLoading(false);
      }
    };
    load();
    return () => { alive = false; };
  }, [activeBusiness]);

  if (loading) return <DashboardSkeleton />;

  if (!activeBusiness && businesses.length === 0) {
    return (
      <div>
        <div className="page-header"><h1 className="page-title">{t("dashboard")}</h1></div>
        <div className="card">
          <EmptyState
            icon={<IconStore size={26} />}
            title={t("no_business_title")}
            subtitle={t("no_business_desc")}
            action={
              <Link to="/setup" className="btn btn-primary">
                <IconPlus size={17} /> {t("register_business")}
              </Link>
            }
          />
        </div>
      </div>
    );
  }

  // Business submitted but admin hasn't approved it yet — customers can't
  // book here, so the normal dashboard would be empty + confusing. Show the
  // waiting-for-approval screen instead.
  if (activeBusiness?.status === "pending") {
    return (
      <div className="animate-in">
        <div className="page-header">
          <div>
            <div className="eyebrow" style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <IconClock size={13} /> {t("status_pending")}
            </div>
            <h1 className="page-title" style={{ marginTop: 4 }}>{activeBusiness.name}</h1>
          </div>
        </div>
        <div className="card" style={{ borderLeft: "3px solid var(--warning)" }}>
          <EmptyState
            icon={<IconClock size={26} />}
            title={t("awaiting_approval_title")}
            subtitle={t("awaiting_approval_desc")}
          />
        </div>
      </div>
    );
  }

  const firstName = (user?.name || "").split(" ")[0];
  const upcoming = todayBookings.filter((b) => ["pending", "confirmed"].includes(b.status));
  const svcName = (b) => b[`service_name_${lang}`] || b.service_name_uz || `#${b.service_id}`;

  const QUICK_LINKS = [
    { to: "/bookings", Icon: IconCalendar, key: "bookings" },
    { to: "/staff", Icon: IconUsers, key: "staff" },
    { to: "/schedule", Icon: IconClock, key: "schedule" },
    { to: "/analytics", Icon: IconChart, key: "analytics" },
    ...(user?.role === "super_admin" ? [{ to: "/admin", Icon: IconShield, key: "admin" }] : []),
  ];

  return (
    <div className="stagger">
      <InstallBanner />

      <div className="page-header">
        <div>
          <div className="eyebrow" style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <IconSparkle size={13} /> {dayjs().format("DD.MM.YYYY")}
          </div>
          <h1 className="page-title" style={{ marginTop: 4 }}>
            {t(greetingKey())}{firstName ? `, ${firstName}` : ""}
          </h1>
          <p className="page-subtitle">{activeBusiness?.name}</p>
        </div>
        <Link to="/bookings" className="btn btn-primary">
          <IconPlus size={17} /> {t("new_booking")}
        </Link>
      </div>

      {analytics && (
        <div className="stats-grid">
          <div className="stat-card">
            <div className="stat-head">
              <span className="stat-icon honey"><IconClock size={18} /></span>
            </div>
            <div className="stat-value" style={{ color: "var(--brand-700)" }}>{upcoming.length}</div>
            <div className="stat-label">{t("today_remaining")}</div>
          </div>
          <div className="stat-card">
            <div className="stat-head">
              <span className="stat-icon"><IconCalendar size={18} /></span>
            </div>
            <div className="stat-value">{analytics.total_bookings}</div>
            <div className="stat-label">{t("last_7_days")}</div>
          </div>
          <div className="stat-card">
            <div className="stat-head">
              <span className="stat-icon blue"><IconCheck size={18} /></span>
            </div>
            <div className="stat-value">{(analytics.by_status?.confirmed || 0) + (analytics.by_status?.completed || 0)}</div>
            <div className="stat-label">{t("confirmed")}</div>
          </div>
          <div className="stat-card">
            <div className="stat-head">
              <span className="stat-icon red"><IconBan size={18} /></span>
            </div>
            <div className="stat-value" style={{ color: analytics.by_status?.no_show ? "var(--danger)" : undefined }}>
              {analytics.by_status?.no_show || 0}
            </div>
            <div className="stat-label">{t("no_show")}</div>
          </div>
        </div>
      )}

      {/* Today's schedule */}
      <div className="card" style={{ marginBottom: "var(--space-4)" }}>
        <div className="row" style={{ justifyContent: "space-between", marginBottom: "var(--space-4)" }}>
          <div>
            <h2 className="card-title">{t("todays_schedule")}</h2>
            <div className="card-sub">{dayjs().format("DD MMMM")}</div>
          </div>
          <Link to="/bookings" className="btn btn-ghost btn-sm">
            {t("view_all")} <IconChevronRight size={15} />
          </Link>
        </div>

        {todayBookings.length === 0 ? (
          <EmptyState icon={<IconCalendar size={24} />} title={t("no_bookings_today")} subtitle={t("no_bookings_today_sub")} />
        ) : (
          <div className="stack" style={{ gap: "var(--space-2)" }}>
            {todayBookings.map((b) => (
              <div
                key={b.id}
                className={`booking-card card-tight${["cancelled_by_customer", "cancelled_by_business", "no_show"].includes(b.status) ? " is-muted" : ""}`}
                style={{ boxShadow: "none", padding: "var(--space-3)" }}
              >
                <div className="booking-time">
                  <span className="t1">{b.start_time?.slice(0, 5)}</span>
                  <span className="t2">{b.end_time?.slice(0, 5)}</span>
                </div>
                <div className="booking-main">
                  <div style={{ fontWeight: 700 }} className="ellipsis">{b.customer_name}</div>
                  <div className="booking-meta">
                    <span>{svcName(b)}</span>
                    {b.staff_name && <><span>·</span><span>{b.staff_name}</span></>}
                  </div>
                </div>
                <span className={`badge ${STATUS_BADGE[b.status] || ""}`} style={{ alignSelf: "center" }}>
                  {t(b.status)}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Quick links — also the only mobile path to Staff/Schedule */}
      <div
        style={{
          display: "grid", gap: "var(--space-3)",
          gridTemplateColumns: "repeat(auto-fill, minmax(150px, 1fr))",
        }}
      >
        {QUICK_LINKS.map(({ to, Icon, key }) => (
          <Link key={to} to={to} className="card card-tight card-interactive row" style={{ gap: 12 }}>
            <span className="stat-icon" style={{ flexShrink: 0 }}><Icon size={18} /></span>
            <span style={{ fontWeight: 700, fontSize: "var(--text-sm)", color: "var(--gray-800)" }}>{t(key)}</span>
            <IconChevronRight size={15} style={{ marginLeft: "auto", color: "var(--gray-300)" }} />
          </Link>
        ))}
      </div>
    </div>
  );
}
