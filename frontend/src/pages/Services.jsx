import { useEffect, useState } from "react";
import { getServices, createService, updateService, updateBusiness } from "../api/client";
import useStore from "../store/useStore";
import { useT } from "../i18n";
import { SkeletonList } from "../components/Skeleton";
import EmptyState from "../components/EmptyState";
import Modal from "../components/Modal";
import Toast from "../components/Toast";
import { IconPlus, IconScissors, IconClock, IconEdit, IconCheck } from "../components/icons";

const EMPTY_FORM = {
  name_uz: "", name_ru: "", name_en: "",
  description_uz: "", description_ru: "", description_en: "",
  duration_minutes: 30, buffer_before_minutes: 0, buffer_after_minutes: 0,
  price: "", currency: "UZS",
  requires_confirmation: false, is_active: true, sort_order: 0,
  online_bookable: true, max_per_day: "",
};

function fmtPrice(price, t) {
  if (price === null || price === undefined || price === "") return t("free");
  return `${parseInt(price, 10).toLocaleString()} ${t("uzs")}`;
}

export default function Services() {
  const { lang, activeBusiness, setActiveBusiness } = useStore();
  const t = useT(lang);
  const [services, setServices] = useState([]);
  const [multiOn, setMultiOn] = useState(false);
  const [showModal, setShowModal] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState(null);
  const [showDescriptions, setShowDescriptions] = useState(false);

  useEffect(() => {
    if (activeBusiness) {
      load();
      setMultiOn(Boolean(activeBusiness.allow_multi_service));
    }
  }, [activeBusiness]);

  const load = async () => {
    setLoading(true);
    try {
      const data = await getServices(activeBusiness.id);
      setServices(data);
    } catch {
      setToast({ message: t("error"), variant: "error" });
    } finally {
      setLoading(false);
    }
  };

  const openNew = () => {
    setForm(EMPTY_FORM);
    setEditing(null);
    setSaveError("");
    setShowDescriptions(false);
    setShowModal(true);
  };

  const openEdit = (svc) => {
    setForm({
      ...EMPTY_FORM,
      ...svc,
      price: svc.price ?? "",
      max_per_day: svc.max_per_day ?? "",
      online_bookable: svc.online_bookable ?? true,
      description_uz: svc.description_uz || "",
      description_ru: svc.description_ru || "",
      description_en: svc.description_en || "",
    });
    setEditing(svc.id);
    setSaveError("");
    setShowDescriptions(Boolean(svc.description_uz || svc.description_ru || svc.description_en));
    setShowModal(true);
  };

  const handleSave = async (e) => {
    e.preventDefault();
    setSaving(true);
    setSaveError("");
    try {
      const payload = {
        ...form,
        price: form.price === "" ? null : parseFloat(form.price),
        max_per_day: form.max_per_day === "" ? null : parseInt(form.max_per_day, 10),
        description_uz: form.description_uz || null,
        description_ru: form.description_ru || null,
        description_en: form.description_en || null,
      };
      if (editing) {
        await updateService(activeBusiness.id, editing, payload);
      } else {
        await createService(activeBusiness.id, payload);
      }
      await load();
      setShowModal(false);
      setToast({ message: t("saved"), variant: "success" });
    } catch (err) {
      setSaveError(err.response?.data?.detail?.[0]?.msg || t("service_save_error"));
    } finally {
      setSaving(false);
    }
  };

  const handleToggle = async (svc) => {
    const next = !svc.is_active;
    // Optimistic: flip the toggle immediately, then reconcile with the server —
    // roll back and warn only if it rejects. Feels instant despite backend latency.
    setServices((prev) => prev.map((s) => (s.id === svc.id ? { ...s, is_active: next } : s)));
    try {
      await updateService(activeBusiness.id, svc.id, { is_active: next });
    } catch {
      setServices((prev) => prev.map((s) => (s.id === svc.id ? { ...s, is_active: !next } : s)));
      setToast({ message: t("error"), variant: "error" });
    }
  };

  const handleMultiToggle = async () => {
    const next = !multiOn;
    setMultiOn(next);  // optimistic
    try {
      const updated = await updateBusiness(activeBusiness.id, { allow_multi_service: next });
      // Keep the store's business in sync so the toggle survives navigation.
      setActiveBusiness({ ...activeBusiness, allow_multi_service: updated.allow_multi_service });
    } catch {
      setMultiOn(!next);  // rollback
      setToast({ message: t("error"), variant: "error" });
    }
  };

  if (!activeBusiness) {
    return <EmptyState icon={<IconScissors size={26} />} title={t("select_business_first")} subtitle={t("select_business_desc")} />;
  }

  return (
    <div className="animate-in">
      <div className="page-header">
        <div>
          <h1 className="page-title">{t("services")}</h1>
          <p className="page-subtitle">{t("services_subtitle")}</p>
        </div>
        <button className="btn btn-primary" onClick={openNew}>
          <IconPlus size={17} /> {t("new_service")}
        </button>
      </div>

      {/* Business-level setting: let customers pick several services in one booking. */}
      <div
        className="card card-tight row"
        style={{ justifyContent: "space-between", gap: "var(--space-3)", marginBottom: "var(--space-3)" }}
      >
        <div>
          <div style={{ fontWeight: 650, fontSize: "var(--text-sm)" }}>{t("allow_multi_service")}</div>
          <div className="form-hint" style={{ marginTop: 2 }}>{t("allow_multi_service_hint")}</div>
        </div>
        <label className="toggle">
          <input
            type="checkbox"
            aria-label={t("allow_multi_service")}
            checked={multiOn}
            onChange={handleMultiToggle}
          />
          <span className="toggle-slider"></span>
        </label>
      </div>

      {loading ? (
        <SkeletonList count={4} />
      ) : services.length === 0 ? (
        <div className="card">
          <EmptyState
            icon={<IconScissors size={24} />}
            title={t("no_services_title")}
            subtitle={t("no_services_desc")}
            action={
              <button className="btn btn-primary btn-sm" onClick={openNew}>
                <IconPlus size={15} /> {t("new_service")}
              </button>
            }
          />
        </div>
      ) : (
        <div className="stack stagger" style={{ gap: "var(--space-3)" }}>
          {services.map((svc) => (
            // flexWrap + a generous flex-basis on the text block: on desktop this
            // renders as one row (name+chips left, controls right); on a narrow
            // phone the controls wrap onto their own line instead of crushing the
            // name into one-character-per-line columns (bug6).
            <div
              key={svc.id}
              className="card card-tight row"
              style={{ gap: "var(--space-3)", flexWrap: "wrap", opacity: svc.is_active ? 1 : 0.6 }}
            >
              <span className="stat-icon" style={{ flexShrink: 0 }} aria-hidden>
                <IconScissors size={17} />
              </span>
              <div style={{ flex: "1 1 220px", minWidth: 0 }}>
                <div style={{ fontWeight: 750, lineHeight: 1.35, wordBreak: "break-word" }}>
                  {svc[`name_${lang}`] || svc.name_uz}
                </div>
                <div className="row" style={{ gap: 6, marginTop: 4, flexWrap: "wrap" }}>
                  <span className="chip" style={{ whiteSpace: "nowrap" }}>
                    <IconClock size={12} /> {svc.duration_minutes} {t("min")}
                  </span>
                  <span className="chip brand" style={{ whiteSpace: "nowrap" }}>{fmtPrice(svc.price, t)}</span>
                  {(svc.buffer_before_minutes > 0 || svc.buffer_after_minutes > 0) && (
                    <span className="chip" style={{ whiteSpace: "nowrap" }}>
                      +{svc.buffer_before_minutes + svc.buffer_after_minutes} {t("min_buffer")}
                    </span>
                  )}
                  {svc.requires_confirmation && <span className="chip honey" style={{ whiteSpace: "nowrap" }}>{t("manual_confirm")}</span>}
                </div>
              </div>
              <div className="row" style={{ gap: "var(--space-3)", marginLeft: "auto", flexShrink: 0, alignItems: "center" }}>
                <label className="toggle" title={t("is_active")}>
                  <input
                    type="checkbox"
                    aria-label={t("is_active")}
                    checked={svc.is_active}
                    onChange={() => handleToggle(svc)}
                  />
                  <span className="toggle-slider"></span>
                </label>
                <button className="btn btn-secondary btn-sm" onClick={() => openEdit(svc)}>
                  <IconEdit size={15} /> {t("edit")}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {showModal && (
        <Modal title={editing ? t("edit_service") : t("new_service")} onClose={() => setShowModal(false)}>
          <form onSubmit={handleSave}>
            {["uz", "ru", "en"].map((l) => (
              <div className="form-group" key={l}>
                <label>{t("name")} ({t(`lang_${l}`)}) *</label>
                <input
                  required maxLength={255} value={form[`name_${l}`]}
                  onChange={(e) => setForm({ ...form, [`name_${l}`]: e.target.value })}
                />
              </div>
            ))}

            <div className="grid-2">
              <div className="form-group">
                <label>{t("duration")} ({t("min")}) *</label>
                <input
                  type="number" min="5" max="1440" step="5" required value={form.duration_minutes}
                  onChange={(e) => setForm({ ...form, duration_minutes: parseInt(e.target.value || "0", 10) })}
                />
              </div>
              <div className="form-group">
                <label>{t("price")} ({t("uzs")})</label>
                <input
                  type="number" min="0" value={form.price} placeholder={t("free")}
                  onChange={(e) => setForm({ ...form, price: e.target.value })}
                />
              </div>
              <div className="form-group">
                <label>{t("buffer_before")} ({t("min")})</label>
                <input
                  type="number" min="0" max="1440" value={form.buffer_before_minutes}
                  onChange={(e) => setForm({ ...form, buffer_before_minutes: parseInt(e.target.value || "0", 10) })}
                />
              </div>
              <div className="form-group">
                <label>{t("buffer_after")} ({t("min")})</label>
                <input
                  type="number" min="0" max="1440" value={form.buffer_after_minutes}
                  onChange={(e) => setForm({ ...form, buffer_after_minutes: parseInt(e.target.value || "0", 10) })}
                />
              </div>
            </div>

            <div className="form-group row" style={{ justifyContent: "space-between" }}>
              <div>
                <div style={{ fontWeight: 650, fontSize: "var(--text-sm)" }}>{t("requires_manual_confirmation")}</div>
                <div className="form-hint" style={{ marginTop: 2 }}>{t("requires_manual_confirmation_hint")}</div>
              </div>
              <label className="toggle">
                <input
                  type="checkbox" aria-label={t("requires_manual_confirmation")}
                  checked={form.requires_confirmation}
                  onChange={(e) => setForm({ ...form, requires_confirmation: e.target.checked })}
                />
                <span className="toggle-slider"></span>
              </label>
            </div>

            {/* Consult-first controls: customers can book online (or staff-only),
                and an optional per-day cap (e.g. limit "Checkup" to 5/day). */}
            <div className="form-group row" style={{ justifyContent: "space-between" }}>
              <div>
                <div style={{ fontWeight: 650, fontSize: "var(--text-sm)" }}>{t("online_bookable")}</div>
                <div className="form-hint" style={{ marginTop: 2 }}>{t("online_bookable_hint")}</div>
              </div>
              <label className="toggle">
                <input
                  type="checkbox" aria-label={t("online_bookable")}
                  checked={form.online_bookable}
                  onChange={(e) => setForm({ ...form, online_bookable: e.target.checked })}
                />
                <span className="toggle-slider"></span>
              </label>
            </div>

            {form.online_bookable && (
              <div className="form-group">
                <label>{t("max_per_day")}</label>
                <input
                  type="number" min="1" max="1000" value={form.max_per_day}
                  placeholder={t("max_per_day_placeholder")}
                  onChange={(e) => setForm({ ...form, max_per_day: e.target.value })}
                />
                <div className="form-hint" style={{ marginTop: 2 }}>{t("max_per_day_hint")}</div>
              </div>
            )}

            {!showDescriptions ? (
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                style={{ marginBottom: "var(--space-3)" }}
                onClick={() => setShowDescriptions(true)}
              >
                <IconPlus size={14} /> {t("add_description")}
              </button>
            ) : (
              ["uz", "ru", "en"].map((l) => (
                <div className="form-group" key={`d-${l}`}>
                  <label>{t("description")} ({t(`lang_${l}`)})</label>
                  <textarea
                    rows={2} maxLength={2000} value={form[`description_${l}`]}
                    onChange={(e) => setForm({ ...form, [`description_${l}`]: e.target.value })}
                  />
                </div>
              ))
            )}

            {saveError && <p className="form-error" style={{ marginBottom: "var(--space-3)" }}>{saveError}</p>}

            <button type="submit" className="btn btn-primary btn-full" disabled={saving}>
              {saving ? t("loading") : (
                <>
                  <IconCheck size={16} /> {t("save")}
                </>
              )}
            </button>
          </form>
        </Modal>
      )}

      <Toast toast={toast} onClose={() => setToast(null)} />
    </div>
  );
}
