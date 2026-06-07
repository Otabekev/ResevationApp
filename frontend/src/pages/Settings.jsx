import { useEffect, useState } from "react";
import { getBusiness, updateBusiness } from "../api/client";
import useStore from "../store/useStore";
import { useT } from "../i18n";

export default function Settings() {
  const { lang, activeBusiness, setActiveBusiness } = useStore();
  const t = useT(lang);
  const [form, setForm] = useState(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (activeBusiness) {
      getBusiness(activeBusiness.id).then((biz) => {
        setForm({
          name: biz.name || "",
          phone: biz.phone || "",
          address: biz.address || "",
          city: biz.city || "",
          region: biz.region || "",
          district: biz.district || "",
          telegram_username: biz.telegram_username || "",
          instagram_link: biz.instagram_link || "",
          description: biz.description || "",
          is_online_booking_enabled: biz.is_online_booking_enabled ?? true,
          slot_step_minutes: biz.slot_step_minutes ?? 15,
          min_advance_booking_minutes: biz.min_advance_booking_minutes ?? 60,
          max_advance_booking_days: biz.max_advance_booking_days ?? 30,
          cancellation_policy_hours: biz.cancellation_policy_hours ?? 2,
          custom_message_uz: biz.custom_message_uz || "",
          custom_message_ru: biz.custom_message_ru || "",
          custom_message_en: biz.custom_message_en || "",
        });
      });
    }
  }, [activeBusiness]);

  const set = (key, value) => setForm((f) => ({ ...f, [key]: value }));

  const handleSave = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError("");
    setSaved(false);
    try {
      const updated = await updateBusiness(activeBusiness.id, form);
      setActiveBusiness(updated);
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (err) {
      setError(err.response?.data?.detail || t("error"));
    } finally {
      setSaving(false);
    }
  };

  if (!activeBusiness) return <p style={{ padding: 24, color: "var(--gray-500)" }}>Select a business first.</p>;
  if (!form) return <p style={{ padding: 24, color: "var(--gray-500)" }}>{t("loading")}</p>;

  return (
    <div style={{ maxWidth: 680 }}>
      <div className="page-header">
        <h1 className="page-title">{t("settings")}</h1>
      </div>

      <form onSubmit={handleSave}>
        {/* Basic info */}
        <div className="card" style={{ marginBottom: 16 }}>
          <h3 style={{ marginTop: 0, marginBottom: 16, fontSize: 15 }}>Business Info</h3>
          <div className="form-group">
            <label>{t("business_name")} *</label>
            <input required value={form.name} onChange={(e) => set("name", e.target.value)} />
          </div>
          <div className="form-group">
            <label>{t("phone")} *</label>
            <input required value={form.phone} onChange={(e) => set("phone", e.target.value)} />
          </div>
          <div className="form-group">
            <label>{t("address")} *</label>
            <input required value={form.address} onChange={(e) => set("address", e.target.value)} />
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12 }}>
            <div className="form-group">
              <label>{t("region")}</label>
              <input value={form.region} onChange={(e) => set("region", e.target.value)} />
            </div>
            <div className="form-group">
              <label>{t("district")}</label>
              <input value={form.district} onChange={(e) => set("district", e.target.value)} />
            </div>
            <div className="form-group">
              <label>City</label>
              <input value={form.city} onChange={(e) => set("city", e.target.value)} />
            </div>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <div className="form-group">
              <label>Telegram</label>
              <input value={form.telegram_username} onChange={(e) => set("telegram_username", e.target.value)}
                placeholder="@yourbusiness" />
            </div>
            <div className="form-group">
              <label>Instagram</label>
              <input value={form.instagram_link} onChange={(e) => set("instagram_link", e.target.value)}
                placeholder="instagram.com/..." />
            </div>
          </div>
          <div className="form-group">
            <label>Description</label>
            <textarea rows={3} value={form.description} onChange={(e) => set("description", e.target.value)} />
          </div>
        </div>

        {/* Booking rules */}
        <div className="card" style={{ marginBottom: 16 }}>
          <h3 style={{ marginTop: 0, marginBottom: 16, fontSize: 15 }}>Booking Rules</h3>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
            <div>
              <div style={{ fontWeight: 600, fontSize: 14 }}>{t("online_booking")}</div>
              <div style={{ fontSize: 12, color: "var(--gray-500)" }}>Allow customers to book via Telegram</div>
            </div>
            <button
              type="button"
              className={`toggle${form.is_online_booking_enabled ? " on" : ""}`}
              onClick={() => set("is_online_booking_enabled", !form.is_online_booking_enabled)}
            />
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <div className="form-group">
              <label>Slot step (minutes)</label>
              <select value={form.slot_step_minutes} onChange={(e) => set("slot_step_minutes", parseInt(e.target.value))}>
                {[5, 10, 15, 20, 30, 60].map((v) => <option key={v} value={v}>{v} min</option>)}
              </select>
            </div>
            <div className="form-group">
              <label>Min advance booking</label>
              <select value={form.min_advance_booking_minutes} onChange={(e) => set("min_advance_booking_minutes", parseInt(e.target.value))}>
                {[0, 30, 60, 120, 180, 360, 720, 1440].map((v) => (
                  <option key={v} value={v}>{v === 0 ? "No minimum" : v < 60 ? `${v} min` : `${v / 60}h`}</option>
                ))}
              </select>
            </div>
            <div className="form-group">
              <label>Max advance booking (days)</label>
              <select value={form.max_advance_booking_days} onChange={(e) => set("max_advance_booking_days", parseInt(e.target.value))}>
                {[7, 14, 30, 60, 90].map((v) => <option key={v} value={v}>{v} days</option>)}
              </select>
            </div>
            <div className="form-group">
              <label>Cancellation policy (hours before)</label>
              <select value={form.cancellation_policy_hours} onChange={(e) => set("cancellation_policy_hours", parseInt(e.target.value))}>
                {[0, 1, 2, 4, 6, 12, 24, 48].map((v) => (
                  <option key={v} value={v}>{v === 0 ? "No policy" : `${v}h before`}</option>
                ))}
              </select>
            </div>
          </div>
        </div>

        {/* Custom messages */}
        <div className="card" style={{ marginBottom: 16 }}>
          <h3 style={{ marginTop: 0, marginBottom: 4, fontSize: 15 }}>Custom Confirmation Message</h3>
          <p style={{ fontSize: 12, color: "var(--gray-500)", marginBottom: 16 }}>Shown to customers after booking. Leave blank for default.</p>
          <div className="form-group">
            <label>O'zbek (UZ)</label>
            <textarea rows={2} value={form.custom_message_uz}
              onChange={(e) => set("custom_message_uz", e.target.value)}
              placeholder="Broningiz uchun rahmat!..." />
          </div>
          <div className="form-group">
            <label>Russian (RU)</label>
            <textarea rows={2} value={form.custom_message_ru}
              onChange={(e) => set("custom_message_ru", e.target.value)}
              placeholder="Спасибо за запись!..." />
          </div>
          <div className="form-group">
            <label>English (EN)</label>
            <textarea rows={2} value={form.custom_message_en}
              onChange={(e) => set("custom_message_en", e.target.value)}
              placeholder="Thank you for booking!..." />
          </div>
        </div>

        {error && <p style={{ color: "var(--danger)", fontSize: 13, marginBottom: 12 }}>{error}</p>}
        {saved && <p style={{ color: "var(--success)", fontSize: 13, marginBottom: 12 }}>Saved!</p>}

        <button type="submit" className="btn btn-primary" disabled={saving}>
          {saving ? t("loading") : t("save")}
        </button>
      </form>
    </div>
  );
}
