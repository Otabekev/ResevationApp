import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import dayjs from "dayjs";
import {
  getAdminStats, getAdminRecent, updateBusinessStatus,
  getAdminInsights, getSystemHealth, getNeedsAttention,
} from "../api/client";
import useStore from "../store/useStore";
import { useT } from "../i18n";
import { SkeletonList } from "../components/Skeleton";
import EmptyState from "../components/EmptyState";
import Toast from "../components/Toast";
import {
  IconShield, IconStore, IconCalendar, IconUsers, IconClock, IconChart,
  IconCheck, IconChevronRight, IconBan,
} from "../components/icons";

function HealthPill({ ok, label }) {
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 7,
      padding: "6px 12px", borderRadius: "var(--radius-full)",
      background: "var(--surface)", border: "1px solid var(--line-soft)",
      fontSize: "var(--text-sm)", fontWeight: 650,
    }}>
      <span style={{
        width: 9, height: 9, borderRadius: 999,
        background: ok ? "var(--success)" : "var(--danger)",
        boxShadow: ok ? "0 0 0 3px rgba(16,185,129,.15)" : "0 0 0 3px rgba(239,68,68,.15)",
      }} />
      {label}
    </span>
  );
}

function TrendBars({ data, t }) {
  const max = Math.max(1, ...data.map((d) => d.bookings));
  const today = dayjs().format("YYYY-MM-DD");
  return (
    <div className="vbar-wrap">
      {data.map((d) => (
        <div key={d.date} className="vbar-col">
          <span className="vbar-count">{d.bookings}</span>
          <div
            className={`vbar${d.bookings === 0 ? " is-zero" : ""}${d.date === today ? " is-today" : ""}`}
            style={{ height: `${Math.max(4, (d.bookings / max) * 100)}%` }}
            title={`${d.date}: ${d.bookings}`}
          />
          <span className="vbar-day">{t(`wd_${dayjs(d.date).day()}`)}</span>
        </div>
      ))}
    </div>
  );
}

const STATUS_BADGE = {
  active: "badge-confirmed",
  trial: "badge-pending",
  pending: "badge-completed",
  suspended: "badge-no_show",
  blocked: "badge-cancelled_by_business",
};

const BOOKING_BADGE = {
  pending: "badge-pending",
  confirmed: "badge-confirmed",
  completed: "badge-completed",
  cancelled_by_customer: "badge-cancelled_by_customer",
  cancelled_by_business: "badge-cancelled_by_business",
  no_show: "badge-no_show",
};

export default function AdminOverview() {
  const { lang } = useStore();
  const t = useT(lang);
  const [stats, setStats] = useState(null);
  const [recent, setRecent] = useState(null);
  const [insights, setInsights] = useState(null);
  const [health, setHealth] = useState(null);
  const [needs, setNeeds] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [toast, setToast] = useState(null);

  const load = async () => {
    try {
      // stats + recent are core (fail → error screen); the extras degrade gracefully.
      const [s, r, ins, h, na] = await Promise.all([
        getAdminStats(),
        getAdminRecent(),
        getAdminInsights().catch(() => null),
        getSystemHealth().catch(() => null),
        getNeedsAttention().catch(() => null),
      ]);
      setStats(s);
      setRecent(r);
      setInsights(ins);
      setHealth(h);
      setNeeds(na);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const approve = async (bizId) => {
    try {
      await updateBusinessStatus(bizId, "active");
      setToast({ message: t("approved"), variant: "success" });
      await load();
    } catch {
      setToast({ message: t("error"), variant: "error" });
    }
  };

  if (loading) return <SkeletonList count={6} />;

  if (error) {
    return (
      <div className="animate-in">
        <div className="page-header"><h1 className="page-title">{t("overview")}</h1></div>
        <div className="card"><EmptyState title={t("error")} subtitle={t("try_again")} /></div>
      </div>
    );
  }

  const STAT_CARDS = [
    { icon: <IconStore size={18} />, value: stats.total_businesses, label: t("total_businesses") },
    { icon: <IconChart size={18} />, value: stats.active_businesses, label: t("active_businesses"), color: "var(--success)" },
    { icon: <IconClock size={18} />, value: recent.pending.length, label: t("pending_approvals"), color: "var(--warning)", iconCls: "honey" },
    { icon: <IconCalendar size={18} />, value: stats.total_bookings, label: t("total_bookings"), iconCls: "blue" },
    { icon: <IconCalendar size={18} />, value: stats.bookings_today, label: t("today") },
    { icon: <IconUsers size={18} />, value: stats.total_customers, label: t("total_customers") },
  ];

  return (
    <div className="animate-in">
      <div className="page-header">
        <div>
          <div className="eyebrow" style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <IconShield size={13} /> {t("platform")}
          </div>
          <h1 className="page-title" style={{ marginTop: 4 }}>{t("overview")}</h1>
        </div>
      </div>

      {/* Platform health strip */}
      {health && (
        <div className="row" style={{ gap: 8, flexWrap: "wrap", marginBottom: "var(--space-4)" }}>
          <HealthPill ok={health.db} label={t("health_db")} />
          <HealthPill ok={!!(health.scheduler?.running && health.scheduler?.healthy)} label={t("health_scheduler")} />
          <HealthPill ok={!!health.healthy} label={health.healthy ? t("health_all_ok") : t("health_degraded")} />
        </div>
      )}

      {/* Needs attention — active businesses that can't serve a customer yet */}
      {needs && needs.total > 0 && (
        <div className="card" style={{ borderLeft: "3px solid var(--danger)", marginBottom: "var(--space-4)" }}>
          <h3 className="card-title" style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: "var(--space-1)" }}>
            <IconBan size={16} /> {t("needs_attention")}
            <span className="badge badge-no_show" style={{ marginLeft: 4 }}>{needs.total}</span>
          </h3>
          <p style={{ fontSize: "var(--text-sm)", color: "var(--gray-500)", marginBottom: "var(--space-3)" }}>
            {t("needs_attention_sub")}
          </p>
          <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: 4 }}>
            {needs.items.slice(0, 6).map((b) => (
              <li key={b.id}>
                <Link to={`/admin/businesses/${b.id}`} className="row" style={{ padding: "8px 12px", borderRadius: "var(--radius-md)", textDecoration: "none", color: "inherit" }}>
                  <div className="grow" style={{ minWidth: 0 }}>
                    <div style={{ fontWeight: 700, fontSize: "var(--text-sm)" }}>{b.name}</div>
                    <div style={{ fontSize: "var(--text-xs)", color: "var(--gray-500)" }}>{b.district || "—"}</div>
                  </div>
                  <div className="row" style={{ gap: 4, flexWrap: "wrap", justifyContent: "flex-end" }}>
                    {b.missing.map((m) => (
                      <span key={m} className="badge badge-no_show" style={{ fontSize: 10 }}>{t(`missing_${m}`)}</span>
                    ))}
                  </div>
                  <IconChevronRight size={15} style={{ color: "var(--gray-400)", flexShrink: 0 }} />
                </Link>
              </li>
            ))}
          </ul>
          {needs.total > 6 && (
            <div style={{ marginTop: 8, fontSize: "var(--text-xs)", color: "var(--gray-500)" }}>
              +{needs.total - 6} {t("more")}
            </div>
          )}
        </div>
      )}

      <div className="stats-grid stagger">
        {STAT_CARDS.map((c, i) => (
          <div className="stat-card" key={i}>
            <div className="stat-head">
              <span className={`stat-icon${c.iconCls ? ` ${c.iconCls}` : ""}`}>{c.icon}</span>
            </div>
            <div className="stat-value" style={c.color ? { color: c.color } : undefined}>{c.value}</div>
            <div className="stat-label">{c.label}</div>
          </div>
        ))}
      </div>

      {insights && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: "var(--space-4)", marginBottom: "var(--space-4)" }}>
          <div className="card">
            <h3 className="card-title" style={{ marginBottom: "var(--space-3)" }}>{t("last_7_days")}</h3>
            <TrendBars data={insights.daily_last_7_days} t={t} />
          </div>
          <div className="card">
            <div className="row" style={{ justifyContent: "space-between", marginBottom: "var(--space-3)", gap: 8 }}>
              <h3 className="card-title">{t("top_businesses")}</h3>
              <span className={`badge ${insights.no_show_rate_percent > 10 ? "badge-no_show" : ""}`}>
                {t("no_show_rate")}: {insights.no_show_rate_percent}%
              </span>
            </div>
            {insights.top_businesses.length === 0 ? (
              <EmptyState icon={<IconChart size={22} />} title={t("no_data")} />
            ) : (
              <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: 8 }}>
                {insights.top_businesses.map((b, i) => (
                  <li key={i} className="row" style={{ gap: 10 }}>
                    <span style={{ width: 18, color: "var(--gray-400)", fontWeight: 800, fontSize: "var(--text-sm)" }}>{i + 1}</span>
                    <span className="grow" style={{ fontWeight: 650, fontSize: "var(--text-sm)" }}>{b.name}</span>
                    <span style={{ fontWeight: 800 }}>{b.bookings}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}

      {recent.pending.length > 0 && (
        <div className="card" style={{ borderLeft: "3px solid var(--warning)" }}>
          <div className="row" style={{ justifyContent: "space-between", marginBottom: "var(--space-3)" }}>
            <h3 className="card-title" style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <IconClock size={16} /> {t("pending_approvals")}
              <span className="badge badge-pending" style={{ marginLeft: 4 }}>{recent.pending.length}</span>
            </h3>
          </div>
          <div className="table-scroll">
            <table className="table">
              <thead>
                <tr>
                  <th>{t("name")}</th>
                  <th>{t("district")}</th>
                  <th>{t("created_at")}</th>
                  <th style={{ width: 200 }}>{t("actions")}</th>
                </tr>
              </thead>
              <tbody>
                {recent.pending.map((b) => (
                  <tr key={b.id}>
                    <td style={{ fontWeight: 700 }}>{b.name}</td>
                    <td style={{ fontSize: "var(--text-sm)", color: "var(--gray-500)" }}>
                      {b.district || "—"}{b.region ? `, ${b.region}` : ""}
                    </td>
                    <td style={{ fontSize: "var(--text-sm)", color: "var(--gray-500)" }}>
                      {b.created_at ? dayjs(b.created_at).format("DD.MM.YYYY") : "—"}
                    </td>
                    <td>
                      <div className="row" style={{ gap: 6, flexWrap: "nowrap" }}>
                        <button type="button" className="btn btn-primary btn-sm" onClick={() => approve(b.id)}>
                          <IconCheck size={14} /> {t("approve")}
                        </button>
                        <Link to={`/admin/businesses/${b.id}`} className="btn btn-ghost btn-sm">
                          {t("view")}
                        </Link>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div className="grid-2-col" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: "var(--space-4)" }}>
        {/* Recent businesses */}
        <div className="card">
          <div className="row" style={{ justifyContent: "space-between", marginBottom: "var(--space-3)" }}>
            <h3 className="card-title">{t("recent_businesses")}</h3>
            <Link to="/admin/businesses" className="btn btn-ghost btn-sm">{t("view_all")}</Link>
          </div>
          {recent.recent_businesses.length === 0 ? (
            <EmptyState icon={<IconStore size={24} />} title={t("no_data")} />
          ) : (
            <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: 4 }}>
              {recent.recent_businesses.map((b) => (
                <li key={b.id}>
                  <Link
                    to={`/admin/businesses/${b.id}`}
                    className="row"
                    style={{
                      padding: "10px 12px", borderRadius: "var(--radius-md)",
                      textDecoration: "none", color: "inherit",
                      transition: "background 0.15s",
                    }}
                    onMouseEnter={(e) => e.currentTarget.style.background = "var(--gray-50)"}
                    onMouseLeave={(e) => e.currentTarget.style.background = "transparent"}
                  >
                    <div className="grow">
                      <div style={{ fontWeight: 700, fontSize: "var(--text-sm)" }}>{b.name}</div>
                      <div style={{ fontSize: "var(--text-xs)", color: "var(--gray-500)" }}>
                        {b.district || "—"} · {b.created_at ? dayjs(b.created_at).fromNow?.() || dayjs(b.created_at).format("DD.MM") : ""}
                      </div>
                    </div>
                    <span className={`badge ${STATUS_BADGE[b.status] || ""}`}>{t(`status_${b.status}`)}</span>
                    <IconChevronRight size={15} style={{ color: "var(--gray-400)" }} />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Recent bookings */}
        <div className="card">
          <h3 className="card-title" style={{ marginBottom: "var(--space-3)" }}>{t("recent_bookings")}</h3>
          {recent.recent_bookings.length === 0 ? (
            <EmptyState icon={<IconCalendar size={24} />} title={t("no_data")} />
          ) : (
            <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: 4 }}>
              {recent.recent_bookings.map((b) => (
                <li key={b.id} className="row" style={{ padding: "10px 12px", borderRadius: "var(--radius-md)" }}>
                  <div className="grow">
                    <div style={{ fontWeight: 700, fontSize: "var(--text-sm)" }}>
                      {b.customer_name} · {b.service_name || "—"}
                    </div>
                    <div style={{ fontSize: "var(--text-xs)", color: "var(--gray-500)" }}>
                      {b.business_name || `#${b.business_id}`} · {b.booking_date ? dayjs(b.booking_date).format("DD.MM") : ""} {b.booking_time?.slice(0, 5) || ""}
                    </div>
                  </div>
                  <span className={`badge ${BOOKING_BADGE[b.status] || ""}`}>{t(b.status) || b.status}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <Toast toast={toast} onClose={() => setToast(null)} />
    </div>
  );
}
