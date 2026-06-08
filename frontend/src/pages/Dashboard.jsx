import { useEffect, useState } from "react";
import { getMyBusinesses, getBookings, getAnalytics, getServices } from "../api/client";
import useStore from "../store/useStore";
import { useT } from "../i18n";
import InstallBanner from "../components/InstallBanner";
import dayjs from "dayjs";

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
      <div className="page-header"><div className="skeleton" style={{ width: 160, height: 26 }} /></div>
      <div className="stats-grid">
        {Array.from({ length: 4 }).map((_, i) => (
          <div className="stat-card" key={i}>
            <div className="skeleton" style={{ width: 48, height: 30, marginBottom: 8 }} />
            <div className="skeleton skeleton-text" style={{ width: 64 }} />
          </div>
        ))}
      </div>
      <div className="card">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="skeleton skeleton-text" style={{ width: `${80 - i * 8}%`, height: 16, margin: "12px 0" }} />
        ))}
      </div>
    </div>
  );
}

export default function Dashboard() {
  const { lang, activeBusiness, setActiveBusiness } = useStore();
  const t = useT(lang);
  const [businesses, setBusinesses] = useState([]);
  const [todayBookings, setTodayBookings] = useState([]);
  const [analytics, setAnalytics] = useState(null);
  const [serviceNames, setServiceNames] = useState({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadData();
  }, []);

  useEffect(() => {
    if (activeBusiness) loadBusinessData(activeBusiness.id);
  }, [activeBusiness]);

  const loadData = async () => {
    try {
      const bizList = await getMyBusinesses();
      setBusinesses(bizList);
      if (bizList.length > 0 && !activeBusiness) {
        setActiveBusiness(bizList[0]);
        await loadBusinessData(bizList[0].id);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const loadBusinessData = async (bizId) => {
    const today = dayjs().format("YYYY-MM-DD");
    const [bookings, stats, services] = await Promise.all([
      getBookings(bizId, { booking_date: today }),
      getAnalytics(bizId, 7),
      getServices(bizId),
    ]);
    setTodayBookings(bookings);
    setAnalytics(stats);
    setServiceNames(
      Object.fromEntries(services.map((s) => [s.id, s[`name_${lang}`] || s.name_uz]))
    );
  };

  if (loading) return <DashboardSkeleton />;

  if (businesses.length === 0) {
    return (
      <div>
        <div className="page-header"><h1 className="page-title">{t("dashboard")}</h1></div>
        <div className="card empty-state">
          <div style={{ fontSize: 48, marginBottom: "var(--space-4)" }}>🏪</div>
          <h2 style={{ marginBottom: "var(--space-2)", fontSize: "var(--text-lg)" }}>{t("no_business_title")}</h2>
          <p style={{ color: "var(--gray-500)", marginBottom: "var(--space-6)" }}>{t("no_business_desc")}</p>
          <a href="/setup" className="btn btn-primary">{t("register_business")}</a>
        </div>
      </div>
    );
  }

  return (
    <div className="animate-in">
      <InstallBanner />
      <div className="page-header">
        <h1 className="page-title">{t("dashboard")}</h1>
        {businesses.length > 1 && (
          <select
            value={activeBusiness?.id || ""}
            onChange={(e) => {
              const biz = businesses.find((b) => b.id === parseInt(e.target.value));
              setActiveBusiness(biz);
            }}
            style={{ width: "auto", maxWidth: 220 }}
          >
            {businesses.map((b) => (
              <option key={b.id} value={b.id}>{b.name}</option>
            ))}
          </select>
        )}
      </div>

      {analytics && (
        <div className="stats-grid">
          <div className="stat-card">
            <div className="stat-value" style={{ color: "var(--brand-600)" }}>{todayBookings.length}</div>
            <div className="stat-label">{t("today")}</div>
          </div>
          <div className="stat-card">
            <div className="stat-value">{analytics.total_bookings}</div>
            <div className="stat-label">{t("last_7_days")}</div>
          </div>
          <div className="stat-card">
            <div className="stat-value">{analytics.by_status?.confirmed || 0}</div>
            <div className="stat-label">{t("confirmed")}</div>
          </div>
          <div className="stat-card">
            <div className="stat-value" style={{ color: "var(--danger)" }}>
              {analytics.by_status?.no_show || 0}
            </div>
            <div className="stat-label">{t("no_show")}</div>
          </div>
        </div>
      )}

      <div className="card">
        <h2 style={{ fontSize: "var(--text-md)", fontWeight: 700, marginBottom: "var(--space-4)", letterSpacing: "-0.01em" }}>
          {t("todays_schedule")} · {dayjs().format("DD MMMM")}
        </h2>
        {todayBookings.length === 0 ? (
          <p className="empty-state" style={{ padding: "var(--space-6) 0" }}>{t("no_data")}</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>{t("time")}</th>
                <th>{t("customer")}</th>
                <th>{t("service")}</th>
                <th>{t("status")}</th>
              </tr>
            </thead>
            <tbody>
              {todayBookings.map((b) => (
                <tr key={b.id}>
                  <td style={{ fontWeight: 700, color: "var(--gray-900)" }}>{b.start_time?.slice(0, 5)}</td>
                  <td>
                    <div style={{ fontWeight: 600 }}>{b.customer_name}</div>
                    <div style={{ fontSize: "var(--text-xs)", color: "var(--gray-500)" }}>{b.customer_phone}</div>
                  </td>
                  <td>{serviceNames[b.service_id] || `#${b.service_id}`}</td>
                  <td>
                    <span className={`badge ${STATUS_BADGE[b.status] || ""}`}>{t(b.status)}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
