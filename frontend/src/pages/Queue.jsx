import { useEffect, useMemo, useRef, useState } from "react";
import { getStaff, getQueue, addQueueWalkin, queueCall, queueDone, queueNoShow } from "../api/client";
import useStore from "../store/useStore";
import { useT } from "../i18n";
import { SkeletonList } from "../components/Skeleton";
import EmptyState from "../components/EmptyState";
import Modal from "../components/Modal";
import Toast from "../components/Toast";
import { IconPlus, IconUsers, IconCheck, IconX, IconPhone, IconTelegram, IconClock } from "../components/icons";

export default function Queue() {
  const { lang, activeBusiness } = useStore();
  const t = useT(lang);
  const [staff, setStaff] = useState([]);
  const [entries, setEntries] = useState([]);
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState(null);
  const [showAdd, setShowAdd] = useState(false);
  const [addForm, setAddForm] = useState({ staff_id: "", customer_name: "", customer_phone: "" });
  const [saving, setSaving] = useState(false);
  const pollRef = useRef(null);

  // Only providers running a live queue.
  const queueStaff = useMemo(() => staff.filter((s) => s.scheduling_mode === "queue"), [staff]);

  const loadStaff = async () => {
    try { setStaff(await getStaff(activeBusiness.id)); } catch { /* keep old */ }
  };
  const loadQueue = async () => {
    try { setEntries(await getQueue(activeBusiness.id)); } catch { /* keep old */ }
  };

  useEffect(() => {
    if (!activeBusiness) return;
    setLoading(true);
    Promise.all([loadStaff(), loadQueue()]).finally(() => setLoading(false));
    // Light poll (15s) only while this page is open — cheap, keeps the desk live.
    pollRef.current = setInterval(loadQueue, 15000);
    return () => clearInterval(pollRef.current);
  }, [activeBusiness]);

  const act = async (fn, entryId) => {
    try {
      await fn(activeBusiness.id, entryId);
      await loadQueue();
    } catch {
      setToast({ message: t("error"), variant: "error" });
    }
  };

  const handleAddWalkin = async (e) => {
    e.preventDefault();
    if (!addForm.staff_id) { setToast({ message: t("pick_staff"), variant: "error" }); return; }
    setSaving(true);
    try {
      await addQueueWalkin(activeBusiness.id, {
        staff_id: parseInt(addForm.staff_id),
        customer_name: addForm.customer_name,
        customer_phone: addForm.customer_phone || null,
      });
      setShowAdd(false);
      setAddForm({ staff_id: "", customer_name: "", customer_phone: "" });
      await loadQueue();
      setToast({ message: t("saved"), variant: "success" });
    } catch {
      setToast({ message: t("error"), variant: "error" });
    } finally {
      setSaving(false);
    }
  };

  if (!activeBusiness) {
    return <EmptyState icon={<IconUsers size={26} />} title={t("select_business_first")} subtitle={t("select_business_desc")} />;
  }

  const byStaff = (sid) => entries.filter((e) => e.staff_id === sid);

  return (
    <div className="animate-in">
      <div className="page-header">
        <div>
          <h1 className="page-title">{t("queue")}</h1>
          <p className="page-subtitle">{t("queue_subtitle")}</p>
        </div>
        {queueStaff.length > 0 && (
          <button className="btn btn-primary" onClick={() => setShowAdd(true)}>
            <IconPlus size={17} /> {t("add_walkin")}
          </button>
        )}
      </div>

      {loading ? (
        <SkeletonList count={3} />
      ) : queueStaff.length === 0 ? (
        <div className="card">
          <EmptyState icon={<IconUsers size={24} />} title={t("no_queue_staff_title")} subtitle={t("no_queue_staff_desc")} />
        </div>
      ) : (
        <div className="stack" style={{ gap: "var(--space-4)" }}>
          {queueStaff.map((s) => {
            const line = byStaff(s.id);
            return (
              <div key={s.id} className="card">
                <div className="row" style={{ justifyContent: "space-between", marginBottom: "var(--space-3)" }}>
                  <span style={{ fontWeight: 750, fontSize: "var(--text-md)" }}>{s.name}</span>
                  <span className="chip"><IconUsers size={12} /> {line.filter((e) => e.status === "waiting").length}</span>
                </div>
                {line.length === 0 ? (
                  <p className="form-hint">{t("queue_empty")}</p>
                ) : (
                  <div className="stack" style={{ gap: 8 }}>
                    {line.map((e) => (
                      <div key={e.id} className="card-tight row" style={{ gap: "var(--space-2)", alignItems: "center",
                        borderColor: e.status === "called" ? "var(--brand-400)" : undefined }}>
                        <span className="avatar" aria-hidden style={{ flexShrink: 0 }}>
                          {e.status === "called" ? "▶" : (e.position ?? "•")}
                        </span>
                        <div className="grow" style={{ minWidth: 0 }}>
                          <div style={{ fontWeight: 650 }}>
                            {e.customer_name}
                            {e.has_telegram && <IconTelegram size={12} style={{ marginLeft: 6, color: "var(--brand-500)" }} />}
                          </div>
                          {e.customer_phone && (
                            <div style={{ fontSize: "var(--text-xs)", color: "var(--gray-500)" }}>
                              <IconPhone size={11} /> {e.customer_phone}
                            </div>
                          )}
                        </div>
                        {e.status === "waiting" && (
                          <button className="btn btn-primary btn-sm" onClick={() => act(queueCall, e.id)}>{t("queue_call")}</button>
                        )}
                        {e.status === "called" && (
                          <button className="btn btn-secondary btn-sm" onClick={() => act(queueDone, e.id)}>
                            <IconCheck size={14} /> {t("queue_done")}
                          </button>
                        )}
                        <button className="btn btn-sm btn-icon" title={t("queue_no_show")} aria-label={t("queue_no_show")}
                          onClick={() => act(queueNoShow, e.id)} style={{ color: "var(--danger)", borderColor: "var(--danger)" }}>
                          <IconX size={14} />
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {showAdd && (
        <Modal title={t("add_walkin")} onClose={() => setShowAdd(false)}>
          <form onSubmit={handleAddWalkin}>
            <div className="form-group">
              <label>{t("staff")} *</label>
              <select required value={addForm.staff_id} onChange={(e) => setAddForm({ ...addForm, staff_id: e.target.value })}>
                <option value="">—</option>
                {queueStaff.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            </div>
            <div className="form-group">
              <label>{t("full_name")} *</label>
              <input required maxLength={255} value={addForm.customer_name}
                onChange={(e) => setAddForm({ ...addForm, customer_name: e.target.value })} />
            </div>
            <div className="form-group">
              <label>{t("phone")}</label>
              <input type="tel" maxLength={20} value={addForm.customer_phone} placeholder="+998 90 123 45 67"
                onChange={(e) => setAddForm({ ...addForm, customer_phone: e.target.value })} />
            </div>
            <button type="submit" className="btn btn-primary btn-full" disabled={saving}>
              {saving ? t("loading") : t("save")}
            </button>
          </form>
        </Modal>
      )}

      <Toast toast={toast} onClose={() => setToast(null)} />
    </div>
  );
}
