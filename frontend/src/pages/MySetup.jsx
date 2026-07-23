import { useEffect, useState } from "react";
import { getMyStaffProfiles, getServices, updateMyStaff } from "../api/client";
import useStore from "../store/useStore";
import { useT } from "../i18n";
import { SkeletonList } from "../components/Skeleton";
import EmptyState from "../components/EmptyState";
import Toast from "../components/Toast";
import { IconUsers, IconCheck } from "../components/icons";

// Provider self-setup: choose your booking mode (time-slots vs live queue), your
// queue speed, and which of the business's services you offer. Saves to your OWN
// staff record only (backend blocks any privilege change).
export default function MySetup() {
  const { lang, activeBusiness } = useStore();
  const t = useT(lang);
  const [me, setMe] = useState(null);
  const [services, setServices] = useState([]);
  const [form, setForm] = useState({ scheduling_mode: "appointments", queue_avg_minutes: 15, service_ids: [] });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState(null);

  useEffect(() => {
    if (!activeBusiness) return;
    let alive = true;
    (async () => {
      setLoading(true);
      try {
        const [profiles, svc] = await Promise.all([
          getMyStaffProfiles().catch(() => []),
          getServices(activeBusiness.id).catch(() => []),
        ]);
        if (!alive) return;
        const mine = profiles.find((s) => s.business_id === activeBusiness.id) || null;
        setMe(mine);
        setServices(Array.isArray(svc) ? svc : []);
        if (mine) {
          setForm({
            scheduling_mode: mine.scheduling_mode || "appointments",
            queue_avg_minutes: mine.queue_avg_minutes || 15,
            service_ids: mine.service_ids || [],
          });
        }
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, [activeBusiness]);

  const toggleService = (id) =>
    setForm((f) => ({
      ...f,
      service_ids: f.service_ids.includes(id)
        ? f.service_ids.filter((x) => x !== id)
        : [...f.service_ids, id],
    }));

  const save = async () => {
    if (!me) return;
    setSaving(true);
    try {
      const updated = await updateMyStaff(activeBusiness.id, me.id, {
        scheduling_mode: form.scheduling_mode,
        queue_avg_minutes: parseInt(form.queue_avg_minutes) || 15,
        service_ids: form.service_ids,
      });
      setMe(updated);
      setToast({ message: t("saved"), variant: "success" });
    } catch {
      setToast({ message: t("error"), variant: "error" });
    } finally {
      setSaving(false);
    }
  };

  if (!activeBusiness) {
    return <EmptyState icon={<IconUsers size={26} />} title={t("select_business_first")} />;
  }

  return (
    <div className="animate-in">
      <div className="page-header">
        <div>
          <h1 className="page-title">{t("my_setup")}</h1>
          <p className="page-subtitle">{t("my_setup_desc")}</p>
        </div>
      </div>

      {loading ? (
        <SkeletonList count={3} />
      ) : !me ? (
        <div className="card">
          <EmptyState icon={<IconUsers size={24} />} title={t("no_provider_profile")} subtitle={t("no_provider_profile_desc")} />
        </div>
      ) : (
        <div className="card stack" style={{ gap: "var(--space-4)" }}>
          <div className="form-group">
            <label>{t("scheduling_mode")}</label>
            <select value={form.scheduling_mode} onChange={(e) => setForm({ ...form, scheduling_mode: e.target.value })}>
              <option value="appointments">{t("mode_appointments")}</option>
              <option value="queue">{t("mode_queue")}</option>
            </select>
          </div>

          {form.scheduling_mode === "queue" && (
            <div className="form-group">
              <label>{t("queue_avg_minutes")}</label>
              <input
                type="number"
                min={1}
                max={480}
                value={form.queue_avg_minutes}
                onChange={(e) => setForm({ ...form, queue_avg_minutes: e.target.value })}
              />
            </div>
          )}

          <div className="form-group">
            <label>{t("my_services")}</label>
            {services.length === 0 ? (
              <p className="form-hint">{t("missing_services")}</p>
            ) : (
              <div className="stack" style={{ gap: 6 }}>
                {services.map((s) => {
                  const nm = s[`name_${lang}`] || s.name_uz;
                  const on = form.service_ids.includes(s.id);
                  return (
                    <button
                      type="button"
                      key={s.id}
                      className="card-tight row"
                      onClick={() => toggleService(s.id)}
                      style={{ alignItems: "center", gap: 8, cursor: "pointer", borderColor: on ? "var(--brand-400)" : undefined }}
                    >
                      <span className="grow" style={{ fontWeight: on ? 650 : 500 }}>{nm}</span>
                      {on && <IconCheck size={16} style={{ color: "var(--brand-600)" }} />}
                    </button>
                  );
                })}
              </div>
            )}
          </div>

          <button className="btn btn-primary" onClick={save} disabled={saving}>
            {saving ? t("loading") : t("save")}
          </button>
        </div>
      )}

      <Toast toast={toast} onClose={() => setToast(null)} />
    </div>
  );
}
