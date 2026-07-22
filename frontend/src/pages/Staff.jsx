import { useEffect, useState } from "react";
import {
  getStaff, createStaff, updateStaff, deleteStaff, getServices, setStaffServices, createStaffInvite,
  getStaffWorkingHours, setStaffWorkingHours, clearStaffWorkingHours, addSelfProvider,
} from "../api/client";
import useStore from "../store/useStore";
import { useT } from "../i18n";
import { SkeletonList } from "../components/Skeleton";
import EmptyState from "../components/EmptyState";
import Modal from "../components/Modal";
import Toast from "../components/Toast";
import {
  IconPlus, IconUsers, IconLink, IconCopy, IconEdit, IconClock,
  IconTelegram, IconCheck, IconRefresh, IconTrash,
} from "../components/icons";

const EMPTY_FORM = { name: "", phone: "", bio: "", role: "staff", can_set_own_hours: false, is_active: true, can_manage: false, is_provider: true };

const DEFAULT_HOURS = Array.from({ length: 7 }, (_, i) => ({
  day_of_week: i, start_time: "09:00", end_time: "18:00", is_day_off: i === 6,
}));

function initials(name = "") {
  return name.split(" ").filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join("") || "?";
}

export default function Staff() {
  const { lang, activeBusiness } = useStore();
  const t = useT(lang);
  const [staffList, setStaffList] = useState([]);
  const [services, setServices] = useState([]);
  const [showModal, setShowModal] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [invite, setInvite] = useState(null); // { staff, data }
  const [copied, setCopied] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const [toast, setToast] = useState(null);

  // Per-staff hours editor
  const [hoursFor, setHoursFor] = useState(null); // staff object
  const [hours, setHours] = useState(DEFAULT_HOURS);
  const [hoursCustom, setHoursCustom] = useState(false);
  const [hoursSaving, setHoursSaving] = useState(false);

  useEffect(() => {
    if (activeBusiness) load();
  }, [activeBusiness]);

  const load = async () => {
    setIsLoading(true);
    setLoadError(false);
    try {
      const [s, svcs] = await Promise.all([
        getStaff(activeBusiness.id),
        getServices(activeBusiness.id),
      ]);
      setStaffList(s);
      setServices(svcs.filter((x) => x.is_active));
    } catch {
      setLoadError(true);
    } finally {
      setIsLoading(false);
    }
  };

  const openNew = () => { setForm(EMPTY_FORM); setEditing(null); setShowModal(true); };
  const openEdit = (s) => {
    setForm({ name: s.name, phone: s.phone || "", bio: s.bio || "", role: s.role, can_set_own_hours: s.can_set_own_hours, is_active: s.is_active, can_manage: s.can_manage, is_provider: s.is_provider });
    setEditing(s.id);
    setShowModal(true);
  };

  // Owner adds a bookable provider profile for themselves (auto-linked, no invite).
  const handleAddSelf = async () => {
    try {
      await addSelfProvider(activeBusiness.id, {});
      await load();
      setToast({ message: t("saved"), variant: "success" });
    } catch (e) {
      setToast({ message: e.response?.data?.detail || t("error"), variant: "error" });
    }
  };

  const handleSave = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      if (editing) {
        await updateStaff(activeBusiness.id, editing, form);
      } else {
        await createStaff(activeBusiness.id, { ...form, service_ids: [] });
      }
      await load();
      setShowModal(false);
      setToast({ message: t("saved"), variant: "success" });
    } catch {
      setToast({ message: t("error"), variant: "error" });
    } finally {
      setSaving(false);
    }
  };

  const handleToggleService = async (staffId, serviceId, currentIds) => {
    const newIds = currentIds.includes(serviceId)
      ? currentIds.filter((id) => id !== serviceId)
      : [...currentIds, serviceId];
    // Optimistic: reflect the chip change immediately, roll back if the server rejects.
    setStaffList((prev) => prev.map((s) => (s.id === staffId ? { ...s, service_ids: newIds } : s)));
    try {
      await setStaffServices(activeBusiness.id, staffId, newIds);
    } catch {
      setStaffList((prev) => prev.map((s) => (s.id === staffId ? { ...s, service_ids: currentIds } : s)));
      setToast({ message: t("error"), variant: "error" });
    }
  };

  const handleDelete = async (staff) => {
    // Two-step by design: the card only shows Delete once the staff is stopped,
    // and the confirm prompts by name so a mis-tap can't quietly wipe someone.
    if (!window.confirm(t("staff_delete_confirm", { name: staff.name }))) return;
    try {
      await deleteStaff(activeBusiness.id, staff.id);
      await load();
      setToast({ message: t("staff_deleted"), variant: "success" });
    } catch (e) {
      setToast({ message: e.response?.data?.detail || t("error"), variant: "error" });
    }
  };

  const handleInvite = async (staff) => {
    try {
      const data = await createStaffInvite(activeBusiness.id, staff.id);
      setInvite({ staff, data });
      setCopied(false);
    } catch {
      setToast({ message: t("error"), variant: "error" });
    }
  };

  const copyInvite = async () => {
    try {
      await navigator.clipboard.writeText(invite.data.invite_url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setToast({ message: t("error"), variant: "error" });
    }
  };

  const openHours = async (staff) => {
    setHoursFor(staff);
    try {
      const rows = await getStaffWorkingHours(activeBusiness.id, staff.id);
      if (rows.length > 0) {
        setHoursCustom(true);
        setHours(DEFAULT_HOURS.map((def) => {
          const ex = rows.find((r) => r.day_of_week === def.day_of_week);
          return ex
            ? { day_of_week: ex.day_of_week, start_time: ex.start_time.slice(0, 5), end_time: ex.end_time.slice(0, 5), is_day_off: ex.is_day_off }
            : { ...def, is_day_off: true };
        }));
      } else {
        setHoursCustom(false);
        setHours(DEFAULT_HOURS);
      }
    } catch {
      setHoursFor(null);
      setToast({ message: t("error"), variant: "error" });
    }
  };

  const saveHours = async () => {
    setHoursSaving(true);
    try {
      if (hoursCustom) {
        await setStaffWorkingHours(activeBusiness.id, hoursFor.id, hours);
      } else {
        await clearStaffWorkingHours(activeBusiness.id, hoursFor.id);
      }
      setHoursFor(null);
      setToast({ message: t("saved"), variant: "success" });
    } catch {
      setToast({ message: t("error"), variant: "error" });
    } finally {
      setHoursSaving(false);
    }
  };

  if (!activeBusiness) {
    return <EmptyState icon={<IconUsers size={26} />} title={t("select_business_first")} subtitle={t("select_business_desc")} />;
  }

  const hasOwnerProvider = staffList.some((s) => s.is_owner);
  // Pin the owner's own provider profile to the top of the list.
  const orderedStaff = [...staffList].sort((a, b) => (b.is_owner === true) - (a.is_owner === true));

  return (
    <div className="animate-in">
      <div className="page-header">
        <div>
          <h1 className="page-title">{t("staff")}</h1>
          <p className="page-subtitle">{t("staff_subtitle")}</p>
        </div>
        <div className="row" style={{ gap: "var(--space-2)", flexWrap: "wrap" }}>
          {!hasOwnerProvider && (
            <button className="btn btn-secondary" onClick={handleAddSelf}>
              <IconPlus size={17} /> {t("add_myself_provider")}
            </button>
          )}
          <button className="btn btn-primary" onClick={openNew}>
            <IconPlus size={17} /> {t("new_staff")}
          </button>
        </div>
      </div>

      {isLoading ? (
        <SkeletonList count={4} />
      ) : loadError ? (
        <div className="card"><EmptyState title={t("error")} subtitle={t("try_again")} /></div>
      ) : staffList.length === 0 ? (
        <div className="card">
          <EmptyState
            icon={<IconUsers size={24} />}
            title={t("no_staff_title")}
            subtitle={t("no_staff_desc")}
            action={
              <button className="btn btn-primary btn-sm" onClick={openNew}>
                <IconPlus size={15} /> {t("new_staff")}
              </button>
            }
          />
        </div>
      ) : (
        <div className="stack stagger" style={{ gap: "var(--space-3)" }}>
          {orderedStaff.map((s) => (
            <div key={s.id} className="card" style={{ opacity: s.is_active ? 1 : 0.6 }}>
              <div className="row" style={{ alignItems: "flex-start", gap: "var(--space-3)" }}>
                <span className="avatar avatar-lg" aria-hidden>{initials(s.name)}</span>
                <div className="grow">
                  <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
                    <span style={{ fontWeight: 750, fontSize: "var(--text-md)" }}>{s.name}</span>
                    {s.is_owner && <span className="chip brand"><IconCheck size={12} /> {t("you_provider")}</span>}
                    {s.can_manage && !s.is_owner && <span className="chip honey">{t("role_secretary")}</span>}
                    {!s.is_active && <span className="chip">{t("inactive")}</span>}
                    {!s.is_owner && (s.user_id ? (
                      <span className="chip brand"><IconCheck size={12} /> {t("staff_joined")}</span>
                    ) : (
                      <span className="chip">{t("staff_not_joined")}</span>
                    ))}
                  </div>
                  {s.phone && <div style={{ fontSize: "var(--text-sm)", color: "var(--gray-500)", marginTop: 2 }}>{s.phone}</div>}
                </div>
                <div className="row" style={{ gap: 8, flexShrink: 0 }}>
                  <button className="btn btn-secondary btn-sm btn-icon" title={t("working_hours")} aria-label={t("working_hours")} onClick={() => openHours(s)}>
                    <IconClock size={16} />
                  </button>
                  {!s.user_id && (
                    <button className="btn btn-secondary btn-sm btn-icon" title={t("invite_link")} aria-label={t("invite_link")} onClick={() => handleInvite(s)}>
                      <IconLink size={16} />
                    </button>
                  )}
                  <button className="btn btn-secondary btn-sm btn-icon" title={t("edit")} aria-label={t("edit")} onClick={() => openEdit(s)}>
                    <IconEdit size={16} />
                  </button>
                  {/* Delete only appears once the staff is stopped — deactivate is
                      the reversible cleanup, delete is the final one. Owners can't
                      delete themselves as a provider. */}
                  {!s.is_active && !s.is_owner && (
                    <button
                      className="btn btn-sm btn-icon"
                      title={t("delete")}
                      aria-label={t("delete")}
                      onClick={() => handleDelete(s)}
                      style={{ color: "var(--danger)", borderColor: "var(--danger)" }}
                    >
                      <IconTrash size={16} />
                    </button>
                  )}
                </div>
              </div>

              <div style={{ marginTop: "var(--space-3)" }}>
                <div className="form-hint" style={{ marginBottom: 6 }}>{t("staff_services_hint")}</div>
                <div className="row" style={{ flexWrap: "wrap", gap: 8 }}>
                  {services.length === 0 && <span className="form-hint">{t("no_services_title")}</span>}
                  {services.map((svc) => {
                    const assigned = (s.service_ids || []).includes(svc.id);
                    return (
                      <button
                        key={svc.id}
                        type="button"
                        className={`service-toggle${assigned ? " on" : ""}`}
                        onClick={() => handleToggleService(s.id, svc.id, s.service_ids || [])}
                      >
                        {assigned && <IconCheck size={13} />}
                        {svc[`name_${lang}`] || svc.name_uz}
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Add / edit staff */}
      {showModal && (
        <Modal title={editing ? t("edit_staff") : t("new_staff")} onClose={() => setShowModal(false)}>
          <form onSubmit={handleSave}>
            <div className="form-group">
              <label>{t("full_name")} *</label>
              <input required maxLength={255} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </div>
            <div className="form-group">
              <label>{t("phone")}</label>
              <input type="tel" maxLength={20} value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} placeholder="+998 90 123 45 67" />
            </div>
            {/* Secretary = a desk-manager who can run the dashboard (bookings,
                schedules, all doctors) but isn't bookable as a provider. */}
            <div className="form-group row" style={{ justifyContent: "space-between" }}>
              <div>
                <div style={{ fontWeight: 650, fontSize: "var(--text-sm)" }}>{t("staff_is_secretary")}</div>
                <div className="form-hint" style={{ marginTop: 2 }}>{t("staff_is_secretary_hint")}</div>
              </div>
              <label className="toggle">
                <input
                  type="checkbox"
                  checked={form.can_manage}
                  aria-label={t("staff_is_secretary")}
                  onChange={(e) => setForm({
                    ...form,
                    can_manage: e.target.checked,
                    is_provider: !e.target.checked,
                    role: e.target.checked ? "manager" : "staff",
                  })}
                />
                <span className="toggle-slider"></span>
              </label>
            </div>
            <div className="form-group row" style={{ justifyContent: "space-between" }}>
              <div>
                <div style={{ fontWeight: 650, fontSize: "var(--text-sm)" }}>{t("can_set_own_hours")}</div>
                <div className="form-hint" style={{ marginTop: 2 }}>{t("can_set_own_hours_hint")}</div>
              </div>
              <label className="toggle">
                <input
                  type="checkbox"
                  checked={form.can_set_own_hours}
                  aria-label={t("can_set_own_hours")}
                  onChange={(e) => setForm({ ...form, can_set_own_hours: e.target.checked })}
                />
                <span className="toggle-slider"></span>
              </label>
            </div>
            {editing && (
              <div className="form-group row" style={{ justifyContent: "space-between" }}>
                <div style={{ fontWeight: 650, fontSize: "var(--text-sm)" }}>{t("is_active")}</div>
                <label className="toggle">
                  <input
                    type="checkbox"
                    checked={form.is_active}
                    aria-label={t("is_active")}
                    onChange={(e) => setForm({ ...form, is_active: e.target.checked })}
                  />
                  <span className="toggle-slider"></span>
                </label>
              </div>
            )}
            <button type="submit" className="btn btn-primary btn-full" disabled={saving}>
              {saving ? t("loading") : t("save")}
            </button>
          </form>
        </Modal>
      )}

      {/* Invite modal */}
      {invite && (
        <Modal title={t("invite_link")} onClose={() => setInvite(null)}>
          <p style={{ fontSize: "var(--text-sm)", color: "var(--gray-600)", marginBottom: "var(--space-4)" }}>
            {t("invite_explainer", { name: invite.staff.name })}
          </p>
          <div
            className="card-tight"
            style={{
              background: "var(--gray-50)", border: "1px dashed var(--gray-300)",
              borderRadius: "var(--radius-sm)", fontSize: "var(--text-sm)",
              wordBreak: "break-all", marginBottom: "var(--space-4)", fontWeight: 600,
              padding: "var(--space-3)",
            }}
          >
            {invite.data.invite_url}
          </div>
          <div className="grid-2">
            <button className="btn btn-secondary" onClick={copyInvite}>
              {copied ? <IconCheck size={16} /> : <IconCopy size={16} />}
              {copied ? t("copied") : t("copy")}
            </button>
            <a
              className="btn btn-primary"
              href={`https://t.me/share/url?url=${encodeURIComponent(invite.data.invite_url)}`}
              target="_blank" rel="noopener noreferrer"
            >
              <IconTelegram size={16} /> {t("share_telegram")}
            </a>
          </div>
          <p className="form-hint" style={{ marginTop: "var(--space-3)" }}>{t("invite_expires_7d")}</p>
        </Modal>
      )}

      {/* Per-staff hours */}
      {hoursFor && (
        <Modal title={hoursFor.is_owner ? t("my_working_hours") : `${t("working_hours")} — ${hoursFor.name}`} onClose={() => setHoursFor(null)}>
          <div className="form-group row" style={{ justifyContent: "space-between" }}>
            <div>
              <div style={{ fontWeight: 650, fontSize: "var(--text-sm)" }}>{t("custom_hours")}</div>
              <div className="form-hint" style={{ marginTop: 2 }}>{t("custom_hours_hint")}</div>
            </div>
            <label className="toggle">
              <input
                type="checkbox"
                checked={hoursCustom}
                aria-label={t("custom_hours")}
                onChange={(e) => setHoursCustom(e.target.checked)}
              />
              <span className="toggle-slider"></span>
            </label>
          </div>

          {hoursCustom && (
            <div className="stack" style={{ gap: 10, marginBottom: "var(--space-4)" }}>
              {hours.map((h, idx) => (
                <div key={h.day_of_week} className="row" style={{ gap: 10 }}>
                  <span style={{ width: 34, fontWeight: 700, fontSize: "var(--text-sm)", flexShrink: 0 }}>
                    {t(`wdm_${h.day_of_week}`)}
                  </span>
                  <label className="toggle" style={{ transform: "scale(.92)" }}>
                    <input
                      type="checkbox"
                      checked={!h.is_day_off}
                      aria-label={t("day_off")}
                      onChange={(e) =>
                        setHours((prev) => prev.map((x, i) => (i === idx ? { ...x, is_day_off: !e.target.checked } : x)))
                      }
                    />
                    <span className="toggle-slider"></span>
                  </label>
                  {!h.is_day_off ? (
                    <>
                      <input
                        type="time" value={h.start_time}
                        onChange={(e) => setHours((prev) => prev.map((x, i) => (i === idx ? { ...x, start_time: e.target.value } : x)))}
                        style={{ minHeight: 38, padding: "6px 8px", width: "auto", flex: 1 }}
                      />
                      <span style={{ color: "var(--gray-400)" }}>–</span>
                      <input
                        type="time" value={h.end_time}
                        onChange={(e) => setHours((prev) => prev.map((x, i) => (i === idx ? { ...x, end_time: e.target.value } : x)))}
                        style={{ minHeight: 38, padding: "6px 8px", width: "auto", flex: 1 }}
                      />
                    </>
                  ) : (
                    <span className="form-hint grow">{t("day_off")}</span>
                  )}
                </div>
              ))}
            </div>
          )}

          {!hoursCustom && (
            <p className="form-hint" style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: "var(--space-4)" }}>
              <IconRefresh size={14} /> {t("uses_business_hours")}
            </p>
          )}

          <button className="btn btn-primary btn-full" onClick={saveHours} disabled={hoursSaving}>
            {hoursSaving ? t("loading") : t("save")}
          </button>
        </Modal>
      )}

      <Toast toast={toast} onClose={() => setToast(null)} />
    </div>
  );
}
