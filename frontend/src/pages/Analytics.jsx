import { useEffect, useState } from "react";
import { getAnalytics } from "../api/client";
import useStore from "../store/useStore";
import { useT } from "../i18n";
import { SkeletonList } from "../components/Skeleton";
import EmptyState from "../components/EmptyState";

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

  if (!activeBusiness)
    return <EmptyState title={t("select_business_first")} subtitle={t("select_business_desc")} />;
  if (error) return <EmptyState icon="⚠️" title={t("error")} />;
  if (!data) return <SkeletonList count={4} />;

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">{t("analytics")}</h1>
        <div className="form-group">
          <label htmlFor="analytics-period">{t("period")}</label>
          <select id="analytics-period" value={days} onChange={(e) => setDays(parseInt(e.target.value))} style={{ width: "auto" }}>
            <option value={7}>{t("days_7")}</option>
            <option value={30}>{t("days_30")}</option>
            <option value={90}>{t("days_90")}</option>
          </select>
        </div>
      </div>

      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-value">{data.total_bookings}</div>
          <div className="stat-label">{t("total_bookings")}</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{data.by_status?.confirmed || 0}</div>
          <div className="stat-label">{t("confirmed")}</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{data.by_status?.completed || 0}</div>
          <div className="stat-label">{t("completed")}</div>
        </div>
        <div className="stat-card">
          <div className="stat-value" style={{ color: "var(--danger)" }}>
            {data.no_show_rate_percent}%
          </div>
          <div className="stat-label">{t("no_show_rate")}</div>
        </div>
      </div>

      {data.top_services.length > 0 && (
        <div className="card" style={{ marginBottom: "var(--space-4)" }}>
          <h3 style={{ fontWeight: 700, marginBottom: "var(--space-4)" }}>{t("top_services")}</h3>
          {data.top_services.map((s, i) => (
            <div key={i} className="divider" style={{ display: "flex", justifyContent: "space-between", padding: "var(--space-2) 0" }}>
              <span>{s.name}</span>
              <strong>{s.bookings}</strong>
            </div>
          ))}
        </div>
      )}

      {data.top_staff.length > 0 && (
        <div className="card" style={{ marginBottom: "var(--space-4)" }}>
          <h3 style={{ fontWeight: 700, marginBottom: "var(--space-4)" }}>{t("top_staff")}</h3>
          {data.top_staff.map((s, i) => (
            <div key={i} className="divider" style={{ display: "flex", justifyContent: "space-between", padding: "var(--space-2) 0" }}>
              <span>{s.name}</span>
              <strong>{s.bookings}</strong>
            </div>
          ))}
        </div>
      )}

      {data.daily_last_7_days.length > 0 && (
        <div className="card">
          <h3 style={{ fontWeight: 700, marginBottom: "var(--space-4)" }}>{t("last_7_days_analytics")}</h3>
          {data.daily_last_7_days.map((d, i) => (
            <div key={i} style={{ display: "flex", alignItems: "center", gap: "var(--space-3)", marginBottom: "var(--space-2)" }}>
              <span style={{ fontSize: "var(--text-sm)", color: "var(--gray-500)", width: 90 }}>{d.date}</span>
              <div style={{
                height: 20, background: "var(--primary)", borderRadius: 4,
                width: `${Math.min(d.bookings * 20, 200)}px`, minWidth: d.bookings > 0 ? 20 : 0,
              }} />
              <span style={{ fontSize: "var(--text-sm)", fontWeight: 600 }}>{d.bookings}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
