import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { getAdminBusinesses, updateBusinessStatus } from "../api/client";
import useStore from "../store/useStore";
import { useT } from "../i18n";
import { SkeletonList } from "../components/Skeleton";
import EmptyState from "../components/EmptyState";
import Toast from "../components/Toast";
import { IconStore, IconChevronRight } from "../components/icons";

const STATUSES = ["pending", "trial", "active", "suspended", "blocked"];
const STATUS_BADGE = {
  active: "badge-confirmed",
  trial: "badge-pending",
  pending: "badge-completed",
  suspended: "badge-no_show",
  blocked: "badge-cancelled_by_business",
};

export default function AdminBusinesses() {
  const { lang } = useStore();
  const t = useT(lang);
  const [businesses, setBusinesses] = useState([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [toast, setToast] = useState(null);

  const load = async () => {
    try {
      const params = statusFilter ? { status: statusFilter } : {};
      setBusinesses(await getAdminBusinesses(params));
      setError(false);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [statusFilter]);

  const handleStatusChange = async (bizId, newStatus) => {
    try {
      await updateBusinessStatus(bizId, newStatus);
      setToast({ message: t("saved"), variant: "success" });
      await load();
    } catch {
      setToast({ message: t("error"), variant: "error" });
    }
  };

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return businesses;
    return businesses.filter((b) =>
      (b.name || "").toLowerCase().includes(q) ||
      (b.district || "").toLowerCase().includes(q) ||
      (b.region || "").toLowerCase().includes(q)
    );
  }, [businesses, search]);

  return (
    <div className="animate-in">
      <div className="page-header">
        <div>
          <div className="eyebrow">{t("platform")}</div>
          <h1 className="page-title" style={{ marginTop: 4 }}>{t("businesses")}</h1>
        </div>
      </div>

      <div className="card">
        <div className="row" style={{ justifyContent: "space-between", marginBottom: "var(--space-4)", flexWrap: "wrap", gap: 12 }}>
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
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={t("search_businesses")}
            aria-label={t("search_businesses")}
            style={{ minHeight: 40, minWidth: 220 }}
          />
        </div>

        {loading ? (
          <SkeletonList count={5} />
        ) : error ? (
          <EmptyState title={t("error")} subtitle={t("try_again")} />
        ) : filtered.length === 0 ? (
          <EmptyState icon={<IconStore size={24} />} title={t("no_data")} />
        ) : (
          <div className="table-scroll">
            <table className="table">
              <thead>
                <tr>
                  <th>{t("name")}</th>
                  <th>{t("district")}</th>
                  <th>{t("status")}</th>
                  <th style={{ width: 160 }}>{t("change_status")}</th>
                  <th style={{ width: 40 }}></th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((b) => (
                  <tr key={b.id}>
                    <td>
                      <Link to={`/admin/businesses/${b.id}`} style={{ fontWeight: 700, color: "inherit", textDecoration: "none" }}>
                        {b.name}
                      </Link>
                    </td>
                    <td style={{ fontSize: "var(--text-sm)", color: "var(--gray-500)" }}>
                      {b.district || "—"}{b.region ? `, ${b.region}` : ""}
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
                    <td>
                      <Link to={`/admin/businesses/${b.id}`} className="btn btn-ghost btn-sm" aria-label={t("view_details")}>
                        <IconChevronRight size={15} />
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <Toast toast={toast} onClose={() => setToast(null)} />
    </div>
  );
}
