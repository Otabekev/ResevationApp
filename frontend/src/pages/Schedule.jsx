import { useEffect, useState } from "react";
import {
  getWorkingHours, setWorkingHours, getBreaks, addBreak, deleteBreak,
  getBlockedTimes, addBlockedTime, deleteBlockedTime,
} from "../api/client";
import useStore from "../store/useStore";
import { useT } from "../i18n";
import { SkeletonList } from "../components/Skeleton";
import EmptyState from "../components/EmptyState";
import Toast from "../components/Toast";
import dayjs from "dayjs";
import {
  IconClock, IconPlus, IconTrash, IconCoffee, IconBan, IconCopy, IconCheck,
} from "../components/icons";

const DEFAULT_HOURS = Array.from({ length: 7 }, (_, i) => ({
  day_of_week: i, start_time: "09:00", end_time: "18:00", is_day_off: i === 6,
}));

export default function Schedule() {
  const { lang, activeBusiness } = useStore();
  const t = useT(lang);
  const [hours, setHours] = useState(DEFAULT_HOURS);
  const [breaks, setBreaks] = useState([]);
  const [blocked, setBlocked] = useState([]);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(false);
  const [toast, setToast] = useState(null);

  // Break form
  const [breakForm, setBreakForm] = useState({ day_of_week: "", start_time: "13:00", end_time: "14:00", label: "" });
  // Block form
  const [blockForm, setBlockForm] = useState({ blocked_date: "", reason: "" });

  useEffect(() => {
    if (activeBusiness) load();
  }, [activeBusiness]);

  const load = async () => {
    setLoading(true);
    try {
      const [wh, brk, blk] = await Promise.all([
        getWorkingHours(activeBusiness.id),
        getBreaks(activeBusiness.id),
        getBlockedTimes(activeBusiness.id),
      ]);
      if (wh.length > 0) {
        setHours(DEFAULT_HOURS.map((def) => {
          const ex = wh.find((w) => w.day_of_week === def.day_of_week);
          return ex
            ? { day_of_week: ex.day_of_week, start_time: ex.start_time.slice(0, 5), end_time: ex.end_time.slice(0, 5), is_day_off: ex.is_day_off }
            : def;
        }));
      }
      setBreaks(brk);
      setBlocked(blk);
    } catch {
      setToast({ message: t("error"), variant: "error" });
    } finally {
      setLoading(false);
    }
  };

  const updateDay = (idx, field, value) => {
    setHours((prev) => prev.map((h, i) => (i === idx ? { ...h, [field]: value } : h)));
  };

  const copyMondayToAll = () => {
    const mon = hours[0];
    setHours((prev) => prev.map((h, i) => (i === 0 ? h : { ...h, start_time: mon.start_time, end_time: mon.end_time })));
    setToast({ message: t("copied_to_all"), variant: "success" });
  };

  const handleSaveHours = async () => {
    setSaving(true);
    try {
      await setWorkingHours(activeBusiness.id, hours);
      setToast({ message: t("saved"), variant: "success" });
    } catch (err) {
      setToast({ message: err.response?.data?.detail?.[0]?.msg || t("error"), variant: "error" });
    } finally {
      setSaving(false);
    }
  };

  const handleAddBreak = async (e) => {
    e.preventDefault();
    try {
      await addBreak(activeBusiness.id, {
        day_of_week: breakForm.day_of_week === "" ? null : parseInt(breakForm.day_of_week, 10),
        start_time: breakForm.start_time,
        end_time: breakForm.end_time,
        label: breakForm.label || null,
      });
      setBreakForm({ day_of_week: "", start_time: "13:00", end_time: "14:00", label: "" });
      setToast({ message: t("saved"), variant: "success" });
      await load();
    } catch (err) {
      setToast({ message: err.response?.data?.detail?.[0]?.msg || t("error"), variant: "error" });
    }
  };

  const handleDeleteBreak = async (id) => {
    try {
      await deleteBreak(activeBusiness.id, id);
      setBreaks((prev) => prev.filter((b) => b.id !== id));
    } catch {
      setToast({ message: t("error"), variant: "error" });
    }
  };

  const handleAddBlock = async (e) => {
    e.preventDefault();
    try {
      await addBlockedTime(activeBusiness.id, {
        blocked_date: blockForm.blocked_date,
        full_day: true,
        reason: blockForm.reason || null,
      });
      setBlockForm({ blocked_date: "", reason: "" });
      setToast({ message: t("day_blocked"), variant: "success" });
      await load();
    } catch {
      setToast({ message: t("error"), variant: "error" });
    }
  };

  const handleDeleteBlock = async (id) => {
    try {
      await deleteBlockedTime(activeBusiness.id, id);
      setBlocked((prev) => prev.filter((b) => b.id !== id));
    } catch {
      setToast({ message: t("error"), variant: "error" });
    }
  };

  if (!activeBusiness) {
    return <EmptyState icon={<IconClock size={26} />} title={t("select_business_first")} subtitle={t("select_business_desc")} />;
  }

  return (
    <div className="animate-in">
      <div className="page-header">
        <div>
          <h1 className="page-title">{t("schedule")}</h1>
          <p className="page-subtitle">{t("schedule_subtitle")}</p>
        </div>
      </div>

      {loading ? (
        <SkeletonList count={3} />
      ) : (
        <div className="stack stagger" style={{ gap: "var(--space-4)" }}>
          {/* Working hours */}
          <div className="card">
            <div className="row" style={{ justifyContent: "space-between", marginBottom: "var(--space-4)" }}>
              <div>
                <h3 className="card-title">{t("working_hours")}</h3>
                <div className="card-sub">{t("working_hours_sub")}</div>
              </div>
              <button type="button" className="btn btn-ghost btn-sm" onClick={copyMondayToAll} title={t("copy_monday")}>
                <IconCopy size={15} /> {t("copy_monday")}
              </button>
            </div>

            <div className="stack" style={{ gap: 10 }}>
              {hours.map((h, idx) => (
                <div key={h.day_of_week} className="row" style={{ gap: 10, flexWrap: "wrap" }}>
                  <span style={{ width: 36, fontWeight: 750, fontSize: "var(--text-sm)", flexShrink: 0 }}>
                    {t(`wdm_${h.day_of_week}`)}
                  </span>
                  <label className="toggle" style={{ transform: "scale(.92)" }}>
                    <input
                      type="checkbox"
                      checked={!h.is_day_off}
                      onChange={(e) => updateDay(idx, "is_day_off", !e.target.checked)}
                      disabled={saving}
                      aria-label={`${t(`wdm_${h.day_of_week}`)} ${t("day_off")}`}
                    />
                    <span className="toggle-slider"></span>
                  </label>
                  {!h.is_day_off ? (
                    <>
                      <input
                        type="time" value={h.start_time}
                        onChange={(e) => updateDay(idx, "start_time", e.target.value)}
                        disabled={saving} style={{ width: 110, minHeight: 40 }}
                      />
                      <span style={{ color: "var(--gray-400)" }}>–</span>
                      <input
                        type="time" value={h.end_time}
                        onChange={(e) => updateDay(idx, "end_time", e.target.value)}
                        disabled={saving} style={{ width: 110, minHeight: 40 }}
                      />
                    </>
                  ) : (
                    <span className="chip">{t("day_off")}</span>
                  )}
                </div>
              ))}
            </div>

            <button className="btn btn-primary" style={{ marginTop: "var(--space-5)" }} onClick={handleSaveHours} disabled={saving}>
              {saving ? t("loading") : (<><IconCheck size={16} /> {t("save")}</>)}
            </button>
          </div>

          {/* Breaks */}
          <div className="card">
            <div className="row" style={{ gap: 10, marginBottom: "var(--space-4)" }}>
              <span className="stat-icon honey" aria-hidden><IconCoffee size={17} /></span>
              <div>
                <h3 className="card-title">{t("breaks")}</h3>
                <div className="card-sub">{t("breaks_sub")}</div>
              </div>
            </div>

            {breaks.length > 0 && (
              <div className="stack" style={{ gap: 8, marginBottom: "var(--space-4)" }}>
                {breaks.map((b) => (
                  <div key={b.id} className="row card-tight" style={{ background: "var(--gray-50)", borderRadius: "var(--radius-sm)", padding: "10px 12px" }}>
                    <span style={{ fontWeight: 700, fontSize: "var(--text-sm)" }} className="tnum">
                      {b.start_time.slice(0, 5)}–{b.end_time.slice(0, 5)}
                    </span>
                    <span className="chip">
                      {b.day_of_week === null ? t("every_day") : t(`wdm_${b.day_of_week}`)}
                    </span>
                    {b.label && <span className="muted" style={{ fontSize: "var(--text-sm)" }}>{b.label}</span>}
                    <button
                      type="button" className="btn btn-ghost btn-sm btn-icon" style={{ marginLeft: "auto", color: "var(--danger)" }}
                      aria-label={t("delete")} onClick={() => handleDeleteBreak(b.id)}
                    >
                      <IconTrash size={15} />
                    </button>
                  </div>
                ))}
              </div>
            )}

            <form onSubmit={handleAddBreak} className="row" style={{ flexWrap: "wrap", gap: 10 }}>
              <select
                value={breakForm.day_of_week}
                onChange={(e) => setBreakForm({ ...breakForm, day_of_week: e.target.value })}
                style={{ width: "auto", minWidth: 130, flex: 1 }}
                aria-label={t("day")}
              >
                <option value="">{t("every_day")}</option>
                {Array.from({ length: 7 }, (_, i) => (
                  <option key={i} value={i}>{t(`wdm_${i}`)}</option>
                ))}
              </select>
              <input
                type="time" required value={breakForm.start_time}
                onChange={(e) => setBreakForm({ ...breakForm, start_time: e.target.value })}
                style={{ width: 110 }}
              />
              <input
                type="time" required value={breakForm.end_time}
                onChange={(e) => setBreakForm({ ...breakForm, end_time: e.target.value })}
                style={{ width: 110 }}
              />
              <input
                placeholder={t("break_label_ph")} value={breakForm.label} maxLength={100}
                onChange={(e) => setBreakForm({ ...breakForm, label: e.target.value })}
                style={{ flex: 2, minWidth: 140 }}
              />
              <button type="submit" className="btn btn-secondary">
                <IconPlus size={16} /> {t("add_break")}
              </button>
            </form>
          </div>

          {/* Blocked days */}
          <div className="card">
            <div className="row" style={{ gap: 10, marginBottom: "var(--space-4)" }}>
              <span className="stat-icon red" aria-hidden><IconBan size={17} /></span>
              <div>
                <h3 className="card-title">{t("blocked_times")}</h3>
                <div className="card-sub">{t("blocked_sub")}</div>
              </div>
            </div>

            {blocked.length > 0 && (
              <div className="stack" style={{ gap: 8, marginBottom: "var(--space-4)" }}>
                {blocked.map((b) => (
                  <div key={b.id} className="row card-tight" style={{ background: "var(--danger-soft)", borderRadius: "var(--radius-sm)", padding: "10px 12px" }}>
                    <span style={{ fontWeight: 700, fontSize: "var(--text-sm)", color: "var(--danger)" }} className="tnum">
                      {b.blocked_date
                        ? dayjs(b.blocked_date).format("DD.MM.YYYY")
                        : `${dayjs(b.start_datetime).format("DD.MM HH:mm")} – ${dayjs(b.end_datetime).format("HH:mm")}`}
                    </span>
                    {b.full_day && <span className="chip">{t("full_day")}</span>}
                    {b.reason && <span className="muted" style={{ fontSize: "var(--text-sm)" }}>{b.reason}</span>}
                    <button
                      type="button" className="btn btn-ghost btn-sm btn-icon" style={{ marginLeft: "auto", color: "var(--danger)" }}
                      aria-label={t("delete")} onClick={() => handleDeleteBlock(b.id)}
                    >
                      <IconTrash size={15} />
                    </button>
                  </div>
                ))}
              </div>
            )}

            <form onSubmit={handleAddBlock} className="row" style={{ flexWrap: "wrap", gap: 10 }}>
              <input
                type="date" required value={blockForm.blocked_date}
                min={dayjs().format("YYYY-MM-DD")}
                onChange={(e) => setBlockForm({ ...blockForm, blocked_date: e.target.value })}
                style={{ flex: 1, minWidth: 150 }}
              />
              <input
                placeholder={t("reason_optional")} value={blockForm.reason} maxLength={255}
                onChange={(e) => setBlockForm({ ...blockForm, reason: e.target.value })}
                style={{ flex: 2, minWidth: 150 }}
              />
              <button type="submit" className="btn btn-danger-soft">
                <IconBan size={16} /> {t("block_day")}
              </button>
            </form>
          </div>
        </div>
      )}

      <Toast toast={toast} onClose={() => setToast(null)} />
    </div>
  );
}
