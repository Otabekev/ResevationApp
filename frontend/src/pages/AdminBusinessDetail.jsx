import { useEffect, useState } from "react";
import { Link, useParams, useNavigate } from "react-router-dom";
import dayjs from "dayjs";
import { getAdminBusinessDetail, updateBusinessStatus } from "../api/client";
import useStore from "../store/useStore";
import { useT } from "../i18n";
import { SkeletonList } from "../components/Skeleton";
import EmptyState from "../components/EmptyState";
import Toast from "../components/Toast";
import {
  IconArrowLeft, IconStore, IconCalendar, IconUsers, IconScissors,
  IconChart, IconCheck, IconBan, IconPhone,
} from "../components/icons";

const STATUSES = ["pending", "trial", "active", "suspended", "blocked"];
const STATUS_BADGE = {
  active: "badge-confirmed",
  trial: "badge-pending",
  pending: "badge-completed",
  suspended: "badge-no_show",
  blocked: "badge-cancelled_by_business",
};

const BOOKING_BADGE = {
  pending: "badge-pending",
  confirmed: "badge-confirmed",
  completed: "badge-completed",
  cancelled_by_customer: "badge-cancelled_by_customer",
  cancelled_by_business: "badge-cancelled_by_business",
  no_show: "badge-no_show",
};

export default function AdminBusinessDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { lang } = useStore();
  const t = useT(lang);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [toast, setToast] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      setData(await getAdminBusinessDetail(id));
      setError(false);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [id]);

  const setStatus = async (newStatus) => {
    try {
      await updateBusinessStatus(id, newStatus);
      setToast({ message: t("saved"), variant: "success" });
      await load();
    } catch {
      setToast({ message: t("error"), variant: "error" });
    }
  };

  if (loading) return <SkeletonList count={6} />;

  if (error || !data) {
    return (
      <div className="animate-in">
        <div className="page-header">
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => navigate(-1)}>
            <IconArrowLeft size={15} /> {t("back")}
          </button>
        </div>
        <div className="card"><EmptyState title={t("error")} subtitle={t("try_again")} /></div>
      </div>
    );
  }

  const c = data.counts;
  const STAT_CARDS = [
    { icon: <IconCalendar size={18} />, value: c.bookings_total, label: t("bookings_total"), iconCls: "blue" },
    { icon: <IconCalendar size={18} />, value: c.bookings_today, label: t("today") },
    { icon: <IconChart size={18} />, value: c.bookings_month, label: t("this_month") },
    { icon: <IconCheck size={18} />, value: c.bookings_confirmed, label: t("confirmed_completed"), color: "var(--success)" },
    { icon: <IconScissors size={18} />, value: c.services, label: t("services") },
    { icon: <IconUsers size={18} />, value: c.staff, label: t("staff") },
  ];

  return (
    <div className="animate-in">
      <div className="page-header" style={{ alignItems: "flex-start" }}>
        <div className="grow">
          <Link to="/admin/businesses" className="btn btn-ghost btn-sm" style={{ marginBottom: 8 }}>
            <IconArrowLeft size={15} /> {t("businesses")}
          </Link>
          <div className="row" style={{ alignItems: "center", gap: 10, flexWrap: "wrap" }}>
            <h1 className="page-title" style={{ margin: 0 }}>{data.name}</h1>
            <span className={`badge ${STATUS_BADGE[data.status] || ""}`}>{t(`status_${data.status}`)}</span>
          </div>
          <p className="page-subtitle">
            {data.district || "—"}{data.region ? `, ${data.region}` : ""}
            {data.address ? ` · ${data.address}` : ""}
            {data.latitude != null && data.longitude != null
              ? ` · 📍 ${Number(data.latitude).toFixed(5)}, ${Number(data.longitude).toFixed(5)}`
              : " · 📍 —"}
          </p>
        </div>
      </div>

      {/* Status actions */}
      <div className="card">
        <h3 className="card-title" style={{ marginBottom: "var(--space-3)" }}>{t("change_status")}</h3>
        <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
          {data.status === "pending" && (
            <button type="button" className="btn btn-primary" onClick={() => setStatus("active")}>
              <IconCheck size={15} /> {t("approve")}
            </button>
          )}
          {data.status === "active" && (
            <button type="button" className="btn btn-secondary" onClick={() => setStatus("suspended")}>
              <IconBan size={15} /> {t("suspend")}
            </button>
          )}
          {data.status === "suspended" && (
            <button type="button" className="btn btn-primary" onClick={() => setStatus("active")}>
              <IconCheck size={15} /> {t("reactivate")}
            </button>
          )}
          <select
            aria-label={t("status")}
            value={data.status}
            onChange={(e) => setStatus(e.target.value)}
            style={{ minHeight: 38, padding: "6px 28px 6px 10px", fontSize: "var(--text-sm)" }}
          >
            {STATUSES.map((s) => (
              <option key={s} value={s}>{t(`status_${s}`)}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Stats */}
      <div className="stats-grid stagger">
        {STAT_CARDS.map((card, i) => (
          <div className="stat-card" key={i}>
            <div className="stat-head">
              <span className={`stat-icon${card.iconCls ? ` ${card.iconCls}` : ""}`}>{card.icon}</span>
            </div>
            <div className="stat-value" style={card.color ? { color: card.color } : undefined}>{card.value}</div>
            <div className="stat-label">{card.label}</div>
          </div>
        ))}
      </div>

      {/* Owner */}
      <div className="card">
        <h3 className="card-title" style={{ marginBottom: "var(--space-3)" }}>{t("owner")}</h3>
        {data.owner ? (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 12 }}>
            <div>
              <div style={{ fontSize: "var(--text-xs)", color: "var(--gray-500)" }}>{t("name")}</div>
              <div style={{ fontWeight: 700 }}>{data.owner.name || "—"}</div>
            </div>
            <div>
              <div style={{ fontSize: "var(--text-xs)", color: "var(--gray-500)" }}>{t("username")}</div>
              <div style={{ fontWeight: 700 }}>{data.owner.username ? `@${data.owner.username}` : "—"}</div>
            </div>
            <div>
              <div style={{ fontSize: "var(--text-xs)", color: "var(--gray-500)" }}>Telegram ID</div>
              <div style={{ fontWeight: 700, fontFamily: "monospace", fontSize: "var(--text-sm)" }}>
                {data.owner.telegram_id || "—"}
              </div>
            </div>
            <div>
              <div style={{ fontSize: "var(--text-xs)", color: "var(--gray-500)" }}>{t("role")}</div>
              <div style={{ fontWeight: 700 }}>{t(`role_${data.owner.role}`) || data.owner.role}</div>
            </div>
          </div>
        ) : (
          <div style={{ color: "var(--gray-500)" }}>{t("no_owner")}</div>
        )}
        {data.phone && (
          <div className="row" style={{ marginTop: 12, gap: 6, color: "var(--gray-600)", fontSize: "var(--text-sm)" }}>
            <IconPhone size={14} /> {data.phone}
          </div>
        )}
      </div>

      {/* Recent bookings */}
      <div className="card">
        <h3 className="card-title" style={{ marginBottom: "var(--space-3)" }}>{t("recent_bookings")}</h3>
        {data.recent_bookings.length === 0 ? (
          <EmptyState icon={<IconCalendar size={24} />} title={t("no_data")} />
        ) : (
          <div className="table-scroll">
            <table className="table">
              <thead>
                <tr>
                  <th>{t("customer")}</th>
                  <th>{t("service")}</th>
                  <th>{t("date")}</th>
                  <th>{t("time")}</th>
                  <th>{t("status")}</th>
                </tr>
              </thead>
              <tbody>
                {data.recent_bookings.map((b) => (
                  <tr key={b.id}>
                    <td style={{ fontWeight: 700 }}>{b.customer_name}</td>
                    <td style={{ fontSize: "var(--text-sm)", color: "var(--gray-600)" }}>{b.service_name || "—"}</td>
                    <td style={{ fontSize: "var(--text-sm)" }}>{b.booking_date ? dayjs(b.booking_date).format("DD.MM.YYYY") : "—"}</td>
                    <td style={{ fontSize: "var(--text-sm)" }}>{b.booking_time?.slice(0, 5) || "—"}</td>
                    <td>
                      <span className={`badge ${BOOKING_BADGE[b.status] || ""}`}>{t(b.status) || b.status}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Meta */}
      <div className="card" style={{ background: "var(--gray-50)" }}>
        <div className="row" style={{ gap: 16, flexWrap: "wrap", fontSize: "var(--text-xs)", color: "var(--gray-500)" }}>
          <div><strong>{t("created_at")}:</strong> {data.created_at ? dayjs(data.created_at).format("DD.MM.YYYY HH:mm") : "—"}</div>
          {data.trial_ends_at && (
            <div><strong>{t("trial_ends_at")}:</strong> {dayjs(data.trial_ends_at).format("DD.MM.YYYY")}</div>
          )}
          <div><strong>{t("online_booking")}:</strong> {data.is_online_booking_enabled ? t("enabled") : t("disabled")}</div>
        </div>
      </div>

      <Toast toast={toast} onClose={() => setToast(null)} />
    </div>
  );
}
