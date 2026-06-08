import { useEffect, useState } from "react";
import { getAdminStats, getAdminBusinesses, updateBusinessStatus } from "../api/client";
import useStore from "../store/useStore";
import { useT } from "../i18n";
import { SkeletonList } from "../components/Skeleton";
import EmptyState from "../components/EmptyState";

export default function AdminPanel() {
  const { lang } = useStore();
  const t = useT(lang);
  const [stats, setStats] = useState(null);
  const [businesses, setBusinesses] = useState([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    loadStats();
    loadBusinesses();
  }, [statusFilter]);

  const loadStats = async () => {
    try {
      const s = await getAdminStats();
      setStats(s);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  };

  const loadBusinesses = async () => {
    try {
      const params = statusFilter ? { status: statusFilter } : {};
      const data = await getAdminBusinesses(params);
      setBusinesses(data);
    } catch {
      setError(true);
    }
  };

  const handleStatusChange = async (bizId, newStatus) => {
    await updateBusinessStatus(bizId, newStatus);
    await loadBusinesses();
  };

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">{t("admin")}</h1>
      </div>

      {error ? (
        <EmptyState icon="⚠️" title={t("error")} />
      ) : loading ? (
        <SkeletonList count={4} />
      ) : stats && (
        <div className="stats-grid" style={{ marginBottom: "var(--space-6)" }}>
          <div className="stat-card">
            <div className="stat-value">{stats.total_businesses}</div>
            <div className="stat-label">{t("total_businesses")}</div>
          </div>
          <div className="stat-card">
            <div className="stat-value" style={{ color: "var(--success)" }}>{stats.active_businesses}</div>
            <div className="stat-label">{t("active_businesses")}</div>
          </div>
          <div className="stat-card">
            <div className="stat-value" style={{ color: "var(--warning)" }}>{stats.trial_businesses}</div>
            <div className="stat-label">{t("trial_businesses")}</div>
          </div>
          <div className="stat-card">
            <div className="stat-value">{stats.total_bookings}</div>
            <div className="stat-label">{t("total_bookings")}</div>
          </div>
          <div className="stat-card">
            <div className="stat-value">{stats.bookings_today}</div>
            <div className="stat-label">{t("today")}</div>
          </div>
          <div className="stat-card">
            <div className="stat-value">{stats.total_customers}</div>
            <div className="stat-label">{t("total_customers")}</div>
          </div>
        </div>
      )}

      <div className="card">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "var(--space-3)" }}>
          <h3 style={{ fontWeight: 700 }}>{t("businesses")}</h3>
          <select
            aria-label={t("status")}
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            style={{ width: "auto" }}
          >
            <option value="">{t("all")}</option>
            <option value="pending">{t("status_pending")}</option>
            <option value="trial">{t("status_trial")}</option>
            <option value="active">{t("status_active")}</option>
            <option value="suspended">{t("status_suspended")}</option>
            <option value="blocked">{t("status_blocked")}</option>
          </select>
        </div>
        {businesses.length === 0 ? (
          <EmptyState title={t("no_data")} />
        ) : (
        <table className="table">
          <thead>
            <tr>
              <th>{t("name")}</th>
              <th>{t("district")}</th>
              <th>{t("status")}</th>
              <th>{t("actions")}</th>
            </tr>
          </thead>
          <tbody>
            {businesses.map((b) => (
              <tr key={b.id}>
                <td style={{ fontWeight: 600 }}>{b.name}</td>
                <td style={{ fontSize: "var(--text-sm)" }}>{b.district}, {b.region}</td>
                <td>
                  <span className={`badge ${
                    b.status === "active" ? "badge-confirmed" :
                    b.status === "trial" ? "badge-pending" :
                    b.status === "suspended" ? "badge-no_show" :
                    b.status === "blocked" ? "badge-cancelled_by_business" : ""
                  }`}>{t(`status_${b.status}`)}</span>
                </td>
                <td>
                  <select
                    aria-label={t("status")}
                    value={b.status}
                    onChange={(e) => handleStatusChange(b.id, e.target.value)}
                    style={{ width: "auto", fontSize: "var(--text-sm)", padding: "var(--space-1) var(--space-2)" }}
                  >
                    <option value="pending">{t("status_pending")}</option>
                    <option value="trial">{t("status_trial")}</option>
                    <option value="active">{t("status_active")}</option>
                    <option value="suspended">{t("status_suspended")}</option>
                    <option value="blocked">{t("status_blocked")}</option>
                  </select>
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
