import { useEffect, useState } from "react";
import {
  getBookings, updateBookingStatus, cancelBooking,
  createManualBooking, getServices, getStaff,
} from "../api/client";
import useStore from "../store/useStore";
import { useT } from "../i18n";
import { SkeletonList } from "../components/Skeleton";
import dayjs from "dayjs";

const STATUSES = ["pending", "confirmed", "completed", "no_show", "cancelled_by_business"];
const STATUS_BADGE = {
  pending: "badge-pending", confirmed: "badge-confirmed", completed: "badge-completed",
  cancelled_by_customer: "badge-cancelled_by_customer", cancelled_by_business: "badge-cancelled_by_business",
  no_show: "badge-no_show",
};

const EMPTY_BOOKING = {
  service_id: "", staff_id: "", booking_date: dayjs().format("YYYY-MM-DD"),
  start_time: "09:00", customer_name: "", customer_phone: "", notes: "",
};

export default function Bookings() {
  const { lang, activeBusiness } = useStore();
  const t = useT(lang);
  const [bookings, setBookings] = useState([]);
  const [date, setDate] = useState(dayjs().format("YYYY-MM-DD"));
  const [statusFilter, setStatusFilter] = useState("");
  const [loading, setLoading] = useState(false);

  // Manual booking modal
  const [showModal, setShowModal] = useState(false);
  const [services, setServices] = useState([]);
  const [staffList, setStaffList] = useState([]);
  const [form, setForm] = useState(EMPTY_BOOKING);
  const [saving, setSaving] = useState(false);
  const [modalError, setModalError] = useState("");

  useEffect(() => {
    if (activeBusiness) {
      load();
      getServices(activeBusiness.id).then(setServices);
      getStaff(activeBusiness.id).then(setStaffList);
    }
  }, [activeBusiness, date, statusFilter]);

  const load = async () => {
    setLoading(true);
    try {
      const params = {};
      if (date) params.booking_date = date;
      if (statusFilter) params.status = statusFilter;
      const data = await getBookings(activeBusiness.id, params);
      setBookings(data);
    } finally {
      setLoading(false);
    }
  };

  const handleStatus = async (bookingId, newStatus) => {
    await updateBookingStatus(bookingId, newStatus);
    await load();
  };

  const openModal = () => {
    setForm({ ...EMPTY_BOOKING, booking_date: date });
    setModalError("");
    setShowModal(true);
  };

  const handleCreate = async (e) => {
    e.preventDefault();
    setSaving(true);
    setModalError("");
    try {
      await createManualBooking(activeBusiness.id, {
        service_id: parseInt(form.service_id),
        staff_id: form.staff_id ? parseInt(form.staff_id) : null,
        booking_date: form.booking_date,
        start_time: form.start_time,
        customer_name: form.customer_name,
        customer_phone: form.customer_phone,
        notes: form.notes || null,
      });
      setShowModal(false);
      await load();
    } catch (err) {
      setModalError(err.response?.data?.detail || t("error"));
    } finally {
      setSaving(false);
    }
  };

  const svc = (key, value) => setForm((f) => ({ ...f, [key]: value }));

  if (!activeBusiness) return <p style={{ padding: "var(--space-6)", color: "var(--gray-500)" }}>{t("select_business_first")}</p>;

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">{t("bookings")}</h1>
        <button className="btn btn-primary btn-sm" onClick={openModal}>
          + {t("new_booking")}
        </button>
      </div>

      {/* Filters */}
      <div style={{ display: "flex", gap: "var(--space-3)", marginBottom: "var(--space-4)", flexWrap: "wrap" }}>
        <input
          type="date" value={date}
          onChange={(e) => setDate(e.target.value)}
          style={{ width: "auto" }}
        />
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} style={{ width: "auto" }}>
          <option value="">{t("all_statuses")}</option>
          {STATUSES.map((s) => <option key={s} value={s}>{t(s) || s}</option>)}
        </select>
        <button className="btn btn-secondary btn-sm" onClick={() => setDate(dayjs().format("YYYY-MM-DD"))}>
          {t("today")}
        </button>
      </div>

      {loading ? (
        <SkeletonList />
      ) : bookings.length === 0 ? (
        <div className="card empty-state">{t("no_data")}</div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
          {bookings.map((b) => (
            <div key={b.id} className="card">
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                <div>
                  <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)", marginBottom: "var(--space-1)" }}>
                    <span style={{ fontWeight: 700, fontSize: "var(--text-md)" }}>{b.start_time?.slice(0, 5)}</span>
                    <span style={{ fontSize: "var(--text-sm)", color: "var(--gray-500)" }}>→ {b.end_time?.slice(0, 5)}</span>
                    <span className={`badge ${STATUS_BADGE[b.status] || ""}`}>{t(b.status) || b.status}</span>
                    {b.was_auto_assigned && <span style={{ fontSize: "var(--text-xs)", color: "var(--gray-400)" }}>{t("auto_assigned")}</span>}
                  </div>
                  <div style={{ fontWeight: 600 }}>{b.customer_name}</div>
                  <div style={{ fontSize: "var(--text-sm)", color: "var(--gray-500)" }}>{b.customer_phone}</div>
                  {b.notes && <div style={{ fontSize: "var(--text-sm)", color: "var(--gray-500)", marginTop: "var(--space-1)" }}>💬 {b.notes}</div>}
                </div>
                <div style={{ display: "flex", gap: "var(--space-2)", flexWrap: "wrap", justifyContent: "flex-end" }}>
                  {b.status === "pending" && (
                    <button className="btn btn-primary btn-sm" onClick={() => handleStatus(b.id, "confirmed")}>
                      ✅ {t("confirm")}
                    </button>
                  )}
                  {["pending", "confirmed"].includes(b.status) && (
                    <>
                      <button className="btn btn-secondary btn-sm" onClick={() => handleStatus(b.id, "completed")} title={t("completed")}>
                        ✔️
                      </button>
                      <button className="btn btn-secondary btn-sm" onClick={() => handleStatus(b.id, "no_show")} title={t("no_show")}>
                        🚫
                      </button>
                      <button className="btn btn-danger btn-sm" onClick={() => handleStatus(b.id, "cancelled_by_business")} title={t("cancelled_by_business")}>
                        ✕
                      </button>
                    </>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Manual booking modal */}
      {showModal && (
        <div className="modal-overlay" onClick={() => setShowModal(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 480 }}>
            <div className="modal-header">
              <h3 style={{ margin: 0 }}>{t("new_booking")}</h3>
              <button className="modal-close" onClick={() => setShowModal(false)}>×</button>
            </div>
            <form onSubmit={handleCreate}>
              <div className="form-group">
                <label>{t("service")} *</label>
                <select required value={form.service_id} onChange={(e) => svc("service_id", e.target.value)}>
                  <option value="">{t("select_service")}</option>
                  {services.filter((s) => s.is_active).map((s) => (
                    <option key={s.id} value={s.id}>
                      {s[`name_${lang}`] || s.name_uz} ({s.duration_minutes} {t("min")})
                    </option>
                  ))}
                </select>
              </div>
              <div className="form-group">
                <label>{t("staff_member")}</label>
                <select value={form.staff_id} onChange={(e) => svc("staff_id", e.target.value)}>
                  <option value="">{t("any_available")}</option>
                  {staffList.filter((s) => s.is_active).map((s) => (
                    <option key={s.id} value={s.id}>{s.name}</option>
                  ))}
                </select>
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--space-3)" }}>
                <div className="form-group">
                  <label>{t("date")} *</label>
                  <input required type="date" value={form.booking_date}
                    onChange={(e) => svc("booking_date", e.target.value)} />
                </div>
                <div className="form-group">
                  <label>{t("time")} *</label>
                  <input required type="time" value={form.start_time}
                    onChange={(e) => svc("start_time", e.target.value)} />
                </div>
              </div>
              <div className="form-group">
                <label>{t("customer")} *</label>
                <input required value={form.customer_name}
                  onChange={(e) => svc("customer_name", e.target.value)}
                  placeholder={t("full_name")} />
              </div>
              <div className="form-group">
                <label>{t("phone")} *</label>
                <input required value={form.customer_phone}
                  onChange={(e) => svc("customer_phone", e.target.value)}
                  placeholder={t("phone_placeholder")} />
              </div>
              <div className="form-group">
                <label>{t("notes")}</label>
                <textarea rows={2} value={form.notes}
                  onChange={(e) => svc("notes", e.target.value)} />
              </div>
              {modalError && <p style={{ color: "var(--danger)", fontSize: "var(--text-sm)", marginBottom: "var(--space-3)" }}>{modalError}</p>}
              <div style={{ display: "flex", gap: "var(--space-2)", justifyContent: "flex-end" }}>
                <button type="button" className="btn btn-secondary" onClick={() => setShowModal(false)}>
                  {t("cancel")}
                </button>
                <button type="submit" className="btn btn-primary" disabled={saving}>
                  {saving ? t("loading") : t("save")}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
