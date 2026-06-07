import { useEffect, useState } from "react";
import { getAdminStats, getAdminBusinesses, updateBusinessStatus } from "../api/client";
import useStore from "../store/useStore";
import { useT } from "../i18n";

export default function AdminPanel() {
  const { lang } = useStore();
  const t = useT(lang);
  const [stats, setStats] = useState(null);
  const [businesses, setBusinesses] = useState([]);
  const [statusFilter, setStatusFilter] = useState("");

  useEffect(() => {
    loadStats();
    loadBusinesses();
  }, [statusFilter]);

  const loadStats = async () => {
    const s = await getAdminStats();
    setStats(s);
  };

  const loadBusinesses = async () => {
    const params = statusFilter ? { status: statusFilter } : {};
    const data = await getAdminBusinesses(params);
    setBusinesses(data);
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

      {stats && (
        <div className="stats-grid" style={{ marginBottom: 24 }}>
          <div className="stat-card">
            <div className="stat-value">{stats.total_businesses}</div>
            <div className="stat-label">Total businesses</div>
          </div>
          <div className="stat-card">
            <div className="stat-value" style={{ color: "var(--success)" }}>{stats.active_businesses}</div>
            <div className="stat-label">Active</div>
          </div>
          <div className="stat-card">
            <div className="stat-value" style={{ color: "var(--warning)" }}>{stats.trial_businesses}</div>
            <div className="stat-label">Trial</div>
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
            <div className="stat-label">Customers</div>
          </div>
        </div>
      )}

      <div className="card">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
          <h3 style={{ fontWeight: 700 }}>Businesses</h3>
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} style={{ width: "auto" }}>
            <option value="">All</option>
            <option value="pending">Pending</option>
            <option value="trial">Trial</option>
            <option value="active">Active</option>
            <option value="suspended">Suspended</option>
            <option value="blocked">Blocked</option>
          </select>
        </div>
        <table className="table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Name</th>
              <th>District</th>
              <th>Status</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {businesses.map((b) => (
              <tr key={b.id}>
                <td style={{ color: "var(--gray-500)" }}>#{b.id}</td>
                <td style={{ fontWeight: 600 }}>{b.name}</td>
                <td style={{ fontSize: 13 }}>{b.district}, {b.region}</td>
                <td>
                  <span className={`badge ${
                    b.status === "active" ? "badge-confirmed" :
                    b.status === "trial" ? "badge-pending" :
                    b.status === "blocked" ? "badge-cancelled_by_business" : ""
                  }`}>{b.status}</span>
                </td>
                <td>
                  <select
                    value={b.status}
                    onChange={(e) => handleStatusChange(b.id, e.target.value)}
                    style={{ width: "auto", fontSize: 13, padding: "4px 8px" }}
                  >
                    <option value="pending">Pending</option>
                    <option value="trial">Trial</option>
                    <option value="active">Active</option>
                    <option value="suspended">Suspended</option>
                    <option value="blocked">Blocked</option>
                  </select>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
