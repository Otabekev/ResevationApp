import { useState } from "react";
import useStore from "../store/useStore";
import { useT } from "../i18n";
import { IconMapPin, IconX, IconCheck } from "./icons";

/**
 * Owner sets their business location. Two ways in, no map-library dependency:
 *  - "Use my current location" (browser geolocation — perfect when standing in
 *    the shop during onboarding).
 *  - Paste a Google Maps link or raw "lat, lng" (for setting it from elsewhere).
 * A free OpenStreetMap embed previews the pin. The coordinates flow up to the
 * business form and get saved like any other field; the bot then sends them to
 * customers as a native Telegram location.
 */

function round(n) {
  return Math.round(n * 1e6) / 1e6;
}

// Accepts "41.0, 71.6", a Google Maps "@41.0,71.6,..." link, or a "!3d..!4d.." link.
function parseCoords(text) {
  if (!text) return null;
  const at = text.match(/@(-?\d{1,3}\.\d+),(-?\d{1,3}\.\d+)/);
  if (at) return { lat: parseFloat(at[1]), lng: parseFloat(at[2]) };
  const d3d4 = text.match(/!3d(-?\d{1,3}\.\d+)!4d(-?\d{1,3}\.\d+)/);
  if (d3d4) return { lat: parseFloat(d3d4[1]), lng: parseFloat(d3d4[2]) };
  const pair = text.match(/(-?\d{1,2}\.\d{3,}|-?\d{1,3}\.\d{3,})\s*,\s*(-?\d{1,3}\.\d{3,})/);
  if (pair) return { lat: parseFloat(pair[1]), lng: parseFloat(pair[2]) };
  return null;
}

function inRange(lat, lng) {
  return lat >= -90 && lat <= 90 && lng >= -180 && lng <= 180;
}

export default function LocationPicker({ latitude, longitude, onChange }) {
  const { lang } = useStore();
  const t = useT(lang);
  const [busy, setBusy] = useState(false);
  const [paste, setPaste] = useState("");
  const [err, setErr] = useState("");

  const has = latitude != null && longitude != null;

  const useCurrent = () => {
    setErr("");
    if (!navigator.geolocation) {
      setErr(t("geo_unavailable"));
      return;
    }
    setBusy(true);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        onChange(round(pos.coords.latitude), round(pos.coords.longitude));
        setBusy(false);
      },
      () => {
        setErr(t("geo_denied"));
        setBusy(false);
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
    );
  };

  const applyPaste = () => {
    const c = parseCoords(paste);
    if (!c || !inRange(c.lat, c.lng)) {
      setErr(t("location_invalid"));
      return;
    }
    setErr("");
    setPaste("");
    onChange(round(c.lat), round(c.lng));
  };

  const clear = () => {
    setErr("");
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

      <div className="row" style={{ gap: 8, flexWrap: "wrap", marginBottom: "var(--space-3)" }}>
        <button type="button" className="btn btn-secondary btn-sm" onClick={useCurrent} disabled={busy}>
          <IconMapPin size={15} /> {busy ? t("locating") : t("use_my_location")}
        </button>
        {has && (
          <button type="button" className="btn btn-ghost btn-sm" onClick={clear}>
            <IconX size={14} /> {t("remove_location")}
          </button>
        )}
      </div>

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

      <div className="row" style={{ gap: 8, alignItems: "stretch" }}>
        <input
          value={paste}
          onChange={(e) => setPaste(e.target.value)}
          placeholder={t("location_paste_ph")}
          aria-label={t("location_paste_ph")}
          style={{ flex: 1 }}
          onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); applyPaste(); } }}
        />
        <button type="button" className="btn btn-secondary" onClick={applyPaste} disabled={!paste.trim()}>
          {t("apply")}
        </button>
      </div>
      {err && <p className="form-error" style={{ marginTop: 6 }}>{err}</p>}
    </div>
  );
}
