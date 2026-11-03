"use client";

import React, { useId } from "react";
import Icon from "./Icon";

export function Field({ label, error, hint, required, children, htmlFor }) {
  return (
    <div className="field">
      <label className="field__label" htmlFor={htmlFor}>
        {label}
        {required && <span aria-hidden="true"> *</span>}
      </label>
      {children}
      {hint && !error && <span className="field__hint">{hint}</span>}
      {error && (
        <span className="field__error" role="alert">
          <Icon name="alert" size={13} /> {error}
        </span>
      )}
    </div>
  );
}

export function TextField({ label, error, hint, required, multiline = false, ...props }) {
  const id = useId();
  const errorId = `${id}-err`;
  const Tag = multiline ? "textarea" : "input";
  return (
    <Field label={label} error={error} hint={hint} required={required} htmlFor={id}>
      <Tag
        id={id}
        className={`input ${error ? "input--invalid" : ""}`}
        aria-invalid={Boolean(error)}
        aria-describedby={error ? errorId : undefined}
        {...props}
      />
    </Field>
  );
}

export function StarRating({ value, rating, count, onChange, readOnly = true, size = 14 }) {
  const score = Number(rating ?? value ?? 5);
  const rounded = Math.round(score);
  return (
    <div
      className="star-rating-display"
      role={readOnly ? "img" : "radiogroup"}
      aria-label={`Rating ${score} out of 5`}
    >
      <span className="stars-gold-row">
        {[1, 2, 3, 4, 5].map((n) => (
          <span
            key={n}
            className={`star-icon ${n <= rounded ? "filled" : "empty"}`}
            onClick={!readOnly ? () => onChange?.(n) : undefined}
            style={{ cursor: readOnly ? "default" : "pointer" }}
          >
            ★
          </span>
        ))}
      </span>
      {score > 0 && <span className="rating-score-num">{score.toFixed(1)}</span>}
      {count !== undefined && <span className="rating-count-num">({count})</span>}
    </div>
  );
}

export function QuantityStepper({ value, min = 1, max = 10, onChange, disabled, label = "Quantity" }) {
  return (
    <div className="stepper" role="group" aria-label={label}>
      <button type="button" onClick={() => onChange(value - 1)} disabled={disabled || value <= min} aria-label="Decrease quantity">
        <Icon name="minus" size={14} />
      </button>
      <span aria-live="polite">{value}</span>
      <button type="button" onClick={() => onChange(value + 1)} disabled={disabled || value >= max} aria-label="Increase quantity">
        <Icon name="plus" size={14} />
      </button>
    </div>
  );
}

export function Badge({ tone = "neutral", children }) {
  return <span className={`badge badge--${tone}`}>{children}</span>;
}

export function Spinner() {
  return <span className="spinner" aria-hidden="true" />;
}

export function Button({ variant = "primary", loading = false, children, icon, className = "", ...props }) {
  return (
    <button
      type="button"
      className={`btn btn--${variant} ${className}`}
      aria-busy={loading}
      disabled={loading || props.disabled}
      {...props}
    >
      {loading ? <Spinner /> : icon ? <Icon name={icon} size={16} /> : null}
      <span>{children}</span>
    </button>
  );
}
