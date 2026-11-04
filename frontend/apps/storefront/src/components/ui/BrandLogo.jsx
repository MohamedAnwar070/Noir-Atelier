"use client";

import React from "react";

/**
 * Noir Atelier Sartorial Monogram Mark (pure flat vector geometry).
 * Octagonal couture plaque with interlocking serif-capped 'N' and needle-eye 'A' chevron.
 * Adapts automatically to Editorial Light & Noir Obsidian themes via CSS variables.
 */
export function BrandMonogram({ size = 34, reversed = false, className = "" }) {
  const plaqueFill = reversed ? "#141312" : "var(--bg-surface)";
  const plaqueStroke = reversed ? "#C5A572" : "var(--text-primary)";
  const innerStroke = reversed ? "#C5A572" : "var(--accent-gold)";
  const primaryInk = reversed ? "#F5F2EB" : "var(--text-primary)";
  const brassInk = reversed ? "#C5A572" : "var(--accent-gold)";

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 64 64"
      fill="none"
      className={`brand-monogram-svg ${className}`}
      aria-hidden="true"
    >
      <path
        d="M13 3.5H51L60.5 13V51L51 60.5H13L3.5 51V13L13 3.5Z"
        fill={plaqueFill}
        stroke={plaqueStroke}
        strokeWidth="1.6"
      />
      <path
        d="M15.2 7H48.8L57 15.2V48.8L48.8 57H15.2L7 48.8V15.2L15.2 7Z"
        stroke={innerStroke}
        strokeOpacity="0.48"
        strokeWidth="0.8"
      />
      <path
        d="M20.5 19V45M43.5 19V45M20.5 19L43.5 45"
        stroke={primaryInk}
        strokeWidth="2.25"
        strokeLinecap="square"
        strokeLinejoin="miter"
      />
      <path
        d="M18 19H23M18 45H23M41 19H46M41 45H46"
        stroke={primaryInk}
        strokeWidth="1.35"
        strokeLinecap="square"
      />
      <path
        d="M24.5 45L32 16.5L39.5 45"
        stroke={brassInk}
        strokeWidth="1.55"
        strokeLinecap="square"
        strokeLinejoin="miter"
      />
      <path d="M27 36.5H37" stroke={brassInk} strokeWidth="1.35" />
      <path d="M32 11.5L34.2 15L32 18.5L29.8 15L32 11.5Z" fill={brassInk} />
    </svg>
  );
}

/**
 * Primary Brand Lockup for Header, Footer, Packaging & Print Invoices.
 * Variants: "horizontal" | "stacked" | "monogram" | "wordmark"
 */
export function BrandLogo({
  variant = "horizontal",
  title = "Noir Atelier",
  subtitle = "Maison de Haute Confection",
  size = 34,
  reversed = false,
  showSubtitle = true,
  className = "",
}) {
  if (variant === "monogram") {
    return <BrandMonogram size={size} reversed={reversed} className={className} />;
  }

  if (variant === "wordmark") {
    return (
      <span className={`brand-lockup brand-lockup--wordmark ${className}`}>
        <span className="brand-wordmark-text">{title}</span>
      </span>
    );
  }

  if (variant === "stacked") {
    return (
      <span className={`brand-lockup brand-lockup--stacked ${className}`}>
        <BrandMonogram size={size} reversed={reversed} />
        <span className="brand-wordmark-text">{title}</span>
        {showSubtitle && <span className="brand-submark-text">{subtitle}</span>}
      </span>
    );
  }

  return (
    <span className={`brand-lockup brand-lockup--horizontal ${className}`}>
      <BrandMonogram size={size} reversed={reversed} />
      <span className="brand-lockup-divider" aria-hidden="true" />
      <span className="brand-wordmark-stack">
        <span className="brand-wordmark-text">{title}</span>
        {showSubtitle && <span className="brand-submark-text">{subtitle}</span>}
      </span>
    </span>
  );
}

/**
 * Woven Garment Neck Label & Tamper-Evident Security Ribbon Specimen
 * Rendered in the Product Detail Craftsmanship & Provenance Dossier.
 */
export function GarmentWovenLabel({ sku, origin, composition, brandTitle = "Noir Atelier" }) {
  return (
    <div className="woven-label-specimen" aria-label="Garment woven label and authenticity specification">
      <div className="woven-label-tack woven-label-tack--tl" aria-hidden="true" />
      <div className="woven-label-tack woven-label-tack--tr" aria-hidden="true" />
      <div className="woven-label-tack woven-label-tack--bl" aria-hidden="true" />
      <div className="woven-label-tack woven-label-tack--br" aria-hidden="true" />
      <div className="woven-label-inner">
        <BrandMonogram size={32} />
        <div className="woven-label-copy">
          <div className="woven-label-brand">{brandTitle}</div>
          <div className="woven-label-meta">
            {composition || "Certified Natural Fibers"}
            {origin ? ` · Crafted in ${origin}` : ""}
          </div>
          <div className="woven-label-code">
            ARCHIVE REF {sku} · NUMBERED SECURITY RIBBON
          </div>
        </div>
      </div>
    </div>
  );
}

export default BrandLogo;
