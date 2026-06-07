import { useEffect, useState } from "react";
import { getWorkingHours, setWorkingHours, getBreaks, addBreak, deleteBreak, addBlockedTime } from "../api/client";
import useStore from "../store/useStore";
import { useT } from "../i18n";

const DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];

const DEFAULT_HOURS = DAYS.map((_, i) => ({
  day_of_week: i,
  start_time: "09:00",
  end_time: "18:00",
  is_day_off: i >= 5,
}));

export default function Schedule() {
  const { lang, activeBusiness } = useStore();
  const t = useT(lang);
  const [hours, setHours] = useState(DEFAULT_HOURS);
  const [breaks, setBreaks] = useState([]);
  const [saving, setSaving] = useState(false);
  const [blockDate, setBlockDate] = useState("");
  const [blockReason, setBlockReason] = useState("");

  useEffect(() => {
    if (activeBusiness) load();
  }, [activeBusiness]);

  const load = async () => {
    const [wh, brk] = await Promise.all([
      getWorkingHours(activeBusiness.id),
      getBreaks(activeBusiness.id),
    ]);
    if (wh.length > 0) {
      const filled = DEFAULT_HOURS.map((def) => {
        const existing = wh.find((w) => w.day_of_week === def.day_of_week);
        return existing || def;
      });
      setHours(filled);
    }
    setBreaks(brk);
  };

  const updateDay = (idx, field, value) => {
    setHours((prev) => prev.map((h, i) => i === idx ? { ...h, [field]: value } : h));
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await setWorkingHours(activeBusiness.id, hours);
      alert("Saved!");
    } catch {
      alert("Error saving");
    } finally {
      setSaving(false);
    }
  };

  const handleAddBlock = async (e) => {
    e.preventDefault();
    await addBlockedTime(activeBusiness.id, { blocked_date: blockDate, full_day: true, reason: blockReason });
    setBlockDate("");
    setBlockReason("");
    alert("Day blocked!");
  };

  if (!activeBusiness) return <p style={{ padding: 24, color: "var(--gray-500)" }}>Select a business first.</p>;

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">{t("schedule")}</h1>
        <button className="btn btn-primary" onClick={handleSave} disabled={saving}>
          {saving ? t("loading") : t("save")}
        </button>
      </div>

      {/* Working hours */}
      <div className="card" style={{ marginBottom: 16 }}>
        <h3 style={{ fontWeight: 700, marginBottom: 14 }}>{t("working_hours")}</h3>
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {hours.map((h, idx) => (
            <div key={idx} style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <span style={{ width: 36, fontWeight: 600, fontSize: 14 }}>{t(DAYS[idx])}</span>
              <label className="toggle">
                <input
                  type="checkbox"
                  checked={!h.is_day_off}
                  onChange={(e) => updateDay(idx, "is_day_off", !e.target.checked)}
                />
                <span className="toggle-slider"></span>
              </label>
              {!h.is_day_off ? (
                <>
                  <input type="time" value={h.start_time} onChange={(e) => updateDay(idx, "start_time", e.target.value)}
                    style={{ width: 110 }} />
                  <span style={{ color: "var(--gray-400)" }}>—</span>
                  <input type="time" value={h.end_time} onChange={(e) => updateDay(idx, "end_time", e.target.value)}
                    style={{ width: 110 }} />
                </>
              ) : (
                <span style={{ fontSize: 13, color: "var(--gray-400)" }}>{t("day_off")}</span>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Block a day */}
      <div className="card">
        <h3 style={{ fontWeight: 700, marginBottom: 14 }}>{t("block_time")}</h3>
        <form onSubmit={handleAddBlock} style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          <input type="date" value={blockDate} onChange={(e) => setBlockDate(e.target.value)}
            required style={{ flex: 1, minWidth: 150 }} />
          <input placeholder="Reason (optional)" value={blockReason}
            onChange={(e) => setBlockReason(e.target.value)} style={{ flex: 2, minWidth: 150 }} />
          <button type="submit" className="btn btn-danger">{t("block_time")}</button>
        </form>
      </div>
    </div>
  );
}
