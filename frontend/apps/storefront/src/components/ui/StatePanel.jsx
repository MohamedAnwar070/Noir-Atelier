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
          <Skeleton className="skeleton--media" />
          <div className="product-card-body">
            <Skeleton className="skeleton--line skeleton--short" />
            <Skeleton className="skeleton--line skeleton--title" />
            <Skeleton className="skeleton--line skeleton--medium" />
          </div>
        </div>
      ))}
    </div>
  );
}

export function ListSkeleton({ count = 3 }) {
  return (
    <div className="stack" role="status" aria-busy="true" aria-label="Loading">
      {Array.from({ length: count }).map((_, i) => (
        <Skeleton key={i} className="skeleton--row" />
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
        <div className="state-panel__actions">
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
      {toasts.map((t) => {
        const tone = t.type || t.tone || "info";
        const icon = { error: "alert", warning: "alert", info: "info", success: "check" }[tone] || "check";
        return (
        <div key={t.id} className={`toast-card toast-${tone}`} role={tone === "error" ? "alert" : undefined}>
          <div className="toast-icon">
            <Icon name={icon} size={16} />
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
        );
      })}
    </div>
  );
}

export default StatePanel;
