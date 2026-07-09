import { useEffect, useState } from "react";
import dayjs from "dayjs";
import { searchAdminBookings } from "../api/client";
import useStore from "../store/useStore";
import { useT } from "../i18n";
import { SkeletonList } from "../components/Skeleton";
import EmptyState from "../components/EmptyState";
import { IconCalendar } from "../components/icons";

const BOOKING_BADGE = {
  pending: "badge-pending",
  confirmed: "badge-confirmed",
  completed: "badge-completed",
  cancelled_by_customer: "badge-cancelled_by_customer",
  cancelled_by_business: "badge-cancelled_by_business",
  no_show: "badge-no_show",
  rescheduled: "badge-pending",
};

export default function AdminBookings() {
  const { lang } = useStore();
  const t = useT(lang);
  const PAGE_SIZE = 20;
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [q, setQ] = useState("");
  const [dateFilter, setDateFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    const id = setTimeout(() => { setQ(search.trim()); setPage(1); }, 350);
    return () => clearTimeout(id);
  }, [search]);

  const load = async () => {
    setLoading(true);
    try {
      const params = { page, page_size: PAGE_SIZE };
      if (q) params.q = q;
      if (dateFilter) params.booking_date = dateFilter;
      const res = await searchAdminBookings(params);
      setRows(res.items || []);
      setTotal(res.total || 0);
      setError(false);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [q, dateFilter, page]);

  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const rangeStart = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
  const rangeEnd = Math.min(page * PAGE_SIZE, total);

  return (
    <div className="animate-in">
      <div className="page-header">
        <div>
          <div className="eyebrow">{t("platform")}</div>
          <h1 className="page-title" style={{ marginTop: 4 }}>{t("admin_bookings")}</h1>
          <p className="page-subtitle">{t("admin_bookings_sub")}</p>
        </div>
      </div>

      <div className="card">
        <div className="row" style={{ gap: 12, marginBottom: "var(--space-4)", flexWrap: "wrap" }}>
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={t("search_bookings_ph")}
            aria-label={t("search_bookings_ph")}
            style={{ minHeight: 40, flex: "1 1 240px", minWidth: 200 }}
          />
          <input
            type="date"
            value={dateFilter}
            onChange={(e) => { setDateFilter(e.target.value); setPage(1); }}
            aria-label={t("date")}
            style={{ minHeight: 40 }}
          />
          {dateFilter && (
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => { setDateFilter(""); setPage(1); }}>
              {t("clear")}
            </button>
          )}
        </div>

        {loading ? (
          <SkeletonList count={5} />
        ) : error ? (
          <EmptyState title={t("error")} subtitle={t("try_again")} />
        ) : rows.length === 0 ? (
          <EmptyState icon={<IconCalendar size={24} />} title={t("no_data")} />
        ) : (
          <div className="table-scroll">
            <table className="table">
              <thead>
                <tr>
                  <th>{t("customer")}</th>
                  <th>{t("phone")}</th>
                  <th>{t("business")}</th>
                  <th>{t("service")}</th>
                  <th>{t("date")}</th>
                  <th>{t("time")}</th>
                  <th>{t("status")}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((b) => (
                  <tr key={b.id}>
                    <td style={{ fontWeight: 700 }}>{b.customer_name || "—"}</td>
                    <td style={{ fontFamily: "monospace", fontSize: "var(--text-sm)" }}>{b.customer_phone || "—"}</td>
                    <td style={{ fontSize: "var(--text-sm)" }}>{b.business_name || `#${b.business_id}`}</td>
                    <td style={{ fontSize: "var(--text-sm)", color: "var(--gray-600)" }}>{b.service_name || "—"}</td>
                    <td style={{ fontSize: "var(--text-sm)" }}>{b.booking_date ? dayjs(b.booking_date).format("DD.MM.YYYY") : "—"}</td>
                    <td style={{ fontSize: "var(--text-sm)" }}>{b.booking_time?.slice(0, 5) || "—"}</td>
                    <td><span className={`badge ${BOOKING_BADGE[b.status] || ""}`}>{t(b.status) || b.status}</span></td>
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
    </div>
  );
}
