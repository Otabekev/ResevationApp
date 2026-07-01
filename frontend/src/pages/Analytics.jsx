import { useEffect, useState } from "react";
import { getAnalytics } from "../api/client";
import useStore from "../store/useStore";
import { useT } from "../i18n";
import { SkeletonList } from "../components/Skeleton";
import EmptyState from "../components/EmptyState";
import dayjs from "dayjs";
import { IconChart, IconCalendar, IconCheck, IconBan, IconUsers, IconScissors } from "../components/icons";

const PERIODS = [7, 30, 90];

const STATUS_COLORS = {
  confirmed: "var(--brand-500)",
  completed: "var(--info)",
  pending: "var(--warning)",
  cancelled_by_customer: "var(--danger)",
  cancelled_by_business: "#9C3A24",
  no_show: "var(--gray-400)",
  rescheduled: "var(--gray-300)",
};

function Donut({ byStatus, total, t }) {
  const entries = Object.entries(byStatus).filter(([, n]) => n > 0);
  if (total === 0 || entries.length === 0) return null;

  let acc = 0;
  const segs = entries.map(([status, n]) => {
    const from = (acc / total) * 360;
    acc += n;
    const to = (acc / total) * 360;
    return `${STATUS_COLORS[status] || "var(--gray-300)"} ${from}deg ${to}deg`;
  });

  return (
    <div className="donut">
      <div className="donut-ring" style={{ background: `conic-gradient(${segs.join(", ")})` }}>
        <div className="donut-hole">
          <span className="n">{total}</span>
          <span className="l">{t("total_bookings")}</span>
        </div>
      </div>
      <div className="legend">
        {entries.map(([status, n]) => (
          <div key={status} className="legend-row">
            <span className="sw" style={{ background: STATUS_COLORS[status] || "var(--gray-300)" }} />
            <span>{t(status) || status}</span>
            <span className="n">{n}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function Analytics() {
  const { lang, activeBusiness } = useStore();
  const t = useT(lang);
  const [data, setData] = useState(null);
  const [error, setError] = useState(false);
  const [days, setDays] = useState(30);

  useEffect(() => {
    if (activeBusiness) load();
  }, [activeBusiness, days]);

  const load = async () => {
    setError(false);
    try {
      const result = await getAnalytics(activeBusiness.id, days);
      setData(result);
    } catch {
      setError(true);
    }
  };

  if (!activeBusiness) {
    return <EmptyState icon={<IconChart size={26} />} title={t("select_business_first")} subtitle={t("select_business_desc")} />;
  }
  if (error) return <div className="card"><EmptyState title={t("error")} subtitle={t("try_again")} /></div>;
  if (!data) return <SkeletonList count={4} />;

  const completedish = (data.by_status?.confirmed || 0) + (data.by_status?.completed || 0);
  const maxService = Math.max(1, ...data.top_services.map((s) => s.bookings));
  const maxStaff = Math.max(1, ...data.top_staff.map((s) => s.bookings));
  const maxDaily = Math.max(1, ...data.daily_last_7_days.map((d) => d.bookings));
  const today = dayjs().format("YYYY-MM-DD");

  return (
    <div className="animate-in">
      <div className="page-header">
        <div>
          <h1 className="page-title">{t("analytics")}</h1>
          <p className="page-subtitle">{t("analytics_subtitle")}</p>
        </div>
        <div className="segmented">
          {PERIODS.map((p) => (
            <button key={p} type="button" className={days === p ? "on" : ""} onClick={() => setDays(p)}>
              {t(`days_${p}`)}
            </button>
          ))}
        </div>
      </div>

      {data.total_bookings === 0 && (
        <div className="card" style={{ marginBottom: "var(--space-4)" }}>
          <EmptyState
            icon={<IconChart size={26} />}
            title={t("analytics_empty_title")}
            subtitle={t("analytics_empty_sub")}
          />
        </div>
      )}

      <div className="stats-grid stagger">
        <div className="stat-card">
          <div className="stat-head"><span className="stat-icon"><IconCalendar size={18} /></span></div>
          <div className="stat-value">{data.total_bookings}</div>
          <div className="stat-label">{t("total_bookings")}</div>
        </div>
        <div className="stat-card">
          <div className="stat-head"><span className="stat-icon blue"><IconCheck size={18} /></span></div>
          <div className="stat-value">{completedish}</div>
          <div className="stat-label">{t("confirmed_completed")}</div>
        </div>
        <div className="stat-card">
          <div className="stat-head"><span className="stat-icon red"><IconBan size={18} /></span></div>
          <div className="stat-value" style={{ color: data.no_show_rate_percent > 10 ? "var(--danger)" : undefined }}>
            {data.no_show_rate_percent}%
          </div>
          <div className="stat-label">{t("no_show_rate")}</div>
        </div>
        <div className="stat-card">
          <div className="stat-head"><span className="stat-icon honey"><IconChart size={18} /></span></div>
          <div className="stat-value">
            {data.total_bookings ? Math.round((completedish / data.total_bookings) * 100) : 0}%
          </div>
          <div className="stat-label">{t("success_rate")}</div>
        </div>
      </div>

      <div className="stack stagger" style={{ gap: "var(--space-4)" }}>
        {/* Last 7 days vertical bars */}
        {data.daily_last_7_days.length > 0 && (
          <div className="card">
            <h3 className="card-title" style={{ marginBottom: "var(--space-2)" }}>{t("last_7_days_analytics")}</h3>
            <div className="vbar-wrap">
              {data.daily_last_7_days.map((d) => (
                <div key={d.date} className="vbar-col">
                  <span className="vbar-count">{d.bookings}</span>
                  <div
                    className={`vbar${d.bookings === 0 ? " is-zero" : ""}${d.date === today ? " is-today" : ""}`}
                    style={{ height: `${Math.max(4, (d.bookings / maxDaily) * 100)}%` }}
                    title={`${d.date}: ${d.bookings}`}
                  />
                  <span className="vbar-day">{t(`wd_${dayjs(d.date).day()}`)}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Status breakdown donut */}
        {data.total_bookings > 0 && (
          <div className="card">
            <h3 className="card-title" style={{ marginBottom: "var(--space-4)" }}>{t("by_status")}</h3>
            <Donut byStatus={data.by_status || {}} total={data.total_bookings} t={t} />
          </div>
        )}

        {/* Top services */}
        {data.top_services.length > 0 && (
          <div className="card">
            <div className="row" style={{ gap: 10, marginBottom: "var(--space-3)" }}>
              <span className="stat-icon" aria-hidden><IconScissors size={16} /></span>
              <h3 className="card-title">{t("top_services")}</h3>
            </div>
            {data.top_services.map((s, i) => (
              <div key={i} className="hbar-row">
                <span className="hbar-label">{s.name}</span>
                <div className="hbar-track">
                  <div className="hbar-fill" style={{ width: `${(s.bookings / maxService) * 100}%` }} />
                </div>
                <span className="hbar-value">{s.bookings}</span>
              </div>
            ))}
          </div>
        )}

        {/* Top staff */}
        {data.top_staff.length > 0 && (
          <div className="card">
            <div className="row" style={{ gap: 10, marginBottom: "var(--space-3)" }}>
              <span className="stat-icon honey" aria-hidden><IconUsers size={16} /></span>
              <h3 className="card-title">{t("top_staff")}</h3>
            </div>
            {data.top_staff.map((s, i) => (
              <div key={i} className="hbar-row">
                <span className="hbar-label">{s.name}</span>
                <div className="hbar-track">
                  <div className="hbar-fill honey" style={{ width: `${(s.bookings / maxStaff) * 100}%` }} />
                </div>
                <span className="hbar-value">{s.bookings}</span>
              </div>
            ))}
          </div>
        )}

      </div>
    </div>
  );
}
