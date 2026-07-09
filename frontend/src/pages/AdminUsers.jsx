import { useEffect, useState } from "react";
import { getAdminUsers, setUserActive } from "../api/client";
import useStore from "../store/useStore";
import { useT } from "../i18n";
import { SkeletonList } from "../components/Skeleton";
import EmptyState from "../components/EmptyState";
import Toast from "../components/Toast";
import { IconUsers, IconBan, IconCheck } from "../components/icons";

const ROLES = ["customer", "business_owner", "staff", "super_admin"];

export default function AdminUsers() {
  const { lang, user } = useStore();
  const t = useT(lang);
  const PAGE_SIZE = 20;
  const [users, setUsers] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [roleFilter, setRoleFilter] = useState("");
  const [search, setSearch] = useState("");
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [busyId, setBusyId] = useState(null);
  const [toast, setToast] = useState(null);

  useEffect(() => {
    const id = setTimeout(() => { setQ(search.trim()); setPage(1); }, 350);
    return () => clearTimeout(id);
  }, [search]);

  const load = async () => {
    setLoading(true);
    try {
      const params = { page, page_size: PAGE_SIZE };
      if (roleFilter) params.role = roleFilter;
      if (q) params.q = q;
      const res = await getAdminUsers(params);
      setUsers(res.items || []);
      setTotal(res.total || 0);
      setError(false);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [roleFilter, q, page]);

  const toggleActive = async (u) => {
    setBusyId(u.id);
    try {
      await setUserActive(u.id, !u.is_active);
      setUsers((list) => list.map((x) => (x.id === u.id ? { ...x, is_active: !x.is_active } : x)));
      setToast({ message: t("saved"), variant: "success" });
    } catch (err) {
      setToast({ message: err.response?.data?.detail || t("error"), variant: "error" });
    } finally {
      setBusyId(null);
    }
  };

  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const rangeStart = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
  const rangeEnd = Math.min(page * PAGE_SIZE, total);

  return (
    <div className="animate-in">
      <div className="page-header">
        <div>
          <div className="eyebrow">{t("platform")}</div>
          <h1 className="page-title" style={{ marginTop: 4 }}>{t("users")}</h1>
        </div>
      </div>

      <div className="card">
        <div className="row" style={{ justifyContent: "space-between", marginBottom: "var(--space-4)", flexWrap: "wrap", gap: 12 }}>
          <div className="segmented">
            <button type="button" className={roleFilter === "" ? "on" : ""} onClick={() => { setRoleFilter(""); setPage(1); }}>{t("all")}</button>
            {ROLES.map((r) => (
              <button key={r} type="button" className={roleFilter === r ? "on" : ""} onClick={() => { setRoleFilter(r); setPage(1); }}>
                {t(`role_${r}`)}
              </button>
            ))}
          </div>
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={t("search_users")}
            aria-label={t("search_users")}
            style={{ minHeight: 40, minWidth: 220 }}
          />
        </div>

        {loading ? (
          <SkeletonList count={5} />
        ) : error ? (
          <EmptyState title={t("error")} subtitle={t("try_again")} />
        ) : users.length === 0 ? (
          <EmptyState icon={<IconUsers size={24} />} title={t("no_data")} />
        ) : (
          <div className="table-scroll">
            <table className="table">
              <thead>
                <tr>
                  <th>{t("name")}</th>
                  <th>{t("username")}</th>
                  <th>Telegram ID</th>
                  <th>{t("role")}</th>
                  <th>{t("status")}</th>
                  <th style={{ width: 130 }}></th>
                </tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.id}>
                    <td style={{ fontWeight: 700 }}>{u.name || "—"}</td>
                    <td style={{ color: "var(--gray-500)" }}>{u.username ? `@${u.username}` : "—"}</td>
                    <td style={{ fontFamily: "monospace", fontSize: "var(--text-sm)" }}>{u.telegram_id || "—"}</td>
                    <td><span className="badge">{t(`role_${u.role}`) || u.role}</span></td>
                    <td>
                      <span className={`badge ${u.is_active ? "badge-confirmed" : "badge-no_show"}`}>
                        {u.is_active ? t("active_label") : t("banned")}
                      </span>
                    </td>
                    <td>
                      {u.role !== "super_admin" && u.id !== user?.id && (
                        <button
                          type="button"
                          className={`btn btn-sm ${u.is_active ? "btn-secondary" : "btn-primary"}`}
                          disabled={busyId === u.id}
                          onClick={() => toggleActive(u)}
                        >
                          {u.is_active ? <><IconBan size={14} /> {t("ban")}</> : <><IconCheck size={14} /> {t("reactivate")}</>}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {!loading && !error && total > 0 && (
          <div className="row" style={{ justifyContent: "space-between", alignItems: "center", marginTop: "var(--space-4)", flexWrap: "wrap", gap: 8 }}>
            <span style={{ fontSize: "var(--text-sm)", color: "var(--gray-500)" }}>{rangeStart}–{rangeEnd} / {total}</span>
            <div className="row" style={{ gap: 6 }}>
              <button type="button" className="btn btn-ghost btn-sm" disabled={page <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))} aria-label="Previous page">‹</button>
              <span style={{ fontSize: "var(--text-sm)", color: "var(--gray-600)", minWidth: 56, textAlign: "center" }}>{page} / {pageCount}</span>
              <button type="button" className="btn btn-ghost btn-sm" disabled={page >= pageCount} onClick={() => setPage((p) => p + 1)} aria-label="Next page">›</button>
            </div>
          </div>
        )}
      </div>

      <Toast toast={toast} onClose={() => setToast(null)} />
    </div>
  );
}
