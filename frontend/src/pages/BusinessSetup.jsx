import { useEffect, useState } from "react";
import { getCategories, createBusiness, getMyBusinesses } from "../api/client";
import useStore from "../store/useStore";
import { useNavigate } from "react-router-dom";
import { useT } from "../i18n";
import { IconArrowLeft, IconCheck, IconStore } from "../components/icons";

const STEPS = 3;

export default function BusinessSetup() {
  const { lang, setActiveBusiness, setBusinesses } = useStore();
  const t = useT(lang);
  const navigate = useNavigate();
  const [categories, setCategories] = useState([]);
  const [step, setStep] = useState(0);
  const [form, setForm] = useState({
    category_id: "",
    name: "",
    region: "Namangan",
    district: "Pop",
    city: "Pop",
    address: "",
    phone: "",
    telegram_username: "",
    instagram_link: "",
    description: "",
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [loadingCategories, setLoadingCategories] = useState(true);

  useEffect(() => {
    getCategories()
      .then(setCategories)
      .catch(() => {})
      .finally(() => setLoadingCategories(false));
  }, []);

  const set = (key, value) => setForm((f) => ({ ...f, [key]: value }));

  const canNext =
    step === 0 ? Boolean(form.category_id)
    : step === 1 ? Boolean(form.name.trim() && form.address.trim() && form.phone.trim())
    : true;

  const handleSubmit = async () => {
    setError("");
    setSaving(true);
    try {
      const biz = await createBusiness({ ...form, category_id: parseInt(form.category_id, 10) });
      const all = await getMyBusinesses().catch(() => [biz]);
      setBusinesses(all);
      setActiveBusiness(biz);
      navigate("/");
    } catch (err) {
      setError(err.response?.data?.detail || t("error_creating_business"));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div style={{ maxWidth: 640 }} className="animate-in">
      <div className="page-header">
        <div>
          <div className="eyebrow">{t("step_x_of_y", { x: step + 1, y: STEPS })}</div>
          <h1 className="page-title" style={{ marginTop: 4 }}>{t("register_business")}</h1>
        </div>
      </div>

      {/* Progress */}
      <div className="steps">
        {Array.from({ length: STEPS }).map((_, i) => (
          <div key={i} style={{ display: "contents" }}>
            <span className={`step-dot${i === step ? " on" : i < step ? " done" : ""}`}>
              {i < step ? <IconCheck size={14} /> : i + 1}
            </span>
            {i < STEPS - 1 && <span className={`step-line${i < step ? " done" : ""}`} />}
          </div>
        ))}
      </div>

      <div className="card">
        {/* Step 1: category */}
        {step === 0 && (
          <>
            <h3 className="card-title" style={{ marginBottom: 4 }}>{t("setup_step1_title")}</h3>
            <p className="form-hint" style={{ marginBottom: "var(--space-4)" }}>{t("setup_step1_sub")}</p>
            {loadingCategories ? (
              <div className="skeleton" style={{ height: 120 }} />
            ) : categories.length === 0 ? (
              <p className="form-hint">{t("no_data")}</p>
            ) : (
              <div className="cat-grid">
                {categories.map((c) => (
                  <button
                    key={c.id}
                    type="button"
                    className={`cat-card${String(form.category_id) === String(c.id) ? " on" : ""}`}
                    onClick={() => set("category_id", c.id)}
                  >
                    <span className="cat-ico" aria-hidden>{c.icon || <IconStore size={24} />}</span>
                    {c[`name_${lang}`] || c.name_uz}
                  </button>
                ))}
              </div>
            )}
          </>
        )}

        {/* Step 2: essentials */}
        {step === 1 && (
          <>
            <h3 className="card-title" style={{ marginBottom: 4 }}>{t("setup_step2_title")}</h3>
            <p className="form-hint" style={{ marginBottom: "var(--space-4)" }}>{t("setup_step2_sub")}</p>
            <div className="form-group">
              <label>{t("business_name")} *</label>
              <input
                required maxLength={255} value={form.name}
                onChange={(e) => set("name", e.target.value)}
                placeholder={t("business_name_ph")}
              />
            </div>
            <div className="form-group">
              <label>{t("phone")} *</label>
              <input
                required type="tel" maxLength={20} value={form.phone}
                onChange={(e) => set("phone", e.target.value)}
                placeholder="+998 90 123 45 67"
              />
            </div>
            <div className="form-group">
              <label>{t("address")} *</label>
              <input
                required maxLength={500} value={form.address}
                onChange={(e) => set("address", e.target.value)}
                placeholder={t("address_ph")}
              />
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))", gap: "var(--space-3)" }}>
              <div className="form-group">
                <label>{t("region")}</label>
                <input maxLength={100} value={form.region} onChange={(e) => set("region", e.target.value)} />
              </div>
              <div className="form-group">
                <label>{t("district")}</label>
                <input maxLength={100} value={form.district} onChange={(e) => set("district", e.target.value)} />
              </div>
              <div className="form-group">
                <label>{t("city")}</label>
                <input maxLength={100} value={form.city} onChange={(e) => set("city", e.target.value)} />
              </div>
            </div>
          </>
        )}

        {/* Step 3: contacts (optional) */}
        {step === 2 && (
          <>
            <h3 className="card-title" style={{ marginBottom: 4 }}>{t("setup_step3_title")}</h3>
            <p className="form-hint" style={{ marginBottom: "var(--space-4)" }}>{t("setup_step3_sub")}</p>
            <div className="grid-2">
              <div className="form-group">
                <label>{t("telegram_username")}</label>
                <input maxLength={100} value={form.telegram_username} onChange={(e) => set("telegram_username", e.target.value)} placeholder="@yourbusiness" />
              </div>
              <div className="form-group">
                <label>{t("instagram")}</label>
                <input maxLength={255} value={form.instagram_link} onChange={(e) => set("instagram_link", e.target.value)} placeholder="instagram.com/..." />
              </div>
            </div>
            <div className="form-group">
              <label>{t("description")}</label>
              <textarea rows={3} maxLength={2000} value={form.description} onChange={(e) => set("description", e.target.value)} />
            </div>
            <div
              className="card-tight"
              style={{ background: "var(--brand-50)", border: "1px solid var(--brand-100)", borderRadius: "var(--radius-sm)", padding: "var(--space-3)" }}
            >
              <p style={{ fontSize: "var(--text-sm)", color: "var(--brand-800)", fontWeight: 600 }}>
                {t("setup_trial_note")}
              </p>
            </div>
          </>
        )}

        {error && <p className="form-error" style={{ marginTop: "var(--space-3)" }}>{error}</p>}

        <div className="row" style={{ justifyContent: "space-between", marginTop: "var(--space-5)" }}>
          <button
            type="button"
            className="btn btn-ghost"
            onClick={() => setStep((s) => Math.max(0, s - 1))}
            style={{ visibility: step === 0 ? "hidden" : "visible" }}
          >
            <IconArrowLeft size={16} /> {t("back")}
          </button>
          {step < STEPS - 1 ? (
            <button type="button" className="btn btn-primary" disabled={!canNext} onClick={() => setStep((s) => s + 1)}>
              {t("continue")}
            </button>
          ) : (
            <button type="button" className="btn btn-primary" disabled={saving} onClick={handleSubmit}>
              {saving ? t("loading") : (<><IconCheck size={16} /> {t("register_business")}</>)}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
