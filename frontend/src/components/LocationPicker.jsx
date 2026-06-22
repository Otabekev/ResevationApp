import { useEffect, useRef, useState } from "react";
import useStore from "../store/useStore";
import { useT } from "../i18n";
import { pollLocationShare } from "../api/client";
import { IconMapPin, IconX, IconCheck, IconTelegram } from "./icons";

/**
 * Owner sets their business location via Telegram — the easiest path for this
 * audience and the only one that's reliable on a phone:
 *  1. Tapping the button opens the bot at t.me/<bot>?start=setloc_<nonce>.
 *  2. The owner taps Telegram's native "Send location" (or 📎 → Location).
 *  3. The bot posts the coords to the backend keyed by the nonce; we poll and
 *     drop them into the form. Same handshake as the web-login flow.
 * Browser geolocation/paste were dropped: geolocation needs HTTPS (blocked on
 * the http PWA + Telegram's in-app browser) and shared map links are usually
 * short URLs with no coordinates in them. A free OpenStreetMap embed previews
 * the pin; the coordinates flow up to the business form like any other field.
 */

const BOT_USERNAME = import.meta.env.VITE_TELEGRAM_BOT_USERNAME || "QulayNavbat_bot";
const POLL_INTERVAL_MS = 2000;
const POLL_TIMEOUT_MS = 300000; // 5 min — matches the backend store TTL

function round(n) {
  return Math.round(n * 1e6) / 1e6;
}

// High-entropy, URL-safe nonce (hex) — shared between the bot deep-link and the poll.
function makeNonce() {
  const a = new Uint8Array(16);
  (window.crypto || window.msCrypto).getRandomValues(a);
  return Array.from(a, (b) => b.toString(16).padStart(2, "0")).join("");
}

export default function LocationPicker({ latitude, longitude, onChange }) {
  const { lang } = useStore();
  const t = useT(lang);
  const [waiting, setWaiting] = useState(false);
  const [err, setErr] = useState("");

  // One nonce per mount; the deep-link and the poll share it. Reusing it across
  // retries is fine — the backend store is keyed by nonce and self-expires.
  const [nonce] = useState(makeNonce);
  const tgUrl = `https://t.me/${BOT_USERNAME}?start=setloc_${nonce}`;
  const pollRef = useRef(null);
  const startedRef = useRef(0);

  const has = latitude != null && longitude != null;

  const stopPolling = () => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  };

  useEffect(() => stopPolling, []);

  // The <a> opens Telegram (a real user gesture, so it isn't popup-blocked);
  // this just starts polling for the coordinates to come back.
  const begin = () => {
    setErr("");
    setWaiting(true);
    startedRef.current = Date.now();
    stopPolling();
    pollRef.current = setInterval(async () => {
      if (Date.now() - startedRef.current > POLL_TIMEOUT_MS) {
        stopPolling();
        setWaiting(false);
        setErr(t("location_timeout"));
        return;
      }
      try {
        const res = await pollLocationShare(nonce);
        if (res.status === "ok") {
          stopPolling();
          setWaiting(false);
          onChange(round(res.latitude), round(res.longitude));
        }
      } catch {
        /* keep polling — transient network errors are expected */
      }
    }, POLL_INTERVAL_MS);
  };

  const clear = () => {
    setErr("");
    stopPolling();
    setWaiting(false);
    onChange(null, null);
  };

  // OpenStreetMap embed — free, no key. Small bbox around the pin.
  const d = 0.004;
  const mapSrc = has
    ? `https://www.openstreetmap.org/export/embed.html?bbox=${longitude - d}%2C${latitude - d}%2C${longitude + d}%2C${latitude + d}&layer=mapnik&marker=${latitude}%2C${longitude}`
    : null;

  return (
    <div className="form-group" style={{ marginBottom: 0 }}>
      <label style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <IconMapPin size={15} /> {t("business_location")}
      </label>
      <p className="form-hint" style={{ marginTop: 0, marginBottom: "var(--space-3)" }}>
        {t("location_hint")}
      </p>

      {has && (
        <div
          style={{
            borderRadius: "var(--radius-sm)", overflow: "hidden",
            border: "1px solid var(--line)", marginBottom: "var(--space-3)",
          }}
        >
          <iframe
            title={t("business_location")}
            src={mapSrc}
            style={{ width: "100%", height: 190, border: 0, display: "block" }}
            loading="lazy"
          />
          <div
            className="row"
            style={{
              justifyContent: "space-between", padding: "8px 12px",
              background: "var(--brand-50)", fontSize: "var(--text-xs)",
              color: "var(--brand-800)", fontWeight: 650,
            }}
          >
            <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <IconCheck size={13} /> {t("location_set")}
            </span>
            <span className="tnum" style={{ color: "var(--gray-500)" }}>
              {latitude.toFixed(5)}, {longitude.toFixed(5)}
            </span>
          </div>
        </div>
      )}

      <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
        <a
          href={tgUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="btn btn-secondary btn-sm"
          onClick={begin}
        >
          <IconTelegram size={15} /> {has ? t("change_location") : t("set_location_telegram")}
        </a>
        {has && (
          <button type="button" className="btn btn-ghost btn-sm" onClick={clear}>
            <IconX size={14} /> {t("remove_location")}
          </button>
        )}
      </div>

      {waiting && (
        <div
          style={{
            marginTop: "var(--space-3)", padding: "var(--space-3) var(--space-4)",
            background: "var(--brand-50)", border: "1px solid var(--brand-100)",
            borderRadius: "var(--radius-sm)", display: "flex", alignItems: "center", gap: 12,
          }}
        >
          <span
            aria-hidden
            style={{
              width: 18, height: 18, borderRadius: "50%", flexShrink: 0,
              border: "2.5px solid var(--brand-200)", borderTopColor: "var(--brand-600)",
              animation: "spin 0.9s linear infinite",
            }}
          />
          <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
          <div>
            <div style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: "var(--brand-800)" }}>
              {t("location_waiting")}
            </div>
            <a href={tgUrl} target="_blank" rel="noopener noreferrer" style={{ fontSize: "var(--text-xs)", fontWeight: 650 }}>
              {t("location_open_telegram")}
            </a>
          </div>
        </div>
      )}

      {err && <p className="form-error" style={{ marginTop: 6 }}>{err}</p>}
    </div>
  );
}
