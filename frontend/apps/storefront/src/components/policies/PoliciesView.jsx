"use client";

import React from "react";
import { useStore } from "@/store/StoreProvider";
import { Icon } from "@/components/ui/Icon";
import { formatInr } from "@noir/utils/formatters.js";

/**
 * Policies & Provenance page. Every threshold, tax rate, shipping floor, and
 * settlement limit is read directly from backend configuration.
 */
export function PoliciesView() {
  const { businessConfig, taxRules, freeShippingMin, paymentMethods } = useStore();

  const returns = businessConfig?.returns_and_refunds || {};
  const shipping = businessConfig?.shipping || {};
  const returnDays = returns.return_window_days ?? 7;
  const signatureMin = Number(shipping.signature_required_above_inr ?? 15000);
  const tiers = returns.tiers || {};
  const autoRefundMax = tiers.tier_1_auto_refund_max_inr ?? 5000;
  const managerMax = tiers.tier_2_manager_approval_max_inr ?? 25000;
  const hsn = taxRules.hsnChapters.join("/");

  return (
    <div className="page-container policies-page-container">
      <div className="policies-header">
        <span className="hero-eyebrow">Provenance, Fiscal &amp; Client Charter</span>
        <h1 className="page-heading">Maison Provenance &amp; Governance</h1>
        <p className="page-subheading">
          Transparent statutory taxation, numbered garment authentication, insured white-glove delivery, and multi-tier return governance.
        </p>
      </div>

      <div className="policy-cards-grid">
        {/* Authenticity & Woven Seal */}
        <section className="policy-card">
          <div className="policy-card-icon">
            <Icon name="award" size={22} />
          </div>
          <h2 className="policy-card-title">Garment Provenance &amp; Security Seal</h2>
          <p className="policy-card-text">
            Every Noir Atelier piece is crafted from certified natural fibers—Belgian flax, Como mulberry silk,
            ZQ merino, Himalayan cashmere, and heritage Indian handlooms—finished with a 4-point hand-tacked woven neck label.
          </p>
          <ul className="policy-list">
            <li>
              <strong>Numbered Security Ribbon (POL-RET-01):</strong> Each garment leaves our vault with a serialised
              tamper-evident bronze-and-obsidian security seal verifying unworn provenance.
            </li>
            <li>
              <strong>Archival Presentation:</strong> Delivered in breathable unbleached muslin and reusable garment covers
              with cedar-wood shoulder support for tailored outerwear.
            </li>
          </ul>
        </section>

        {/* GST slabs */}
        <section className="policy-card">
          <div className="policy-card-icon">
            <Icon name="shield" size={22} />
          </div>
          <h2 className="policy-card-title">Statutory GST Transparency (HSN {hsn})</h2>
          <p className="policy-card-text">
            Apparel under CBIC HSN Chapters {hsn} is assessed per unit sale value. All tariffs displayed across the
            Maison archive are inclusive of statutory Goods &amp; Services Tax.
          </p>
          <ul className="policy-list">
            <li>
              <strong>{taxRules.lowRate}% GST:</strong> garments priced {taxRules.describe(taxRules.lowRate)}.
            </li>
            <li>
              <strong>{taxRules.highRate}% GST:</strong> garments priced {taxRules.describe(taxRules.highRate)}.
            </li>
          </ul>
          <p className="policy-card-footnote">
            Every acquisition generates an itemised tax invoice detailing CGST + SGST (intra-state) or IGST (inter-state).
          </p>
        </section>

        {/* Returns & refunds */}
        <section className="policy-card">
          <div className="policy-card-icon">
            <Icon name="refresh" size={22} />
          </div>
          <h2 className="policy-card-title">{returnDays}-Day Return &amp; Refund Charter</h2>
          <p className="policy-card-text">
            Acquisitions may be returned within {returnDays} days of delivery (14 days for VIP Gold clients).
            {returns.require_security_tag_intact !== false &&
              " The numbered POL-RET-01 security ribbon must remain intact and untampered."}
          </p>
          <ul className="policy-list">
            <li>
              <strong>Pre-Dispatch Cancellation:</strong> Instant full release on any unshipped order.
            </li>
            <li>
              <strong>Tier 1 — up to {formatInr(autoRefundMax)}:</strong> Automated settlement upon quality verification.
            </li>
            <li>
              <strong>Tier 2 — up to {formatInr(managerMax)}:</strong> Store Manager verification.
            </li>
            <li>
              <strong>Tier 3 — above {formatInr(managerMax)}:</strong> Dual-control Manager and Finance sign-off for high-value couture pieces.
            </li>
          </ul>
          <p className="policy-card-footnote">
            Final Sale archive pieces are eligible for return solely on verified manufacturing defects.
          </p>
        </section>

        {/* Delivery & Settlement */}
        <section className="policy-card">
          <div className="policy-card-icon">
            <Icon name="truck" size={22} />
          </div>
          <h2 className="policy-card-title">White-Glove Courier &amp; High-Value Settlement</h2>
          <p className="policy-card-text">
            Orders from {formatInr(freeShippingMin)} receive complimentary boutique dispatch. Acquisitions of{" "}
            {formatInr(signatureMin)} and above travel via transit-insured white-glove courier with mandatory recipient signature.
          </p>
          <ul className="policy-list">
            {(paymentMethods || []).map((pm) => (
              <li key={pm.id}>
                <strong>{pm.label}:</strong>{" "}
                {Number.isFinite(pm.maxOrder)
                  ? `Supported from ${formatInr(pm.minOrder || 1)} up to ${formatInr(pm.maxOrder)}.`
                  : `Supported from ${formatInr(pm.minOrder || 1)}.`}
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  );
}

export default PoliciesView;
