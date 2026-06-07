import { useEffect, useState } from "react";
import { getServices, createService, updateService, deleteService } from "../api/client";
import useStore from "../store/useStore";
import { useT } from "../i18n";

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

  useEffect(() => {
    if (activeBusiness) load();
  }, [activeBusiness]);

  const load = async () => {
    const data = await getServices(activeBusiness.id);
    setServices(data);
  };

  const openNew = () => { setForm(EMPTY_FORM); setEditing(null); setShowModal(true); };
  const openEdit = (svc) => {
    setForm({ ...svc, price: svc.price ?? "" });
    setEditing(svc.id);
    setShowModal(true);
  };

  const handleSave = async (e) => {
    e.preventDefault();
    setSaving(true);
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
      alert("Error saving service");
    } finally {
      setSaving(false);
    }
  };

  const handleToggle = async (svc) => {
    await updateService(activeBusiness.id, svc.id, { is_active: !svc.is_active });
    await load();
  };

  if (!activeBusiness) return <p style={{ padding: 24, color: "var(--gray-500)" }}>Select a business first.</p>;

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">{t("services")}</h1>
        <button className="btn btn-primary" onClick={openNew}>+ {t("new_service")}</button>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {services.map((svc) => (
          <div key={svc.id} className="card" style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 700 }}>{svc[`name_${lang}`] || svc.name_uz}</div>
              <div style={{ fontSize: 13, color: "var(--gray-500)", marginTop: 2 }}>
                ⏱ {svc.duration_minutes} {t("min")}
                {svc.price && ` • ${parseInt(svc.price).toLocaleString()} ${t("uzs")}`}
                {svc.requires_confirmation && " • ✋ Manual confirm"}
              </div>
            </div>
            <label className="toggle">
              <input type="checkbox" checked={svc.is_active} onChange={() => handleToggle(svc)} />
              <span className="toggle-slider"></span>
            </label>
            <button className="btn btn-secondary btn-sm" onClick={() => openEdit(svc)}>{t("edit")}</button>
          </div>
        ))}
        {services.length === 0 && (
          <div className="card" style={{ textAlign: "center", padding: 40, color: "var(--gray-400)" }}>
            No services yet. Add your first service.
          </div>
        )}
      </div>

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
                  <label>Name ({l.toUpperCase()})</label>
                  <input required value={form[`name_${l}`]}
                    onChange={(e) => setForm({ ...form, [`name_${l}`]: e.target.value })} />
                </div>
              ))}
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                <div className="form-group">
                  <label>{t("duration")} ({t("min")})</label>
                  <input type="number" min="5" required value={form.duration_minutes}
                    onChange={(e) => setForm({ ...form, duration_minutes: parseInt(e.target.value) })} />
                </div>
                <div className="form-group">
                  <label>{t("price")} (UZS)</label>
                  <input type="number" min="0" value={form.price}
                    onChange={(e) => setForm({ ...form, price: e.target.value })} />
                </div>
                <div className="form-group">
                  <label>Buffer Before ({t("min")})</label>
                  <input type="number" min="0" value={form.buffer_before_minutes}
                    onChange={(e) => setForm({ ...form, buffer_before_minutes: parseInt(e.target.value) })} />
                </div>
                <div className="form-group">
                  <label>Buffer After ({t("min")})</label>
                  <input type="number" min="0" value={form.buffer_after_minutes}
                    onChange={(e) => setForm({ ...form, buffer_after_minutes: parseInt(e.target.value) })} />
                </div>
              </div>
              <div className="form-group" style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <label className="toggle">
                  <input type="checkbox" checked={form.requires_confirmation}
                    onChange={(e) => setForm({ ...form, requires_confirmation: e.target.checked })} />
                  <span className="toggle-slider"></span>
                </label>
                <span style={{ fontSize: 14 }}>Requires manual confirmation</span>
              </div>
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
