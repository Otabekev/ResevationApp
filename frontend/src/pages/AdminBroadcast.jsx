import { useEffect, useState } from "react";
import dayjs from "dayjs";
import {
  getBroadcastAudienceCounts, getBroadcasts, createBroadcast,
  sendBroadcastTest, cancelBroadcast,
} from "../api/client";
import useStore from "../store/useStore";
import { useT } from "../i18n";
import { SkeletonList } from "../components/Skeleton";
import EmptyState from "../components/EmptyState";
import Toast from "../components/Toast";
import { IconShield, IconSend, IconUsers, IconStore, IconCheck, IconBan } from "../components/icons";

const AUDIENCES = [
  { key: "all", labelKey: "bc_aud_all", Icon: IconUsers },
  { key: "owners_staff", labelKey: "bc_aud_owners_staff", Icon: IconStore },
  { key: "customers", labelKey: "bc_aud_customers", Icon: IconUsers },
];

const STATUS_BADGE = {
  scheduled: "badge-pending",
  sending: "badge-confirmed",
  done: "badge-completed",
  cancelled: "badge-cancelled_by_business",
};

const MAX_LEN = 4000;

export default function AdminBroadcast() {
  const { lang } = useStore();
  const t = useT(lang);

  const [counts, setCounts] = useState(null);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const [audience, setAudience] = useState("all");
  const [text, setText] = useState("");
  const [scheduleMode, setScheduleMode] = useState(false);
  const [scheduledAt, setScheduledAt] = useState("");
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState(null);

  const load = async () => {
    try {
      const [c, h] = await Promise.all([getBroadcastAudienceCounts(), getBroadcasts()]);
      setCounts(c);
      setHistory(h);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const recipientCount = counts ? counts[audience] ?? 0 : 0;

  const handleTest = async () => {
    if (!text.trim()) { setToast({ message: t("bc_message_required"), variant: "error" }); return; }
    setBusy(true);
    try {
      const res = await sendBroadcastTest(text);
      setToast({ message: res.ok ? t("bc_test_sent") : t("bc_test_failed"), variant: res.ok ? "success" : "error" });
    } catch {
      setToast({ message: t("bc_test_failed"), variant: "error" });
    } finally {
      setBusy(false);
    }
  };

  const handleSend = async () => {
    if (!text.trim()) { setToast({ message: t("bc_message_required"), variant: "error" }); return; }
    if (scheduleMode && !scheduledAt) { setToast({ message: t("bc_when"), variant: "error" }); return; }
    if (!scheduleMode && !window.confirm(t("bc_confirm", { n: recipientCount }))) return;

    setBusy(true);
    try {
      await createBroadcast({
        audience,
        text,
        scheduled_at: scheduleMode ? scheduledAt : null,
      });
      setToast({ message: scheduleMode ? t("bc_scheduled_ok") : t("bc_queued"), variant: "success" });
      setText("");
      setScheduleMode(false);
      setScheduledAt("");
      await load();
    } catch {
      setToast({ message: t("error"), variant: "error" });
    } finally {
      setBusy(false);
    }
  };

  const handleCancel = async (id) => {
    if (!window.confirm(t("bc_cancel_q"))) return;
    try {
      await cancelBroadcast(id);
      await load();
    } catch {
      setToast({ message: t("error"), variant: "error" });
    }
  };

  if (loading) return <SkeletonList count={5} />;
  if (error) {
    return (
      <div className="animate-in">
        <div className="page-header"><h1 className="page-title">{t("broadcast")}</h1></div>
        <div className="card"><EmptyState title={t("error")} subtitle={t("try_again")} /></div>
      </div>
    );
  }

  return (
    <div className="animate-in">
      <div className="page-header">
        <div>
          <div className="eyebrow" style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <IconShield size={13} /> {t("platform")}
          </div>
          <h1 className="page-title" style={{ marginTop: 4 }}>{t("broadcast")}</h1>
          <p style={{ color: "var(--gray-500)", fontSize: "var(--text-sm)", marginTop: 4 }}>{t("bc_subtitle")}</p>
        </div>
      </div>

      {/* Compose */}
      <div className="card">
        {/* Audience */}
        <label className="form-label">{t("bc_audience")}</label>
        <div className="row" style={{ gap: 8, flexWrap: "wrap", marginBottom: "var(--space-4)" }}>
          {AUDIENCES.map(({ key, labelKey, Icon }) => {
            const selected = audience === key;
            return (
              <button
                type="button"
                key={key}
                onClick={() => setAudience(key)}
                className={`btn ${selected ? "btn-primary" : "btn-ghost"}`}
                style={{ display: "flex", alignItems: "center", gap: 8 }}
              >
                <Icon size={15} />
                <span>{t(labelKey)}</span>
                <span className="badge" style={{ background: selected ? "rgba(255,255,255,0.25)" : "var(--gray-100)" }}>
                  {counts ? counts[key] ?? 0 : 0}
                </span>
              </button>
            );
          })}
        </div>

        {/* Message */}
        <label className="form-label">{t("bc_message")}</label>
        <textarea
          className="input"
          rows={5}
          maxLength={MAX_LEN}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={t("bc_message_ph")}
          style={{ resize: "vertical", width: "100%" }}
        />
        <div style={{ textAlign: "right", fontSize: "var(--text-xs)", color: "var(--gray-400)", marginTop: 2 }}>
          {text.length} / {MAX_LEN}
        </div>

        {/* Timing */}
        <label className="form-label" style={{ marginTop: "var(--space-3)" }}>{t("bc_timing")}</label>
        <div className="row" style={{ gap: 8, marginBottom: scheduleMode ? 8 : 0 }}>
          <button type="button" className={`btn btn-sm ${!scheduleMode ? "btn-primary" : "btn-ghost"}`} onClick={() => setScheduleMode(false)}>
            {t("bc_now")}
          </button>
          <button type="button" className={`btn btn-sm ${scheduleMode ? "btn-primary" : "btn-ghost"}`} onClick={() => setScheduleMode(true)}>
            {t("bc_schedule")}
          </button>
        </div>
        {scheduleMode && (
          <input
            type="datetime-local"
            className="input"
            value={scheduledAt}
            onChange={(e) => setScheduledAt(e.target.value)}
            min={dayjs().format("YYYY-MM-DDTHH:mm")}
            style={{ maxWidth: 260 }}
          />
        )}

        {/* Actions */}
        <div className="row" style={{ gap: 8, marginTop: "var(--space-4)", justifyContent: "flex-end", flexWrap: "wrap" }}>
          <button type="button" className="btn btn-ghost" onClick={handleTest} disabled={busy}>
            {t("bc_test")}
          </button>
          <button type="button" className="btn btn-primary" onClick={handleSend} disabled={busy}>
            <IconSend size={15} /> {scheduleMode ? t("bc_schedule") : t("bc_send")}
            {!scheduleMode && ` · ${recipientCount}`}
          </button>
        </div>
      </div>

      {/* History */}
      <div className="card">
        <h3 className="card-title" style={{ marginBottom: "var(--space-3)" }}>{t("bc_history")}</h3>
        {history.length === 0 ? (
          <EmptyState icon={<IconSend size={24} />} title={t("bc_none")} />
        ) : (
          <div className="table-scroll">
            <table className="table">
              <thead>
                <tr>
                  <th>{t("bc_message")}</th>
                  <th>{t("bc_audience")}</th>
                  <th>{t("status")}</th>
                  <th>{t("bc_recipients")}</th>
                  <th>{t("bc_when")}</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {history.map((b) => (
                  <tr key={b.id}>
                    <td style={{ maxWidth: 280 }}>
                      <div style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{b.text}</div>
                    </td>
                    <td style={{ fontSize: "var(--text-sm)" }}>{t(`bc_aud_${b.audience === "owners_staff" ? "owners_staff" : b.audience}`)}</td>
                    <td><span className={`badge ${STATUS_BADGE[b.status] || ""}`}>{t(`bc_status_${b.status}`)}</span></td>
                    <td style={{ fontSize: "var(--text-sm)" }}>
                      {b.status === "done"
                        ? t("bc_delivered", { sent: b.sent_count, failed: b.failed_count })
                        : b.total_recipients}
                    </td>
                    <td style={{ fontSize: "var(--text-sm)", color: "var(--gray-500)" }}>
                      {b.scheduled_at
                        ? dayjs(b.scheduled_at).format("DD.MM HH:mm")
                        : (b.created_at ? dayjs(b.created_at).format("DD.MM HH:mm") : "—")}
                    </td>
                    <td>
                      {b.status === "scheduled" && (
                        <button type="button" className="btn btn-ghost btn-sm" onClick={() => handleCancel(b.id)}>
                          <IconBan size={14} /> {t("cancel")}
                        </button>
                      )}
                      {b.status === "done" && <IconCheck size={15} style={{ color: "var(--success)" }} />}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <Toast toast={toast} onClose={() => setToast(null)} />
    </div>
  );
}
