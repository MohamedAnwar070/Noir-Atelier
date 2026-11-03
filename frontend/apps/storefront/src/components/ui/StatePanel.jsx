"use client";

import React from "react";
import { getStateCopy } from "@noir/ui/states.js";
import { Icon } from "./Icon";

export function Skeleton({ className = "", style }) {
  return <div className={`skeleton ${className}`} style={style} aria-hidden="true" />;
}

export function ProductGridSkeleton({ count = 6 }) {
  return (
    <div className="product-grid" role="status" aria-busy="true" aria-label="Loading collection">
      {Array.from({ length: count }).map((_, i) => (
        <div className="product-card product-card--skeleton" key={i}>
          <Skeleton className="skeleton--media" style={{ aspectRatio: "3 / 4", width: "100%" }} />
          <div className="product-card-body" style={{ padding: "1rem" }}>
            <Skeleton className="skeleton--line skeleton--short" style={{ height: "14px", width: "40%", marginBottom: "8px" }} />
            <Skeleton className="skeleton--line" style={{ height: "18px", width: "80%", marginBottom: "8px" }} />
            <Skeleton className="skeleton--line skeleton--medium" style={{ height: "16px", width: "50%" }} />
          </div>
        </div>
      ))}
    </div>
  );
}

export function ListSkeleton({ count = 3, rows = 3 }) {
  const actualCount = count || rows;
  return (
    <div className="stack" role="status" aria-busy="true" aria-label="Loading" style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
      {Array.from({ length: actualCount }).map((_, i) => (
        <div key={i} className="skeleton" style={{ height: "72px", borderRadius: "14px", width: "100%" }} />
      ))}
    </div>
  );
}

export function StatePanel({
  type,
  kind = "error",
  title,
  description,
  detail,
  action,
  actionLabel,
  onAction,
  secondaryAction,
  compact = false,
  role,
}) {
  const actualKind = type || kind;
  const copy = getStateCopy(actualKind, {
    title,
    description,
    actionLabel: actionLabel || action?.label,
  });
  const liveRole = role || (actualKind === "error" || actualKind === "offline" ? "alert" : "status");

  return (
    <div className={`state-panel state-panel--${copy.tone} ${compact ? "state-panel--compact" : ""}`} role={liveRole}>
      <span className="state-panel__icon">
        <Icon name={copy.icon} size={compact ? 22 : 30} />
      </span>
      <h3 className="state-panel__title">{copy.title}</h3>
      {copy.description && <p className="state-panel__text">{copy.description}</p>}
      {detail && <p className="state-panel__detail">{detail}</p>}
      {(actionLabel || onAction || action || secondaryAction) && (
        <div className="state-panel__actions" style={{ marginTop: "1rem" }}>
          {(actionLabel || onAction || action) && (
            <button
              type="button"
              className="btn-pill btn-pill-outline btn-sm"
              onClick={onAction || action?.onClick}
            >
              {actionLabel || action?.label || copy.actionLabel || "Continue"}
            </button>
          )}
          {secondaryAction && (
            <button
              type="button"
              className="btn-pill btn-sm"
              onClick={secondaryAction.onClick}
            >
              {secondaryAction.label}
            </button>
          )}
        </div>
      )}
    </div>
  );
}

export function ToastContainer({ toasts = [], onDismiss }) {
  if (!toasts || toasts.length === 0) return null;

  return (
    <div className="toast-container" role="region" aria-label="Notifications" aria-live="polite">
      {toasts.map((t) => (
        <div key={t.id} className={`toast-card toast-${t.type || t.tone || "info"}`}>
          <div className="toast-icon">
            <Icon name={t.type === "error" ? "alert" : "check"} size={16} />
          </div>
          <div className="toast-content">
            <div className="toast-title">{t.title}</div>
            {t.description && <div className="toast-desc">{t.description}</div>}
            {t.message && <div className="toast-desc">{t.message}</div>}
          </div>
          <button
            type="button"
            className="toast-close-btn"
            onClick={() => onDismiss?.(t.id)}
            aria-label="Dismiss notification"
          >
            <Icon name="close" size={14} />
          </button>
        </div>
      ))}
    </div>
  );
}

export default StatePanel;
