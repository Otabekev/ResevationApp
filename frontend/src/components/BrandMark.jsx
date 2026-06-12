/**
 * The Qulay Navbat mark — a stacked queue (rounded bars with leading dots),
 * honey "now serving" row on top. Drawn on a transparent background; drop it
 * inside a teal tile (.logo-mark, or the login badge). One source of truth for
 * the in-app logo so the sidebar, app bar and login all stay in sync.
 */
export default function BrandMark({ size = 22 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden focusable="false">
      <circle cx="6" cy="7" r="1.7" fill="#E0982B" />
      <rect x="9" y="5.3" width="9" height="3.4" rx="1.7" fill="#E0982B" />
      <circle cx="6" cy="12" r="1.7" fill="#ffffff" />
      <rect x="9" y="10.3" width="9" height="3.4" rx="1.7" fill="#ffffff" />
      <circle cx="6" cy="17" r="1.7" fill="#ffffff" opacity="0.6" />
      <rect x="9" y="15.3" width="6.5" height="3.4" rx="1.7" fill="#ffffff" opacity="0.6" />
    </svg>
  );
}
