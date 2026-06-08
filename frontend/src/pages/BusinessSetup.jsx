import { useEffect, useState } from "react";
import { getCategories, createBusiness } from "../api/client";
import useStore from "../store/useStore";
import { useNavigate } from "react-router-dom";
import { useT } from "../i18n";

export default function BusinessSetup() {
  const { lang, setActiveBusiness } = useStore();
  const t = useT(lang);
  const navigate = useNavigate();
  const [categories, setCategories] = useState([]);
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
      .finally(() => setLoadingCategories(false));
  }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setSaving(true);
    try {
      const biz = await createBusiness({ ...form, category_id: parseInt(form.category_id) });
      setActiveBusiness(biz);
      navigate("/");
    } catch (err) {
      setError(err.response?.data?.detail || t("error_creating_business"));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div style={{ maxWidth: 560 }}>
      <div className="page-header">
        <h1 className="page-title">{t("register_business")}</h1>
      </div>
      <div className="card">
        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label>{t("category")} *</label>
            <select required value={form.category_id} disabled={loadingCategories}
              onChange={(e) => setForm({ ...form, category_id: e.target.value })}>
              <option value="">{loadingCategories ? t("loading") : t("select_category")}</option>
              {categories.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.icon} {c[`name_${lang}`] || c.name_uz}
                </option>
              ))}
            </select>
            {!loadingCategories && categories.length === 0 && (
              <p className="muted" style={{ fontSize: "var(--text-sm)" }}>{t("no_data")}</p>
            )}
          </div>
          <div className="form-group">
            <label>{t("business_name")} *</label>
            <input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="e.g. Barber Style, Dental Plus..." />
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--space-3)" }}>
            <div className="form-group">
              <label>{t("region")}</label>
              <input value={form.region} onChange={(e) => setForm({ ...form, region: e.target.value })} />
            </div>
            <div className="form-group">
              <label>{t("district")}</label>
              <input value={form.district} onChange={(e) => setForm({ ...form, district: e.target.value })} />
            </div>
          </div>
          <div className="form-group">
            <label>{t("address")} *</label>
            <input required value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })}
              placeholder="Street, building..." />
          </div>
          <div className="form-group">
            <label>{t("phone")} *</label>
            <input required value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })}
              placeholder="+998901234567" />
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--space-3)" }}>
            <div className="form-group">
              <label>{t("telegram_username")}</label>
              <input value={form.telegram_username} onChange={(e) => setForm({ ...form, telegram_username: e.target.value })}
                placeholder="@yourbusiness" />
            </div>
            <div className="form-group">
              <label>{t("instagram")}</label>
              <input value={form.instagram_link} onChange={(e) => setForm({ ...form, instagram_link: e.target.value })}
                placeholder="instagram.com/..." />
            </div>
          </div>
          <div className="form-group">
            <label>{t("description")}</label>
            <textarea rows={3} value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })} />
          </div>
          {error && (
            <div className="form-group">
              <p style={{ color: "var(--danger)", fontSize: "var(--text-sm)" }}>{error}</p>
            </div>
          )}
          <button type="submit" className="btn btn-primary btn-full" disabled={saving}>
            {saving ? t("loading") : t("register_business")}
          </button>
        </form>
      </div>
    </div>
  );
}
