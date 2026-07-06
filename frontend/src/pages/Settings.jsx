import { useEffect, useState } from "react";
import { getBusiness, updateBusiness } from "../api/client";
import useStore from "../store/useStore";
import { useT } from "../i18n";
import { SkeletonCard } from "../components/Skeleton";
import EmptyState from "../components/EmptyState";
import Toast from "../components/Toast";
import {
  IconStore, IconLink, IconCopy, IconCheck, IconSettings, IconSend, IconTelegram,
} from "../components/icons";
import LocationPicker from "../components/LocationPicker";

const BOT_USERNAME = import.meta.env.VITE_TELEGRAM_BOT_USERNAME || "QulayNavbat_bot";

export default function Settings() {
  const { lang, activeBusiness, setActiveBusiness } = useStore();
  const t = useT(lang);
  const [form, setForm] = useState(null);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState(null);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState(false);

  const load = () => {
    if (!activeBusiness) return;
    setError(false);
    getBusiness(activeBusiness.id).then((biz) => {
        setForm({
          name: biz.name || "",
          phone: biz.phone || "",
          address: biz.address || "",
          city: biz.city || "",
          region: biz.region || "",
          district: biz.district || "",
          latitude: biz.latitude ?? null,
          longitude: biz.longitude ?? null,
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
      }).catch(() => setError(true));
  };

  useEffect(() => { load(); }, [activeBusiness]);

  const set = (key, value) => setForm((f) => ({ ...f, [key]: value }));

  const bookingLink = activeBusiness ? `https://t.me/${BOT_USERNAME}?start=book_${activeBusiness.id}` : "";

  const copyLink = async () => {
    try {
      await navigator.clipboard.writeText(bookingLink);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setToast({ message: t("error"), variant: "error" });
    }
  };

  const handleSave = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      const updated = await updateBusiness(activeBusiness.id, form);
      setActiveBusiness(updated);
      setToast({ message: t("saved"), variant: "success" });
    } catch (err) {
      setToast({ message: err.response?.data?.detail || t("error"), variant: "error" });
    } finally {
      setSaving(false);
    }
  };

  if (!activeBusiness) {
    return <EmptyState icon={<IconSettings size={26} />} title={t("select_business_first")} subtitle={t("select_business_desc")} />;
  }
  if (error) {
    return (
      <div style={{ maxWidth: 720 }}>
        <div className="page-header"><h1 className="page-title">{t("settings")}</h1></div>
        <div className="card">
          <EmptyState
            icon={<IconSettings size={26} />}
            title={t("error")}
            subtitle={t("try_again")}
            action={<button type="button" className="btn btn-primary" onClick={load}>{t("refresh")}</button>}
          />
        </div>
      </div>
    );
  }
  if (!form) {
    return (
      <div style={{ maxWidth: 720 }}>
        <div className="page-header"><h1 className="page-title">{t("settings")}</h1></div>
        <div className="stack"><SkeletonCard /><SkeletonCard /><SkeletonCard /></div>
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 720 }} className="animate-in">
      <div className="page-header">
        <div>
          <h1 className="page-title">{t("settings")}</h1>
          <p className="page-subtitle">{activeBusiness.name}</p>
        </div>
      </div>

      {/* Booking link — the thing owners put in their Instagram bio */}
      <div
        className="card"
        style={{
          marginBottom: "var(--space-4)",
          background: "linear-gradient(120deg, var(--brand-50), #fff 75%)",
          border: "1px solid var(--brand-100)",
        }}
      >
        <div className="row" style={{ gap: 10, marginBottom: "var(--space-3)" }}>
          <span className="stat-icon" aria-hidden><IconLink size={17} /></span>
          <div>
            <h3 className="card-title">{t("booking_link")}</h3>
            <div className="card-sub">{t("booking_link_sub")}</div>
          </div>
        </div>
        <div
          className="tnum"
          style={{
            background: "var(--surface)", border: "1px dashed var(--brand-200)",
            borderRadius: "var(--radius-sm)", padding: "var(--space-3)",
            fontSize: "var(--text-sm)", fontWeight: 650, wordBreak: "break-all",
            marginBottom: "var(--space-3)",
          }}
        >
          {bookingLink}
        </div>
        <div className="row" style={{ flexWrap: "wrap", gap: 8 }}>
          <button type="button" className="btn btn-primary btn-sm" onClick={copyLink}>
            {copied ? <IconCheck size={15} /> : <IconCopy size={15} />} {copied ? t("copied") : t("copy")}
          </button>
          <a
            className="btn btn-secondary btn-sm"
            href={`https://t.me/share/url?url=${encodeURIComponent(bookingLink)}&text=${encodeURIComponent(activeBusiness.name)}`}
            target="_blank" rel="noopener noreferrer"
          >
            <IconSend size={15} /> {t("share_telegram")}
          </a>
          <a className="btn btn-secondary btn-sm" href={bookingLink} target="_blank" rel="noopener noreferrer">
            <IconTelegram size={15} /> {t("open_in_telegram")}
          </a>
        </div>
      </div>

      <form onSubmit={handleSave}>
        {/* Basic info */}
        <div className="card" style={{ marginBottom: "var(--space-4)" }}>
          <div className="row" style={{ gap: 10, marginBottom: "var(--space-4)" }}>
            <span className="stat-icon" aria-hidden><IconStore size={17} /></span>
            <h3 className="card-title">{t("business_info")}</h3>
          </div>
          <div className="form-group">
            <label>{t("business_name")} *</label>
            <input required maxLength={255} value={form.name} onChange={(e) => set("name", e.target.value)} />
          </div>
          <div className="grid-2">
            <div className="form-group">
              <label>{t("phone")} *</label>
              <input required type="tel" maxLength={20} value={form.phone} onChange={(e) => set("phone", e.target.value)} />
            </div>
            <div className="form-group">
              <label>{t("telegram")}</label>
              <input maxLength={100} value={form.telegram_username} onChange={(e) => set("telegram_username", e.target.value)} placeholder="@yourbusiness" />
            </div>
          </div>
          <div className="form-group">
            <label>{t("address")} *</label>
            <input required maxLength={500} value={form.address} onChange={(e) => set("address", e.target.value)} />
          </div>
          {/* Region/district/city locked to Namangan / Pop for launch — kept in
              form state (loaded from the business), just not shown here. */}
          <div className="form-group">
            <label>{t("instagram")}</label>
            <input maxLength={255} value={form.instagram_link} onChange={(e) => set("instagram_link", e.target.value)} placeholder="instagram.com/..." />
          </div>
          <div className="form-group">
            <label>{t("description")}</label>
            <textarea rows={3} maxLength={2000} value={form.description} onChange={(e) => set("description", e.target.value)} />
          </div>
          <LocationPicker
            latitude={form.latitude}
            longitude={form.longitude}
            onChange={(lat, lng) => setForm((f) => ({ ...f, latitude: lat, longitude: lng }))}
          />
        </div>

        {/* Booking rules */}
        <div className="card" style={{ marginBottom: "var(--space-4)" }}>
          <div className="row" style={{ gap: 10, marginBottom: "var(--space-4)" }}>
            <span className="stat-icon honey" aria-hidden><IconSettings size={17} /></span>
            <h3 className="card-title">{t("booking_rules")}</h3>
          </div>

          <div className="row" style={{ justifyContent: "space-between", marginBottom: "var(--space-4)" }}>
            <div>
              <div style={{ fontWeight: 650, fontSize: "var(--text-sm)" }}>{t("online_booking")}</div>
              <div className="form-hint" style={{ marginTop: 2 }}>{t("allow_online_booking_desc")}</div>
            </div>
            <label className="toggle">
              <input
                type="checkbox"
                aria-label={t("online_booking")}
                checked={form.is_online_booking_enabled}
                onChange={(e) => set("is_online_booking_enabled", e.target.checked)}
              />
              <span className="toggle-slider"></span>
            </label>
          </div>

          <div className="grid-2">
            <div className="form-group">
              <label>{t("slot_step_minutes")}</label>
              <select value={form.slot_step_minutes} onChange={(e) => set("slot_step_minutes", parseInt(e.target.value, 10))}>
                {[5, 10, 15, 20, 30, 60].map((v) => <option key={v} value={v}>{v} {t("min")}</option>)}
              </select>
            </div>
            <div className="form-group">
              <label>{t("min_advance_booking")}</label>
              <select value={form.min_advance_booking_minutes} onChange={(e) => set("min_advance_booking_minutes", parseInt(e.target.value, 10))}>
                {[0, 30, 60, 120, 180, 360, 720, 1440].map((v) => (
                  <option key={v} value={v}>
                    {v === 0 ? t("no_minimum") : v < 60 ? `${v} ${t("min")}` : `${v / 60} ${t("hours_unit")}`}
                  </option>
                ))}
              </select>
            </div>
            <div className="form-group">
              <label>{t("max_advance_booking_days")}</label>
              <select value={form.max_advance_booking_days} onChange={(e) => set("max_advance_booking_days", parseInt(e.target.value, 10))}>
                {[7, 14, 30, 60, 90].map((v) => <option key={v} value={v}>{v} {t("days_unit")}</option>)}
              </select>
            </div>
            <div className="form-group">
              <label>{t("cancellation_policy_hours")}</label>
              <select value={form.cancellation_policy_hours} onChange={(e) => set("cancellation_policy_hours", parseInt(e.target.value, 10))}>
                {[0, 1, 2, 4, 6, 12, 24, 48].map((v) => (
                  <option key={v} value={v}>{v === 0 ? t("no_policy") : `${v} ${t("hours_unit")} ${t("before")}`}</option>
                ))}
              </select>
            </div>
          </div>
        </div>

        {/* Custom messages */}
        <div className="card" style={{ marginBottom: "var(--space-4)" }}>
          <h3 className="card-title">{t("custom_confirmation_message")}</h3>
          <p className="form-hint" style={{ marginBottom: "var(--space-4)" }}>{t("custom_message_help")}</p>
          {["uz", "ru", "en"].map((l) => (
            <div className="form-group" key={l}>
              <label>{t(`lang_${l}`)}</label>
              <textarea
                rows={2} maxLength={1000}
                value={form[`custom_message_${l}`]}
                onChange={(e) => set(`custom_message_${l}`, e.target.value)}
              />
            </div>
          ))}
        </div>

        <div className="savebar">
          <span className="form-hint">{t("save_hint")}</span>
          <button type="submit" className="btn btn-primary" disabled={saving}>
            {saving ? t("loading") : (<><IconCheck size={16} /> {t("save")}</>)}
          </button>
        </div>
      </form>

      <Toast toast={toast} onClose={() => setToast(null)} />
    </div>
  );
}
