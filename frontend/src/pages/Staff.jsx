import { useEffect, useState } from "react";
import { getStaff, createStaff, updateStaff, getServices, setStaffServices, createStaffInvite } from "../api/client";
import useStore from "../store/useStore";
import { useT } from "../i18n";

const EMPTY_FORM = { name: "", phone: "", bio: "", role: "staff", can_set_own_hours: false };

export default function Staff() {
  const { lang, activeBusiness } = useStore();
  const t = useT(lang);
  const [staffList, setStaffList] = useState([]);
  const [services, setServices] = useState([]);
  const [showModal, setShowModal] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [invite, setInvite] = useState(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (activeBusiness) load();
  }, [activeBusiness]);

  const load = async () => {
    const [s, svcs] = await Promise.all([
      getStaff(activeBusiness.id),
      getServices(activeBusiness.id),
    ]);
    setStaffList(s);
    setServices(svcs);
  };

  const openNew = () => { setForm(EMPTY_FORM); setEditing(null); setInvite(null); setShowModal(true); };
  const openEdit = (s) => { setForm(s); setEditing(s.id); setInvite(null); setShowModal(true); };

  const handleSave = async (e) => {
    e.preventDefault();
    if (editing) {
      await updateStaff(activeBusiness.id, editing, form);
    } else {
      await createStaff(activeBusiness.id, form);
    }
    await load();
    setShowModal(false);
  };

  const handleToggleService = async (staffId, serviceId, currentIds) => {
    const newIds = currentIds.includes(serviceId)
      ? currentIds.filter((id) => id !== serviceId)
      : [...currentIds, serviceId];
    await setStaffServices(activeBusiness.id, staffId, newIds);
    await load();
  };

  const handleInvite = async (staffId) => {
    const data = await createStaffInvite(activeBusiness.id, staffId);
    setInvite(data);
  };

  const copyInvite = () => {
    navigator.clipboard.writeText(invite.invite_url);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (!activeBusiness) return <p style={{ padding: 24, color: "var(--gray-500)" }}>Select a business first.</p>;

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">{t("staff")}</h1>
        <button className="btn btn-primary" onClick={openNew}>+ {t("new_staff")}</button>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        {staffList.map((s) => (
          <div key={s.id} className="card">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
              <div>
                <div style={{ fontWeight: 700, fontSize: 16 }}>{s.name}</div>
                {s.phone && <div style={{ fontSize: 13, color: "var(--gray-500)" }}>{s.phone}</div>}
                <div style={{ marginTop: 6, display: "flex", flexWrap: "wrap", gap: 4 }}>
                  {services.map((svc) => (
                    <button
                      key={svc.id}
                      onClick={() => handleToggleService(s.id, svc.id, s.service_ids || [])}
                      style={{
                        padding: "3px 10px", borderRadius: 999, fontSize: 12, border: "1.5px solid",
                        borderColor: (s.service_ids || []).includes(svc.id) ? "var(--primary)" : "var(--gray-300)",
                        background: (s.service_ids || []).includes(svc.id) ? "var(--primary-light)" : "#fff",
                        color: (s.service_ids || []).includes(svc.id) ? "var(--primary)" : "var(--gray-500)",
                        cursor: "pointer",
                      }}
                    >
                      {svc[`name_${lang}`] || svc.name_uz}
                    </button>
                  ))}
                </div>
              </div>
              <div style={{ display: "flex", gap: 6 }}>
                <button className="btn btn-secondary btn-sm" onClick={() => handleInvite(s.id)}>🔗</button>
                <button className="btn btn-secondary btn-sm" onClick={() => openEdit(s)}>{t("edit")}</button>
              </div>
            </div>
            {!s.user_id && (
              <div style={{ marginTop: 8, fontSize: 12, color: "var(--warning)" }}>
                ⚠️ Not joined yet
              </div>
            )}
          </div>
        ))}
      </div>

      {invite && (
        <div className="card" style={{ marginTop: 16, background: "var(--primary-light)", border: "1.5px solid var(--primary)" }}>
          <div style={{ fontWeight: 600, marginBottom: 8 }}>{t("invite_link")}</div>
          <div style={{ fontSize: 13, wordBreak: "break-all", marginBottom: 10 }}>{invite.invite_url}</div>
          <button className="btn btn-primary btn-sm" onClick={copyInvite}>
            {copied ? t("copied") : t("copy")}
          </button>
        </div>
      )}

      {showModal && (
        <div className="modal-overlay" onClick={(e) => e.target === e.currentTarget && setShowModal(false)}>
          <div className="modal">
            <div className="modal-header">
              <h3 className="modal-title">{editing ? t("edit") : t("new_staff")}</h3>
              <button className="modal-close" onClick={() => setShowModal(false)}>×</button>
            </div>
            <form onSubmit={handleSave}>
              <div className="form-group">
                <label>Name *</label>
                <input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
              </div>
              <div className="form-group">
                <label>{t("phone")}</label>
                <input value={form.phone || ""} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
              </div>
              <div className="form-group">
                <label>Role</label>
                <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
                  <option value="staff">Staff</option>
                  <option value="manager">Manager</option>
                </select>
              </div>
              <button type="submit" className="btn btn-primary btn-full">{t("save")}</button>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
