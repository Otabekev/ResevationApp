import { useEffect, useState } from "react";
import { getMyStaffProfiles, getStaffWorkingHours, setStaffWorkingHours } from "../api/client";
import useStore from "../store/useStore";
import { useT } from "../i18n";
import { SkeletonList } from "../components/Skeleton";
import EmptyState from "../components/EmptyState";
import Toast from "../components/Toast";
import { IconUsers } from "../components/icons";

// Weekday names inline (0=Mon…6=Sun) so we don't need 21 extra i18n keys.
const DOW = {
  uz: ["Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba", "Yakshanba"],
  ru: ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"],
  en: ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
};

// Provider self-schedule: a simple weekly working-hours editor scoped to their own
// staff record. Time off / holidays stay owner-managed for now.
export default function MySchedule() {
  const { lang, activeBusiness } = useStore();
  const t = useT(lang);
  const [me, setMe] = useState(null);
  const [rows, setRows] = useState(null); // array of 7 {start_time,end_time,is_day_off}
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState(null);

  useEffect(() => {
    if (!activeBusiness) return;
    let alive = true;
    (async () => {
      setLoading(true);
      try {
        const profiles = await getMyStaffProfiles().catch(() => []);
        const mine = profiles.find((s) => s.business_id === activeBusiness.id) || null;
        if (!alive) return;
        setMe(mine);
        let hours = [];
        if (mine) hours = await getStaffWorkingHours(activeBusiness.id, mine.id).catch(() => []);
        const byDay = {};
        for (const h of hours) byDay[h.day_of_week] = h;
        const built = Array.from({ length: 7 }, (_, d) => {
          const h = byDay[d];
          return h
            ? {
                start_time: (h.start_time || "09:00").slice(0, 5),
                end_time: (h.end_time || "18:00").slice(0, 5),
                is_day_off: !!h.is_day_off,
              }
            : { start_time: "09:00", end_time: "18:00", is_day_off: true }; // no row → off
        });
        if (alive) setRows(built);
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, [activeBusiness]);

  const update = (d, patch) => setRows((r) => r.map((row, i) => (i === d ? { ...row, ...patch } : row)));

  const save = async () => {
    if (!me || !rows) return;
    setSaving(true);
    try {
      const hours = rows.map((row, d) => ({
        day_of_week: d,
        start_time: row.start_time,
        end_time: row.end_time,
        is_day_off: row.is_day_off,
      }));
      await setStaffWorkingHours(activeBusiness.id, me.id, hours);
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
          <h1 className="page-title">{t("my_working_hours")}</h1>
          <p className="page-subtitle">{t("my_schedule_desc")}</p>
        </div>
      </div>

      {loading || !rows ? (
        <SkeletonList count={4} />
      ) : !me ? (
        <div className="card">
          <EmptyState icon={<IconUsers size={24} />} title={t("no_provider_profile")} subtitle={t("no_provider_profile_desc")} />
        </div>
      ) : (
        <div className="card stack" style={{ gap: 10 }}>
          {rows.map((row, d) => (
            <div key={d} className="card-tight row" style={{ alignItems: "center", gap: 8, flexWrap: "wrap" }}>
              <span className="grow" style={{ fontWeight: 600, minWidth: 96 }}>{(DOW[lang] || DOW.en)[d]}</span>
              {row.is_day_off ? (
                <span className="chip" style={{ color: "var(--gray-500)" }}>{t("day_off")}</span>
              ) : (
                <span className="row" style={{ gap: 6, alignItems: "center" }}>
                  <input type="time" value={row.start_time} onChange={(e) => update(d, { start_time: e.target.value })} />
                  <span>—</span>
                  <input type="time" value={row.end_time} onChange={(e) => update(d, { end_time: e.target.value })} />
                </span>
              )}
              <label className="row" style={{ gap: 5, alignItems: "center", cursor: "pointer", marginLeft: "auto" }}>
                <input type="checkbox" checked={row.is_day_off} onChange={(e) => update(d, { is_day_off: e.target.checked })} />
                {t("day_off")}
              </label>
            </div>
          ))}
          <button className="btn btn-primary" onClick={save} disabled={saving}>
            {saving ? t("loading") : t("save")}
          </button>
        </div>
      )}

      <Toast toast={toast} onClose={() => setToast(null)} />
    </div>
  );
}
