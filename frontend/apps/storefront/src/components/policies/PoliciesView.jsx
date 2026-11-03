"use client";

import React from "react";
import { useStore } from "@/store/StoreProvider";
import { Icon } from "@/components/ui/Icon";
import { formatInr } from "@noir/utils/formatters.js";

/**
 * Policies page. Every number shown here comes from the backend business
 * config (the same values checkout and the return service enforce), so the
 * published policy can never drift from actual behaviour.
 */
export function PoliciesView() {
  const { businessConfig, taxRules, freeShippingMin } = useStore();

  const returns = businessConfig?.returns_and_refunds || {};
  const returnDays = returns.return_window_days ?? 7;
  const tiers = returns.tiers || {};
  const autoRefundMax = tiers.tier_1_auto_refund_max_inr ?? 5000;
  const managerMax = tiers.tier_2_manager_approval_max_inr ?? 25000;
  const hsn = taxRules.hsnChapters.join("/");

  return (
    <div className="page-container policies-page-container">
      <div className="policies-header">
        <span className="hero-eyebrow">Legal &amp; Fiscal Governance</span>
        <h1 className="page-heading">Atelier Policies &amp; Compliance</h1>
        <p className="page-subheading">
          How we price tax, handle returns and refunds, and deliver your pieces.
        </p>
      </div>

      <div className="policy-cards-grid">
        {/* GST slabs */}
        <section className="policy-card">
          <div className="policy-card-icon">
            <Icon name="shield" size={24} />
          </div>
          <h2 className="policy-card-title">Dual-Slab GST Taxation (HSN {hsn})</h2>
          <p className="policy-card-text">
            Garments under HSN {hsn} are taxed at one of two GST slabs, based on the sale price of each
            piece. All prices shown include GST.
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
            Every invoice itemises CGST and SGST (within the state) or IGST (between states).
          </p>
        </section>

        {/* Returns & refunds */}
        <section className="policy-card">
          <div className="policy-card-icon">
            <Icon name="refresh" size={24} />
          </div>
          <h2 className="policy-card-title">Returns &amp; Refunds</h2>
          <p className="policy-card-text">
            You can return a piece within {returnDays} days of delivery (14 days for VIP Gold clients).
            {returns.require_security_tag_intact !== false &&
              " The atelier security ribbon must be intact and the garment must pass our quality check."}
          </p>
          <ul className="policy-list">
            <li>
              <strong>Before dispatch:</strong> cancel any unshipped order in one click for a full refund.
            </li>
            <li>
              <strong>Tier 1 — up to {formatInr(autoRefundMax)}:</strong> refunded automatically once the
              return passes inspection.
            </li>
            <li>
              <strong>Tier 2 — up to {formatInr(managerMax)}:</strong> approved by a store manager.
            </li>
            <li>
              <strong>Tier 3 — above {formatInr(managerMax)}:</strong> requires two approvals (manager and
              finance).
            </li>
          </ul>
          <p className="policy-card-footnote">
            Final Sale pieces can only be returned if they are defective.
          </p>
        </section>

        {/* Delivery */}
        <section className="policy-card">
          <div className="policy-card-icon">
            <Icon name="truck" size={24} />
          </div>
          <h2 className="policy-card-title">Complimentary Boutique Delivery</h2>
          <p className="policy-card-text">
            Orders of {formatInr(freeShippingMin)} or more ship free in our signature reusable garment
            pouch with a cedar hanger.
          </p>
          <ul className="policy-list">
            <li>
              <strong>Mumbai, Delhi, Bengaluru:</strong> Next-day studio courier hand delivery.
            </li>
            <li>
              <strong>Rest of India:</strong> 2 to 4 business days via insured express air courier.
            </li>
          </ul>
        </section>
      </div>
    </div>
  );
}

export default PoliciesView;
