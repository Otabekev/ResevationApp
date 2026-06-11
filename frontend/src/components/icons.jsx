/**
 * Rezerv icon set — hand-tuned 24px stroke icons, drawn for this product.
 * All icons inherit `currentColor` and scale via the `size` prop, so they
 * recolor with text and stay crisp on any DPI (no emoji, no icon font).
 */

const base = {
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.8,
  strokeLinecap: "round",
  strokeLinejoin: "round",
};

function Icon({ size = 20, children, ...rest }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      aria-hidden="true"
      focusable="false"
      {...base}
      {...rest}
    >
      {children}
    </svg>
  );
}

/* ── Navigation ─────────────────────────────────────────────────────────── */

export const IconHome = (p) => (
  <Icon {...p}>
    <path d="M3 10.2 12 3l9 7.2" />
    <path d="M5 9.5V21h14V9.5" />
    <path d="M9.5 21v-6h5v6" />
  </Icon>
);

export const IconCalendar = (p) => (
  <Icon {...p}>
    <rect x="3" y="4.5" width="18" height="16" rx="2.5" />
    <path d="M3 9.5h18" />
    <path d="M8 2.5v4M16 2.5v4" />
    <path d="M7.5 13.5h3M13.5 13.5h3M7.5 17h3" />
  </Icon>
);

export const IconScissors = (p) => (
  <Icon {...p}>
    <circle cx="6" cy="6.5" r="2.6" />
    <circle cx="6" cy="17.5" r="2.6" />
    <path d="M8.2 8.3 20 19M8.2 15.7 20 5" />
  </Icon>
);

export const IconUsers = (p) => (
  <Icon {...p}>
    <circle cx="9" cy="8" r="3.4" />
    <path d="M2.8 20c.7-3.4 3.2-5.2 6.2-5.2s5.5 1.8 6.2 5.2" />
    <path d="M15.5 4.9a3.4 3.4 0 0 1 0 6.2" />
    <path d="M17.8 14.9c1.8.8 3 2.3 3.4 4.6" />
  </Icon>
);

export const IconClock = (p) => (
  <Icon {...p}>
    <circle cx="12" cy="12" r="8.5" />
    <path d="M12 7.5V12l3 2.2" />
  </Icon>
);

export const IconChart = (p) => (
  <Icon {...p}>
    <path d="M4 20V4" />
    <path d="M4 20h16" />
    <path d="M8.5 16v-5M13 16V7.5M17.5 16v-3" />
  </Icon>
);

export const IconSettings = (p) => (
  <Icon {...p}>
    <circle cx="12" cy="12" r="3.2" />
    <path d="M19.2 12a7.2 7.2 0 0 0-.1-1.2l2-1.5-2-3.4-2.3.9a7.3 7.3 0 0 0-2-1.2L14.4 3h-4l-.4 2.6a7.3 7.3 0 0 0-2 1.2l-2.3-1-2 3.5 2 1.5a7.2 7.2 0 0 0 0 2.4l-2 1.5 2 3.4 2.3-.9a7.3 7.3 0 0 0 2 1.2l.4 2.6h4l.4-2.6a7.3 7.3 0 0 0 2-1.2l2.3.9 2-3.4-2-1.5c.06-.4.1-.8.1-1.2Z" />
  </Icon>
);

export const IconShield = (p) => (
  <Icon {...p}>
    <path d="M12 3 5 5.8v5.4c0 4.5 3 7.8 7 9.8 4-2 7-5.3 7-9.8V5.8L12 3Z" />
    <path d="m9 11.8 2.2 2.2L15.5 9.5" />
  </Icon>
);

/* ── Actions ────────────────────────────────────────────────────────────── */

export const IconPlus = (p) => (
  <Icon {...p}>
    <path d="M12 5v14M5 12h14" />
  </Icon>
);

export const IconX = (p) => (
  <Icon {...p}>
    <path d="m6 6 12 12M18 6 6 18" />
  </Icon>
);

export const IconCheck = (p) => (
  <Icon {...p}>
    <path d="m4.5 12.5 5 5L19.5 7" />
  </Icon>
);

export const IconBan = (p) => (
  <Icon {...p}>
    <circle cx="12" cy="12" r="8.5" />
    <path d="M6 6.5 18 17.5" />
  </Icon>
);

export const IconEdit = (p) => (
  <Icon {...p}>
    <path d="M4 20h4.5L20 8.5a2.1 2.1 0 0 0-3-3L5.5 17 4 20Z" />
    <path d="m14.5 7 3 3" />
  </Icon>
);

export const IconTrash = (p) => (
  <Icon {...p}>
    <path d="M4.5 6.5h15" />
    <path d="M9 6V4.5h6V6" />
    <path d="M6.5 6.5 7.5 20h9l1-13.5" />
    <path d="M10 10.5v6M14 10.5v6" />
  </Icon>
);

export const IconLink = (p) => (
  <Icon {...p}>
    <path d="M9.5 14.5 14.5 9.5" />
    <path d="M11 6.5 13 4.5a4 4 0 0 1 6 6l-2.2 2.1" />
    <path d="M13 17.5 11 19.5a4 4 0 0 1-6-6l2.2-2.1" />
  </Icon>
);

export const IconCopy = (p) => (
  <Icon {...p}>
    <rect x="9" y="9" width="11.5" height="11.5" rx="2" />
    <path d="M5.5 15H4.7A1.7 1.7 0 0 1 3 13.3V4.7A1.7 1.7 0 0 1 4.7 3h8.6A1.7 1.7 0 0 1 15 4.7v.8" />
  </Icon>
);

export const IconLogout = (p) => (
  <Icon {...p}>
    <path d="M14 4.5H6.5A1.5 1.5 0 0 0 5 6v12a1.5 1.5 0 0 0 1.5 1.5H14" />
    <path d="m16 8 4 4-4 4M20 12H9.5" />
  </Icon>
);

export const IconRefresh = (p) => (
  <Icon {...p}>
    <path d="M20 5v5h-5" />
    <path d="M4 19v-5h5" />
    <path d="M19.5 10a8 8 0 0 0-14-3.3M4.5 14a8 8 0 0 0 14 3.3" />
  </Icon>
);

export const IconSend = (p) => (
  <Icon {...p}>
    <path d="M21 3.5 3.6 10.4c-.8.3-.75 1.4.05 1.7l6.4 2 2 6.3c.3.8 1.4.85 1.7.05L21 3.5Z" />
    <path d="m10 14 4.5-4.5" />
  </Icon>
);

export const IconDownload = (p) => (
  <Icon {...p}>
    <path d="M12 4v11M7.5 11 12 15.5 16.5 11" />
    <path d="M4.5 19.5h15" />
  </Icon>
);

/* ── Status / info ──────────────────────────────────────────────────────── */

export const IconPhone = (p) => (
  <Icon {...p}>
    <path d="M5.5 3.5h3.4l1.5 4.2-2 1.6a12.8 12.8 0 0 0 6.3 6.3l1.6-2 4.2 1.5v3.4c0 .9-.7 1.7-1.7 1.6C10.6 19.5 4.5 13.4 3.9 5.2c-.07-1 .7-1.7 1.6-1.7Z" />
  </Icon>
);

export const IconNote = (p) => (
  <Icon {...p}>
    <path d="M5 4.5h14v12l-4 4H5v-16Z" />
    <path d="M15 20.5V16h4.5" />
    <path d="M8.5 9h7M8.5 12.5H13" />
  </Icon>
);

export const IconAlert = (p) => (
  <Icon {...p}>
    <path d="M12 4 2.8 19.5h18.4L12 4Z" />
    <path d="M12 10v4.2" />
    <path d="M12 16.8v.4" />
  </Icon>
);

export const IconStore = (p) => (
  <Icon {...p}>
    <path d="M4 9.5 5.5 4h13L20 9.5" />
    <path d="M4 9.5a2.6 2.6 0 0 0 5.3 0 2.6 2.6 0 0 0 5.4 0 2.6 2.6 0 0 0 5.3 0" />
    <path d="M5 12.5V20h14v-7.5" />
    <path d="M9.5 20v-5h5v5" />
  </Icon>
);

export const IconGlobe = (p) => (
  <Icon {...p}>
    <circle cx="12" cy="12" r="8.5" />
    <path d="M3.5 12h17" />
    <path d="M12 3.5c2.5 2.3 3.8 5.2 3.8 8.5s-1.3 6.2-3.8 8.5c-2.5-2.3-3.8-5.2-3.8-8.5S9.5 5.8 12 3.5Z" />
  </Icon>
);

export const IconChevronDown = (p) => (
  <Icon {...p}>
    <path d="m6 9.5 6 6 6-6" />
  </Icon>
);

export const IconChevronRight = (p) => (
  <Icon {...p}>
    <path d="m9.5 6 6 6-6 6" />
  </Icon>
);

export const IconArrowLeft = (p) => (
  <Icon {...p}>
    <path d="M19 12H5M11 6l-6 6 6 6" />
  </Icon>
);

export const IconStar = (p) => (
  <Icon {...p}>
    <path d="m12 4 2.4 5 5.6.7-4.1 3.8 1.1 5.5-5-2.8-5 2.8 1.1-5.5L4 9.7 9.6 9 12 4Z" />
  </Icon>
);

export const IconCoffee = (p) => (
  <Icon {...p}>
    <path d="M4.5 9h12v6.5a4 4 0 0 1-4 4h-4a4 4 0 0 1-4-4V9Z" />
    <path d="M16.5 10.5h1.6a2.4 2.4 0 0 1 0 4.8h-1.7" />
    <path d="M8 3.5c-.8 1.1-.8 2 0 3M12 3.5c-.8 1.1-.8 2 0 3" />
  </Icon>
);

export const IconMoon = (p) => (
  <Icon {...p}>
    <path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5Z" />
  </Icon>
);

export const IconSparkle = (p) => (
  <Icon {...p}>
    <path d="M12 3.5 13.8 9 19.5 11 13.8 13 12 18.5 10.2 13 4.5 11 10.2 9 12 3.5Z" />
    <path d="M18.5 16.5 19 18l1.5.5L19 19l-.5 1.5L18 19l-1.5-.5L18 18l.5-1.5Z" />
  </Icon>
);

export const IconInstall = (p) => (
  <Icon {...p}>
    <rect x="6.5" y="2.8" width="11" height="18.4" rx="2.4" />
    <path d="M12 9v5M9.8 11.8 12 14l2.2-2.2" />
    <path d="M10.5 18.5h3" />
  </Icon>
);

export const IconTelegram = (p) => (
  <Icon {...p}>
    <path d="M20.7 4.2 3.3 10.9c-1 .4-.94 1.7.1 2l4.4 1.4 1.7 5.2c.3.95 1.5 1.1 2.1.3l2.4-3 4.4 3.2c.8.6 1.9.13 2.1-.84l2-13c.2-1.1-.85-1.96-1.8-1.56Z" transform="scale(0.92) translate(1 1)" />
    <path d="m7.8 14.3 9.4-7.5-6.9 8.2" />
  </Icon>
);

export default Icon;
