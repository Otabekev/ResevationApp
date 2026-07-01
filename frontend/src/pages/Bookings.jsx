import { useEffect, useMemo, useState } from "react";
import {
  getBookings, updateBookingStatus, cancelBooking,
  createManualBooking, getServices, getStaff, getAvailability,
} from "../api/client";
import useStore from "../store/useStore";
import { useT } from "../i18n";
import { SkeletonList } from "../components/Skeleton";
import EmptyState from "../components/EmptyState";
import Modal from "../components/Modal";
import Toast from "../components/Toast";
import dayjs from "dayjs";
import {
  IconPlus, IconCheck, IconBan, IconX, IconCalendar, IconPhone, IconNote, IconUsers,
} from "../components/icons";

const STATUS_BADGE = {
  pending: "badge-pending", confirmed: "badge-confirmed", completed: "badge-completed",
  cancelled_by_customer: "badge-cancelled_by_customer", cancelled_by_business: "badge-cancelled_by_business",
  no_show: "badge-no_show", rescheduled: "badge-rescheduled",
};
const FILTERS = ["", "pending", "confirmed", "completed", "no_show"];
const MUTED = ["cancelled_by_customer", "cancelled_by_business", "no_show", "completed"];

const EMPTY_FORM = {
  service_id: "", staff_id: "", booking_date: dayjs().format("YYYY-MM-DD"),
  start_time: "", customer_name: "", customer_phone: "", notes: "",
};

function DateStrip({ value, onChange, t }) {
  const days = useMemo(
    () => Array.from({ length: 14 }, (_, i) => dayjs().add(i, "day")),
    []
  );
  return (
    <div className="date-strip">
      {days.map((d) => {
        const iso = d.format("YYYY-MM-DD");
        const isToday = iso === dayjs().format("YYYY-MM-DD");
        return (
          <button
            key={iso}
            type="button"
            className={`date-chip${value === iso ? " on" : ""}${isToday ? " today" : ""}`}
            onClick={() => onChange(iso)}
          >
            <span className="dow">{isToday ? t("today") : t(`wd_${d.day()}`)}</span>
            <span className="dom">{d.format("D")}</span>
          </button>
        );
      })}
      <input
        type="date"
        value={value}
        onChange={(e) => e.target.value && onChange(e.target.value)}
        aria-label={t("date")}
        style={{ width: 150, minHeight: "auto", alignSelf: "stretch", flexShrink: 0 }}
      />
    </div>
  );
}

export default function Bookings() {
  const { lang, activeBusiness } = useStore();
  const t = useT(lang);
  const [bookings, setBookings] = useState([]);
  const [date, setDate] = useState(dayjs().format("YYYY-MM-DD"));
  const [statusFilter, setStatusFilter] = useState("");
  const [loading, setLoading] = useState(false);
  const [toast, setToast] = useState(null);
  const [confirmCancelId, setConfirmCancelId] = useState(null);
  const [cancelReason, setCancelReason] = useState("");

  // Manual booking modal
  const [showModal, setShowModal] = useState(false);
  const [services, setServices] = useState([]);
  const [staffList, setStaffList] = useState([]);
  const [form, setForm] = useState(EMPTY_FORM);
  const [slots, setSlots] = useState(null); // null = not loaded, [] = none
  const [slotsLoading, setSlotsLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [modalError, setModalError] = useState("");

  useEffect(() => {
    if (!activeBusiness) return;
    load();
  }, [activeBusiness, date, statusFilter]);

  useEffect(() => {
    if (!activeBusiness) return;
    getServices(activeBusiness.id).then(setServices).catch(() => {});
    getStaff(activeBusiness.id).then(setStaffList).catch(() => {});
  }, [activeBusiness]);

  // Load available slots whenever the modal's service/staff/date changes.
  useEffect(() => {
    if (!showModal || !form.service_id || !form.booking_date) {
      setSlots(null);
      return;
    }
    let alive = true;
    setSlotsLoading(true);
    getAvailability(activeBusiness.id, form.service_id, form.booking_date, form.staff_id || null)
      .then((s) => alive && setSlots(s))
      .catch(() => alive && setSlots([]))
      .finally(() => alive && setSlotsLoading(false));
    return () => { alive = false; };
  }, [showModal, form.service_id, form.staff_id, form.booking_date, activeBusiness]);

  const load = async () => {
    setLoading(true);
    try {
      const params = { booking_date: date };
      if (statusFilter) params.status = statusFilter;
      const data = await getBookings(activeBusiness.id, params);
      setBookings(data);
    } catch {
      setToast({ message: t("error"), variant: "error" });
    } finally {
      setLoading(false);
    }
  };

  const handleStatus = async (bookingId, newStatus) => {
    try {
      await updateBookingStatus(bookingId, newStatus);
      setToast({ message: t("saved"), variant: "success" });
      await load();
    } catch {
      setToast({ message: t("error"), variant: "error" });
    }
  };

  const handleCancel = async (bookingId) => {
    try {
      const res = await cancelBooking(bookingId, cancelReason || null);
      setConfirmCancelId(null);
      setCancelReason("");
      // Reassure the owner the customer actually got the message — but stay
      // honest for a walk-in with no Telegram (customer_notified === false).
      setToast({
        message: res?.customer_notified ? t("booking_cancelled_notified") : t("booking_cancelled_toast"),
        variant: "success",
      });
      await load();
    } catch {
      setToast({ message: t("error"), variant: "error" });
    }
  };

  const openModal = () => {
    setForm({ ...EMPTY_FORM, booking_date: date });
    setModalError("");
    setSlots(null);
    setShowModal(true);
  };

  const handleCreate = async (e) => {
    e.preventDefault();
    if (!form.start_time) {
      setModalError(t("pick_time_slot"));
      return;
    }
    // Phone must be a real Uzbek number so it's callable later (a tel: link) —
    // catch "asdf" here for instant feedback; the backend enforces it too.
    const digits = (form.customer_phone || "").replace(/\D/g, "");
    if (!(digits.length === 9 || (digits.length === 12 && digits.startsWith("998")))) {
      setModalError(t("invalid_phone"));
      return;
    }
    setSaving(true);
    setModalError("");
    try {
      await createManualBooking(activeBusiness.id, {
        service_id: parseInt(form.service_id),
        staff_id: form.staff_id ? parseInt(form.staff_id) : null,
        booking_date: form.booking_date,
        start_time: form.start_time + ":00",
        customer_name: form.customer_name,
        customer_phone: form.customer_phone,
        notes: form.notes || null,
      });
      setShowModal(false);
      setDate(form.booking_date);
      setToast({ message: t("booking_created"), variant: "success" });
      await load();
    } catch (err) {
      setModalError(err.response?.data?.detail || t("error"));
    } finally {
      setSaving(false);
    }
  };

  const set = (key, value) => setForm((f) => ({ ...f, [key]: value, ...(key !== "start_time" ? { start_time: "" } : {}) }));
  const svcName = (b) => b[`service_name_${lang}`] || b.service_name_uz || `#${b.service_id}`;

  if (!activeBusiness) {
    return <EmptyState icon={<IconUsers size={26} />} title={t("select_business_first")} subtitle={t("select_business_desc")} />;
  }

  return (
    <div className="animate-in">
      <div className="page-header">
        <div>
          <h1 className="page-title">{t("bookings")}</h1>
          <p className="page-subtitle">{dayjs(date).format("DD MMMM YYYY")}</p>
        </div>
        <button className="btn btn-primary" onClick={openModal}>
          <IconPlus size={17} /> {t("new_booking")}
        </button>
      </div>

      <div style={{ marginBottom: "var(--space-4)" }}>
        <DateStrip value={date} onChange={setDate} t={t} />
      </div>

      <div className="segmented" style={{ marginBottom: "var(--space-4)" }}>
        {FILTERS.map((s) => (
          <button
            key={s || "all"}
            type="button"
            className={statusFilter === s ? "on" : ""}
            onClick={() => setStatusFilter(s)}
          >
            {s === "" ? t("all_statuses") : t(s)}
          </button>
        ))}
      </div>

      {loading ? (
        <SkeletonList />
      ) : bookings.length === 0 ? (
        <div className="card">
          <EmptyState
            icon={<IconCalendar size={24} />}
            title={t("no_bookings_for_day")}
            subtitle={t("no_bookings_for_day_sub")}
            action={
              <button className="btn btn-secondary btn-sm" onClick={openModal}>
                <IconPlus size={15} /> {t("new_booking")}
              </button>
            }
          />
        </div>
      ) : (
        <div className="stack stagger" style={{ gap: "var(--space-3)" }}>
          {bookings.map((b) => {
            const active = ["pending", "confirmed"].includes(b.status);
            return (
              <div key={b.id} className={`booking-card${MUTED.includes(b.status) ? " is-muted" : ""}`}>
                <div className="booking-time">
                  <span className="t1">{b.start_time?.slice(0, 5)}</span>
                  <span className="t2">{b.end_time?.slice(0, 5)}</span>
                </div>

                <div className="booking-main">
                  <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
                    <span style={{ fontWeight: 750 }} className="ellipsis">{b.customer_name}</span>
                    <span className={`badge ${STATUS_BADGE[b.status] || ""}`}>{t(b.status) || b.status}</span>
                    {b.was_auto_assigned && <span className="chip">{t("auto_assigned")}</span>}
                  </div>
                  <div className="booking-meta" style={{ marginTop: 4 }}>
                    <span className="chip brand">{svcName(b)}</span>
                    {b.staff_name && <span className="chip">{b.staff_name}</span>}
                    <a href={`tel:${b.customer_phone}`} className="chip" style={{ color: "var(--gray-600)" }}>
                      <IconPhone size={12} /> {b.customer_phone}
                    </a>
                  </div>
                  {b.notes && (
                    <div className="booking-meta" style={{ marginTop: 6, fontStyle: "normal" }}>
                      <IconNote size={13} style={{ flexShrink: 0 }} /> <span>{b.notes}</span>
                    </div>
                  )}
                </div>

                {active && (
                  <div className="booking-actions">
                    {b.status === "pending" && (
                      <button className="btn btn-primary btn-sm" onClick={() => handleStatus(b.id, "confirmed")}>
                        <IconCheck size={15} /> {t("confirm")}
                      </button>
                    )}
                    <button className="btn btn-secondary btn-sm" onClick={() => handleStatus(b.id, "completed")}>
                      <IconCheck size={15} /> {t("completed_action")}
                    </button>
                    <button className="btn btn-secondary btn-sm" title={t("no_show")} onClick={() => handleStatus(b.id, "no_show")}>
                      <IconBan size={15} /> {t("no_show")}
                    </button>
                    {confirmCancelId === b.id ? (
                      <span className="row" style={{ gap: 6, flexWrap: "wrap" }}>
                        <select
                          className="input"
                          value={cancelReason}
                          onChange={(e) => setCancelReason(e.target.value)}
                          style={{ minHeight: 32, padding: "4px 8px", fontSize: "var(--text-sm)", width: "auto" }}
                          aria-label={t("cancel_reason_prompt")}
                        >
                          <option value="">{t("cancel_reason_prompt")}</option>
                          <option value={t("cancel_reason_staff")}>{t("cancel_reason_staff")}</option>
                          <option value={t("cancel_reason_closed")}>{t("cancel_reason_closed")}</option>
                          <option value={t("cancel_reason_customer")}>{t("cancel_reason_customer")}</option>
                          <option value={t("cancel_reason_other")}>{t("cancel_reason_other")}</option>
                        </select>
                        <button className="btn btn-danger btn-sm" onClick={() => handleCancel(b.id)}>
                          {t("yes_cancel")}
                        </button>
                        <button className="btn btn-ghost btn-sm" onClick={() => { setConfirmCancelId(null); setCancelReason(""); }}>
                          {t("keep")}
                        </button>
                      </span>
                    ) : (
                      <button
                        className="btn btn-danger-soft btn-sm"
                        title={t("cancel")}
                        onClick={() => { setConfirmCancelId(b.id); setCancelReason(""); }}
                      >
                        <IconX size={15} />
                      </button>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Manual booking modal */}
      {showModal && (
        <Modal title={t("new_booking")} onClose={() => setShowModal(false)}>
          <form onSubmit={handleCreate}>
            <div className="form-group">
              <label>{t("service")} *</label>
              <select required value={form.service_id} onChange={(e) => set("service_id", e.target.value)}>
                <option value="">{t("select_service")}</option>
                {services.filter((s) => s.is_active).map((s) => (
                  <option key={s.id} value={s.id}>
                    {s[`name_${lang}`] || s.name_uz} · {s.duration_minutes} {t("min")}
                  </option>
                ))}
              </select>
            </div>
            <div className="grid-2">
              <div className="form-group">
                <label>{t("staff_member")}</label>
                <select value={form.staff_id} onChange={(e) => set("staff_id", e.target.value)}>
                  <option value="">{t("any_available")}</option>
                  {staffList.filter((s) => s.is_active).map((s) => (
                    <option key={s.id} value={s.id}>{s.name}</option>
                  ))}
                </select>
              </div>
              <div className="form-group">
                <label>{t("date")} *</label>
                <input
                  required type="date" value={form.booking_date}
                  min={dayjs().format("YYYY-MM-DD")}
                  onChange={(e) => set("booking_date", e.target.value)}
                />
              </div>
            </div>

            {/* Live availability — the server is the source of truth */}
            <div className="form-group">
              <label>{t("time")} *</label>
              {!form.service_id ? (
                <p className="form-hint">{t("choose_service_first")}</p>
              ) : slotsLoading ? (
                <div className="skeleton" style={{ height: 44 }} />
              ) : !slots || slots.length === 0 ? (
                <p className="form-hint" style={{ color: "var(--warning)" }}>{t("no_slots_day")}</p>
              ) : (
                <div style={{ display: "flex", flexWrap: "wrap", gap: 8, maxHeight: 160, overflowY: "auto", padding: 2 }}>
                  {slots.map((s) => (
                    <button
                      key={s.start_time}
                      type="button"
                      className={`service-toggle${form.start_time === s.start_time ? " on" : ""}`}
                      onClick={() => setForm((f) => ({ ...f, start_time: s.start_time }))}
                    >
                      {s.start_time}
                    </button>
                  ))}
                </div>
              )}
            </div>

            <div className="form-group">
              <label>{t("customer")} *</label>
              <input
                required value={form.customer_name} maxLength={255}
                onChange={(e) => setForm((f) => ({ ...f, customer_name: e.target.value }))}
                placeholder={t("full_name")}
              />
            </div>
            <div className="form-group">
              <label>{t("phone")} *</label>
              <input
                required type="tel" value={form.customer_phone} maxLength={20}
                onChange={(e) => setForm((f) => ({ ...f, customer_phone: e.target.value }))}
                placeholder="+998 90 123 45 67"
              />
            </div>
            <div className="form-group">
              <label>{t("notes")}</label>
              <textarea
                rows={2} value={form.notes} maxLength={1000}
                onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))}
              />
            </div>

            {modalError && <p className="form-error" style={{ marginBottom: "var(--space-3)" }}>{modalError}</p>}

            <div className="modal-footer" style={{ marginTop: 0 }}>
              <button type="button" className="btn btn-secondary" onClick={() => setShowModal(false)}>
                {t("cancel")}
              </button>
              <button type="submit" className="btn btn-primary" disabled={saving || !form.start_time}>
                {saving ? t("loading") : t("save")}
              </button>
            </div>
          </form>
        </Modal>
      )}

      <Toast toast={toast} onClose={() => setToast(null)} />
    </div>
  );
}
