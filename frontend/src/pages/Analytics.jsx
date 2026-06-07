import { useEffect, useState } from "react";
import { getAnalytics } from "../api/client";
import useStore from "../store/useStore";
import { useT } from "../i18n";

export default function Analytics() {
  const { lang, activeBusiness } = useStore();
  const t = useT(lang);
  const [data, setData] = useState(null);
  const [days, setDays] = useState(30);

  useEffect(() => {
    if (activeBusiness) load();
  }, [activeBusiness, days]);

  const load = async () => {
    const result = await getAnalytics(activeBusiness.id, days);
    setData(result);
  };

  if (!activeBusiness) return <p style={{ padding: 24, color: "var(--gray-500)" }}>Select a business first.</p>;
  if (!data) return <p style={{ padding: 24 }}>{t("loading")}</p>;

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">{t("analytics")}</h1>
        <select value={days} onChange={(e) => setDays(parseInt(e.target.value))} style={{ width: "auto" }}>
          <option value={7}>7 days</option>
          <option value={30}>30 days</option>
          <option value={90}>90 days</option>
        </select>
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
          <div className="stat-label">{t("no_show")} rate</div>
        </div>
      </div>

      {data.top_services.length > 0 && (
        <div className="card" style={{ marginBottom: 16 }}>
          <h3 style={{ fontWeight: 700, marginBottom: 14 }}>Top Services</h3>
          {data.top_services.map((s, i) => (
            <div key={i} style={{ display: "flex", justifyContent: "space-between", padding: "8px 0", borderBottom: "1px solid var(--gray-100)" }}>
              <span>{s.name}</span>
              <strong>{s.bookings}</strong>
            </div>
          ))}
        </div>
      )}

      {data.top_staff.length > 0 && (
        <div className="card" style={{ marginBottom: 16 }}>
          <h3 style={{ fontWeight: 700, marginBottom: 14 }}>Top Staff</h3>
          {data.top_staff.map((s, i) => (
            <div key={i} style={{ display: "flex", justifyContent: "space-between", padding: "8px 0", borderBottom: "1px solid var(--gray-100)" }}>
              <span>{s.name}</span>
              <strong>{s.bookings}</strong>
            </div>
          ))}
        </div>
      )}

      {data.daily_last_7_days.length > 0 && (
        <div className="card">
          <h3 style={{ fontWeight: 700, marginBottom: 14 }}>Last 7 Days</h3>
          {data.daily_last_7_days.map((d, i) => (
            <div key={i} style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
              <span style={{ fontSize: 13, color: "var(--gray-500)", width: 90 }}>{d.date}</span>
              <div style={{
                height: 20, background: "var(--primary)", borderRadius: 4,
                width: `${Math.min(d.bookings * 20, 200)}px`, minWidth: d.bookings > 0 ? 20 : 0,
              }} />
              <span style={{ fontSize: 13, fontWeight: 600 }}>{d.bookings}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
