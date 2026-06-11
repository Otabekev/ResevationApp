import { useEffect, useState } from "react";
import { getAdminStats, getAdminBusinesses, updateBusinessStatus } from "../api/client";
import useStore from "../store/useStore";
import { useT } from "../i18n";
import { SkeletonList } from "../components/Skeleton";
import EmptyState from "../components/EmptyState";
import Toast from "../components/Toast";
import {
  IconShield, IconStore, IconCalendar, IconUsers, IconClock, IconChart,
} from "../components/icons";

const STATUSES = ["pending", "trial", "active", "suspended", "blocked"];
const STATUS_BADGE = {
  active: "badge-confirmed",
  trial: "badge-pending",
  pending: "badge-completed",
  suspended: "badge-no_show",
  blocked: "badge-cancelled_by_business",
};

export default function AdminPanel() {
  const { lang } = useStore();
  const t = useT(lang);
  const [stats, setStats] = useState(null);
  const [businesses, setBusinesses] = useState([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [toast, setToast] = useState(null);

  useEffect(() => {
    loadStats();
  }, []);

  useEffect(() => {
    loadBusinesses();
  }, [statusFilter]);

  const loadStats = async () => {
    try {
      setStats(await getAdminStats());
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  };

  const loadBusinesses = async () => {
    try {
      const params = statusFilter ? { status: statusFilter } : {};
      setBusinesses(await getAdminBusinesses(params));
    } catch {
      setError(true);
    }
  };

  const handleStatusChange = async (bizId, newStatus) => {
    try {
      await updateBusinessStatus(bizId, newStatus);
      setToast({ message: t("saved"), variant: "success" });
      await Promise.all([loadBusinesses(), loadStats()]);
    } catch {
      setToast({ message: t("error"), variant: "error" });
    }
  };

  return (
    <div className="animate-in">
      <div className="page-header">
        <div>
          <div className="eyebrow" style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <IconShield size={13} /> {t("platform")}
          </div>
          <h1 className="page-title" style={{ marginTop: 4 }}>{t("admin")}</h1>
        </div>
      </div>

      {error ? (
        <div className="card"><EmptyState title={t("error")} subtitle={t("try_again")} /></div>
      ) : loading ? (
        <SkeletonList count={4} />
      ) : (
        <>
          {stats && (
            <div className="stats-grid stagger">
              <div className="stat-card">
                <div className="stat-head"><span className="stat-icon"><IconStore size={18} /></span></div>
                <div className="stat-value">{stats.total_businesses}</div>
                <div className="stat-label">{t("total_businesses")}</div>
              </div>
              <div className="stat-card">
                <div className="stat-head"><span className="stat-icon"><IconChart size={18} /></span></div>
                <div className="stat-value" style={{ color: "var(--success)" }}>{stats.active_businesses}</div>
                <div className="stat-label">{t("active_businesses")}</div>
              </div>
              <div className="stat-card">
                <div className="stat-head"><span className="stat-icon honey"><IconClock size={18} /></span></div>
                <div className="stat-value" style={{ color: "var(--warning)" }}>{stats.trial_businesses}</div>
                <div className="stat-label">{t("trial_businesses")}</div>
              </div>
              <div className="stat-card">
                <div className="stat-head"><span className="stat-icon blue"><IconCalendar size={18} /></span></div>
                <div className="stat-value">{stats.total_bookings}</div>
                <div className="stat-label">{t("total_bookings")}</div>
              </div>
              <div className="stat-card">
                <div className="stat-head"><span className="stat-icon"><IconCalendar size={18} /></span></div>
                <div className="stat-value">{stats.bookings_today}</div>
                <div className="stat-label">{t("today")}</div>
              </div>
              <div className="stat-card">
                <div className="stat-head"><span className="stat-icon"><IconUsers size={18} /></span></div>
                <div className="stat-value">{stats.total_customers}</div>
                <div className="stat-label">{t("total_customers")}</div>
              </div>
            </div>
          )}

          <div className="card">
            <div className="row" style={{ justifyContent: "space-between", marginBottom: "var(--space-4)", flexWrap: "wrap" }}>
              <h3 className="card-title">{t("businesses")}</h3>
              <div className="segmented">
                <button type="button" className={statusFilter === "" ? "on" : ""} onClick={() => setStatusFilter("")}>
                  {t("all")}
                </button>
                {STATUSES.map((s) => (
                  <button key={s} type="button" className={statusFilter === s ? "on" : ""} onClick={() => setStatusFilter(s)}>
                    {t(`status_${s}`)}
                  </button>
                ))}
              </div>
            </div>

            {businesses.length === 0 ? (
              <EmptyState icon={<IconStore size={24} />} title={t("no_data")} />
            ) : (
              <div className="table-scroll">
                <table className="table">
                  <thead>
                    <tr>
                      <th>{t("name")}</th>
                      <th>{t("district")}</th>
                      <th>{t("status")}</th>
                      <th style={{ width: 160 }}>{t("actions")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {businesses.map((b) => (
                      <tr key={b.id}>
                        <td style={{ fontWeight: 700 }}>{b.name}</td>
                        <td style={{ fontSize: "var(--text-sm)", color: "var(--gray-500)" }}>
                          {b.district}, {b.region}
                        </td>
                        <td>
                          <span className={`badge ${STATUS_BADGE[b.status] || ""}`}>{t(`status_${b.status}`)}</span>
                        </td>
                        <td>
                          <select
                            aria-label={t("status")}
                            value={b.status}
                            onChange={(e) => handleStatusChange(b.id, e.target.value)}
                            style={{ minHeight: 38, padding: "6px 28px 6px 10px", fontSize: "var(--text-sm)" }}
                          >
                            {STATUSES.map((s) => (
                              <option key={s} value={s}>{t(`status_${s}`)}</option>
                            ))}
                          </select>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}

      <Toast toast={toast} onClose={() => setToast(null)} />
    </div>
  );
}
