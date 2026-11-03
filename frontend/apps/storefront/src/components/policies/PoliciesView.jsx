"use client";

import React from "react";
import { useStore } from "@/store/StoreProvider";
import { Icon } from "@/components/ui/Icon";

export function PoliciesView() {
  const { businessConfig } = useStore();

  const gstConfig = businessConfig?.gst_config || {
    apparel_threshold: 2500,
    rate_below: 5,
    rate_above: 12,
  };

  const returnDays = businessConfig?.return_window_days || 7;

  return (
    <div className="page-container policies-page-container">
      <div className="policies-header">
        <span className="hero-eyebrow">Legal &amp; Fiscal Governance</span>
        <h1 className="page-heading">Atelier Policies &amp; Compliance</h1>
        <p className="page-subheading">
          Full transparency on our dual-slab GST computation, 4-tier garment return matrix,
          and luxury packaging standards.
        </p>
      </div>

      <div className="policy-cards-grid">
        {/* GST Slab Policy */}
        <section className="policy-card">
          <div className="policy-card-icon">
            <Icon name="shield" size={24} />
          </div>
          <h2 className="policy-card-title">Dual-Slab GST Taxation (HSN 61/62)</h2>
          <p className="policy-card-text">
            Under Indian CBIC Notification 15/2021, garments classified under HSN 61 (knitted/crocheted)
            and HSN 62 (woven tailored apparel) are subject to two distinct GST slabs based on sale price:
          </p>
          <ul className="policy-list">
            <li>
              <strong>{gstConfig.rate_below}% GST:</strong> Applies to all garments with a final sale price
              up to ₹{gstConfig.apparel_threshold.toLocaleString("en-IN")}.
            </li>
            <li>
              <strong>{gstConfig.rate_above}% GST:</strong> Applies to luxury and tailored garments with a
              sale price exceeding ₹{gstConfig.apparel_threshold.toLocaleString("en-IN")}.
            </li>
          </ul>
          <p className="policy-card-footnote">
            Our checkout engine splits and itemizes both CGST, SGST, and IGST components automatically on
            every verified GST invoice.
          </p>
        </section>

        {/* 4-Tier Return Matrix */}
        <section className="policy-card">
          <div className="policy-card-icon">
            <Icon name="refresh" size={24} />
          </div>
          <h2 className="policy-card-title">4-Tier Luxury Return Matrix</h2>
          <p className="policy-card-text">
            Noir Atelier provides a {returnDays}-day return privilege from the date of studio delivery:
          </p>
          <ul className="policy-list">
            <li>
              <strong>Tier 0 (Pre-Shipment):</strong> Instant 1-click cancellation with 100% immediate
              pre-authorization hold release.
            </li>
            <li>
              <strong>Tier 1 (Tags Intact):</strong> Full refund to original payment method within 24 hours
              of studio receipt.
            </li>
            <li>
              <strong>Tier 2 (Studio Verification):</strong> If security tags are detached, garments undergo
              physical textile inspection at our Colaba studio before store credit release.
            </li>
            <li>
              <strong>Tier 3 (Substantial Wear/Defects):</strong> Non-qualifying returns are returned to the
              client with an inspection report.
            </li>
          </ul>
        </section>

        {/* Delivery & Boutique Packaging */}
        <section className="policy-card">
          <div className="policy-card-icon">
            <Icon name="truck" size={24} />
          </div>
          <h2 className="policy-card-title">Complimentary Boutique Delivery</h2>
          <p className="policy-card-text">
            Orders exceeding ₹2,500 qualify for complimentary climate-controlled delivery in our
            signature reusable black garment pouches with cedar hanger.
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
