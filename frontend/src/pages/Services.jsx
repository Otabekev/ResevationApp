import { useEffect, useState } from "react";
import { getServices, createService, updateService, deleteService } from "../api/client";
import useStore from "../store/useStore";
import { useT } from "../i18n";
import { SkeletonList } from "../components/Skeleton";
import EmptyState from "../components/EmptyState";

const EMPTY_FORM = {
  name_uz: "", name_ru: "", name_en: "",
  duration_minutes: 30, buffer_before_minutes: 0, buffer_after_minutes: 0,
  price: "", currency: "UZS",
  requires_confirmation: false, is_active: true, sort_order: 0,
};

export default function Services() {
  const { lang, activeBusiness } = useStore();
  const t = useT(lang);
  const [services, setServices] = useState([]);
  const [showModal, setShowModal] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (activeBusiness) load();
  }, [activeBusiness]);

  const load = async () => {
    setLoading(true);
    try {
      const data = await getServices(activeBusiness.id);
      setServices(data);
    } finally {
      setLoading(false);
    }
  };

  const openNew = () => { setForm(EMPTY_FORM); setEditing(null); setSaveError(false); setShowModal(true); };
  const openEdit = (svc) => {
    setForm({ ...svc, price: svc.price ?? "" });
    setEditing(svc.id);
    setSaveError(false);
    setShowModal(true);
  };

  const handleSave = async (e) => {
    e.preventDefault();
    setSaving(true);
    setSaveError(false);
    try {
      const payload = { ...form, price: form.price === "" ? null : parseFloat(form.price) };
      if (editing) {
        await updateService(activeBusiness.id, editing, payload);
      } else {
        await createService(activeBusiness.id, payload);
      }
      await load();
      setShowModal(false);
    } catch (err) {
      setSaveError(true);
    } finally {
      setSaving(false);
    }
  };

  const handleToggle = async (svc) => {
    await updateService(activeBusiness.id, svc.id, { is_active: !svc.is_active });
    await load();
  };

  if (!activeBusiness) return <EmptyState title={t("select_business_first")} />;

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">{t("services")}</h1>
        <button className="btn btn-primary" onClick={openNew}>+ {t("new_service")}</button>
      </div>

      {loading ? (
        <SkeletonList count={4} />
      ) : services.length === 0 ? (
        <EmptyState icon="✂️" title={t("no_services_title")} subtitle={t("no_services_desc")} />
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
          {services.map((svc) => (
            <div key={svc.id} className="card" style={{ display: "flex", alignItems: "center", gap: "var(--space-3)" }}>
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 700 }}>{svc[`name_${lang}`] || svc.name_uz}</div>
                <div style={{ fontSize: "var(--text-sm)", color: "var(--gray-500)", marginTop: 2 }}>
                  ⏱ {svc.duration_minutes} {t("min")}
                  {` • ${svc.price ? `${parseInt(svc.price).toLocaleString()} ${t("uzs")}` : t("free")}`}
                  {svc.requires_confirmation && ` • ✋ ${t("manual_confirm")}`}
                </div>
              </div>
              <label className="toggle">
                <input type="checkbox" aria-label={t("is_active")} checked={svc.is_active} onChange={() => handleToggle(svc)} />
                <span className="toggle-slider"></span>
              </label>
              <button className="btn btn-secondary btn-sm" onClick={() => openEdit(svc)}>{t("edit")}</button>
            </div>
          ))}
        </div>
      )}

      {showModal && (
        <div className="modal-overlay" onClick={(e) => e.target === e.currentTarget && setShowModal(false)}>
          <div className="modal">
            <div className="modal-header">
              <h3 className="modal-title">{editing ? t("edit") : t("new_service")}</h3>
              <button className="modal-close" onClick={() => setShowModal(false)}>×</button>
            </div>
            <form onSubmit={handleSave}>
              {["uz", "ru", "en"].map((l) => (
                <div className="form-group" key={l}>
                  <label>{t("name")} ({t(`lang_${l}`)})</label>
                  <input required value={form[`name_${l}`]}
                    onChange={(e) => setForm({ ...form, [`name_${l}`]: e.target.value })} />
                </div>
              ))}
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--space-3)" }}>
                <div className="form-group">
                  <label>{t("duration")} ({t("min")})</label>
                  <input type="number" min="5" required value={form.duration_minutes}
                    onChange={(e) => setForm({ ...form, duration_minutes: parseInt(e.target.value) })} />
                </div>
                <div className="form-group">
                  <label>{t("price")} ({t("uzs")})</label>
                  <input type="number" min="0" value={form.price}
                    onChange={(e) => setForm({ ...form, price: e.target.value })} />
                </div>
                <div className="form-group">
                  <label>{t("buffer_before")} ({t("min")})</label>
                  <input type="number" min="0" value={form.buffer_before_minutes}
                    onChange={(e) => setForm({ ...form, buffer_before_minutes: parseInt(e.target.value) })} />
                </div>
                <div className="form-group">
                  <label>{t("buffer_after")} ({t("min")})</label>
                  <input type="number" min="0" value={form.buffer_after_minutes}
                    onChange={(e) => setForm({ ...form, buffer_after_minutes: parseInt(e.target.value) })} />
                </div>
              </div>
              <div className="form-group" style={{ display: "flex", alignItems: "center", gap: "var(--space-3)" }}>
                <label className="toggle">
                  <input type="checkbox" aria-label={t("requires_manual_confirmation")} checked={form.requires_confirmation}
                    onChange={(e) => setForm({ ...form, requires_confirmation: e.target.checked })} />
                  <span className="toggle-slider"></span>
                </label>
                <span style={{ fontSize: "var(--text-sm)" }}>{t("requires_manual_confirmation")}</span>
              </div>
              {saveError && (
                <p style={{ color: "var(--danger)", fontSize: "var(--text-sm)" }}>{t("service_save_error")}</p>
              )}
              <button type="submit" className="btn btn-primary btn-full" disabled={saving}>
                {saving ? t("loading") : t("save")}
              </button>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
