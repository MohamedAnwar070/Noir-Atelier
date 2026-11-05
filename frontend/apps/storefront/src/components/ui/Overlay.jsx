"use client";

import React, { useEffect, useRef } from "react";
import Icon from "./Icon";

const FOCUSABLE =
  'a[href],button:not([disabled]),textarea,input:not([disabled]),select,[tabindex]:not([tabindex="-1"])';

export function Overlay({
  open,
  onClose,
  label,
  variant = "drawer",
  title,
  subtitle,
  children,
  footer,
  headerExtra,
}) {
  const panelRef = useRef(null);
  const returnFocusRef = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    returnFocusRef.current = document.activeElement;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const frame = requestAnimationFrame(() => {
      const first =
        panelRef.current?.querySelector("[data-autofocus]") ||
        panelRef.current?.querySelector(FOCUSABLE);
      first?.focus();
    });

    // With stacked overlays (e.g. address modal over the bag drawer), only the
    // top-most dialog should react to Escape / Tab.
    const isTopMost = () => {
      const dialogs = document.querySelectorAll('[role="dialog"][aria-modal="true"]');
      return dialogs[dialogs.length - 1] === panelRef.current;
    };

    const onKeyDown = (event) => {
      if (!isTopMost()) return;
      if (event.key === "Escape") {
        event.stopPropagation();
        onClose?.();
        return;
      }
      if (event.key !== "Tab" || !panelRef.current) return;
      const nodes = Array.from(panelRef.current.querySelectorAll(FOCUSABLE));
      if (!nodes.length) return;
      const first = nodes[0];
      const last = nodes[nodes.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = previousOverflow;
      returnFocusRef.current?.focus?.();
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className={`overlay overlay--${variant}`}
      onMouseDown={(e) => e.target === e.currentTarget && onClose?.()}
    >
      <section
        ref={panelRef}
        className={`overlay__panel overlay__panel--${variant}`}
        role="dialog"
        aria-modal="true"
        aria-label={label || title}
      >
        <div className="sheet-grabber" aria-hidden="true" />
        {(title || headerExtra) && (
          <header className="overlay__header">
            <div className="overlay__heading">
              {title && <h2 className="overlay__title">{title}</h2>}
              {subtitle && <p className="overlay__subtitle">{subtitle}</p>}
            </div>
            <div className="overlay__header-actions">
              {headerExtra}
              <button
                type="button"
                className="icon-btn overlay__close"
                onClick={onClose}
                aria-label="Close"
              >
                <Icon name="close" size={18} />
              </button>
            </div>
          </header>
        )}
        <div className="overlay__body">{children}</div>
        {footer && <footer className="overlay__footer">{footer}</footer>}
      </section>
    </div>
  );
}

export function Modal({ open, isOpen, onClose, title, subtitle, children, footer, size = "md" }) {
  const isVisible = Boolean(isOpen ?? open);
  return (
    <Overlay
      open={isVisible}
      onClose={onClose}
      variant={`modal modal--${size}`}
      title={title}
      subtitle={subtitle}
      footer={footer}
    >
      {children}
    </Overlay>
  );
}

export function Drawer({ open, isOpen, onClose, title, subtitle, children, footer, width }) {
  const isVisible = Boolean(isOpen ?? open);
  return (
    <Overlay
      open={isVisible}
      onClose={onClose}
      variant="drawer"
      title={title}
      subtitle={subtitle}
      footer={footer}
    >
      {children}
    </Overlay>
  );
}

export default Overlay;
