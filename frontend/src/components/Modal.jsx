import { useEffect } from "react";
import { createPortal } from "react-dom";
import { IconX } from "./icons";

/**
 * Shared modal: bottom sheet on phones, centered dialog on desktop.
 * Closes on overlay tap and Escape. Children render inside the body;
 * pass `footer` for the standard right-aligned action row.
 */
export default function Modal({ title, onClose, children, footer, maxWidth = 500 }) {
  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [onClose]);

  // Rendered through a portal to <body> so the fixed overlay is positioned
  // against the viewport, not trapped by an ancestor that has a lingering
  // transform (e.g. the page's `.animate-in` wrapper) — which would otherwise
  // size/clip the sheet to the scrolled page and push its top off-screen.
  return createPortal(
    <div
      className="modal-overlay"
      onClick={(e) => e.target === e.currentTarget && onClose()}
      role="presentation"
    >
      <div className="modal" role="dialog" aria-modal="true" aria-label={title} style={{ maxWidth }}>
        <div className="modal-header">
          <h3 className="modal-title">{title}</h3>
          <button type="button" className="modal-close" onClick={onClose} aria-label="Close">
            <IconX size={20} />
          </button>
        </div>
        {children}
        {footer && <div className="modal-footer">{footer}</div>}
      </div>
    </div>,
    document.body,
  );
}
