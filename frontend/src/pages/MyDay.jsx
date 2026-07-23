import { useEffect, useState } from "react";
import { getMyStaffProfiles, getBookings, getQueue } from "../api/client";
import useStore from "../store/useStore";
import { useT } from "../i18n";
import { SkeletonList } from "../components/Skeleton";
import EmptyState from "../components/EmptyState";
import { IconCalendar, IconClock, IconUsers } from "../components/icons";

function todayISO() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
function fmtDate(iso) {
  try {
    const [, m, dd] = iso.split("-");
    return `${dd}.${m}`;
  } catch {
    return iso;
  }
}

// Provider "home": their name, a live-queue snapshot (if they run one), and their
// upcoming appointments — all self-scoped by the backend, no roster/analytics calls.
export default function MyDay() {
  const { lang, activeBusiness, user } = useStore();
  const t = useT(lang);
  const [me, setMe] = useState(null);
  const [bookings, setBookings] = useState([]);
  const [queue, setQueue] = useState([]);
  const [loading, setLoading] = useState(true);

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
        const [bk, q] = await Promise.all([
          getBookings(activeBusiness.id, { date_from: todayISO() }).catch(() => []),
          mine && mine.scheduling_mode === "queue"
            ? getQueue(activeBusiness.id).catch(() => [])
            : Promise.resolve([]),
        ]);
        if (!alive) return;
        setBookings(Array.isArray(bk) ? bk : []);
        setQueue(Array.isArray(q) ? q : []);
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, [activeBusiness]);

  if (!activeBusiness) {
    return <EmptyState icon={<IconUsers size={26} />} title={t("select_business_first")} />;
  }

  const waiting = queue.filter((e) => e.status === "waiting").length;

  return (
    <div className="animate-in">
      <div className="page-header">
        <div>
          <h1 className="page-title">{t("my_day")}</h1>
          <p className="page-subtitle">{me?.name || user?.name}</p>
        </div>
      </div>

      {loading ? (
        <SkeletonList count={4} />
      ) : (
        <div className="stack" style={{ gap: "var(--space-4)" }}>
          {me?.scheduling_mode === "queue" && (
            <div className="card row" style={{ justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontWeight: 650, display: "flex", alignItems: "center", gap: 6 }}>
                <IconUsers size={16} /> {t("queue")}
              </span>
              <span className="chip">{waiting}</span>
            </div>
          )}

          <div className="card">
            <div className="row" style={{ justifyContent: "space-between", marginBottom: "var(--space-3)" }}>
              <span style={{ fontWeight: 750 }}>{t("upcoming")}</span>
              <IconCalendar size={16} style={{ color: "var(--gray-400)" }} />
            </div>
            {bookings.length === 0 ? (
              <p className="form-hint">{t("no_upcoming")}</p>
            ) : (
              <div className="stack" style={{ gap: 8 }}>
                {bookings.slice(0, 40).map((b) => {
                  const svc = b[`service_name_${lang}`] || b.service_name_uz;
                  return (
                    <div key={b.id} className="card-tight row" style={{ alignItems: "center", gap: 8 }}>
                      <span className="avatar" aria-hidden style={{ flexShrink: 0 }}>
                        <IconClock size={14} />
                      </span>
                      <div className="grow" style={{ minWidth: 0 }}>
                        <div style={{ fontWeight: 650 }}>{b.customer_name || "—"}</div>
                        <div style={{ fontSize: "var(--text-xs)", color: "var(--gray-500)" }}>
                          {fmtDate(b.booking_date)} · {(b.start_time || "").slice(0, 5)}
                          {svc ? ` · ${svc}` : ""}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
