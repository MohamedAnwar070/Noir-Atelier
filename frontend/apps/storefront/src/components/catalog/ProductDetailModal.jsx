"use client";

import React, { useState, useEffect, useMemo } from "react";
import { useStore } from "@/store/StoreProvider";
import { normalizeProduct } from "@/store/normalizers";
import { Modal } from "@/components/ui/Overlay";
import { Icon } from "@/components/ui/Icon";
import { BrandMonogram, GarmentWovenLabel } from "@/components/ui/BrandLogo";
import { StarRating, QuantityStepper, Button } from "@/components/ui/Controls";
import { formatInr, formatPriceRange, getProductImage, validateReviewForm } from "@noir/utils/formatters.js";

export function ProductDetailModal({ product: initialProduct, isOpen, onClose }) {
  const {
    apiClient,
    addToBag,
    openDrawer,
    openProduct,
    askStylist,
    notify,
    taxRules,
    business,
    paymentMethods,
    catalogMeta,
    refreshCatalog,
  } = useStore();

  const [detailProduct, setDetailProduct] = useState(null);
  const product = detailProduct || initialProduct;

  const fitOptions = catalogMeta?.fit_feedback_options || [];
  const fitLabelByCode = useMemo(() => {
    const map = {};
    for (const opt of fitOptions) {
      map[opt.code] = opt.label;
    }
    return map;
  }, [fitOptions]);

  const defaultFitCode = fitOptions[0]?.code || "true_to_size";

  const [selectedSize, setSelectedSize] = useState("");
  const [quantity, setQuantity] = useState(1);
  const [isAdding, setIsAdding] = useState(false);

  const [recommendations, setRecommendations] = useState([]);

  const [reviews, setReviews] = useState([]);
  const [reviewCount, setReviewCount] = useState(0);
  const [avgRating, setAvgRating] = useState(5.0);

  const [showReviewForm, setShowReviewForm] = useState(false);
  const [reviewRating, setReviewRating] = useState(5);
  const [fitFeedback, setFitFeedback] = useState(defaultFitCode);
  const [reviewComment, setReviewComment] = useState("");
  const [formErrors, setFormErrors] = useState({});
  const [isSubmittingReview, setIsSubmittingReview] = useState(false);

  useEffect(() => {
    if (initialProduct?.product_id && isOpen) {
      const normalizedInit = normalizeProduct(initialProduct);
      setDetailProduct(normalizedInit);
      // Open on the first size that can actually be bought.
      const sizes = normalizedInit.sizes_available || [];
      setSelectedSize(sizes.find((sz) => normalizedInit.stockFor(sz) > 0) || sizes[0] || "");
      setQuantity(1);
      setReviews(normalizedInit.reviews || []);
      setReviewCount(normalizedInit.review_count || (normalizedInit.reviews?.length ?? 0));
      setAvgRating(normalizedInit.average_rating || 5.0);
      setFitFeedback(defaultFitCode);
      setShowReviewForm(false);
      setFormErrors({});

      let cancelled = false;
      setRecommendations([]);

      Promise.all([
        apiClient.getProductDetails(initialProduct.product_id).catch(() => null),
        apiClient.getRecommendations(initialProduct.product_id).catch(() => []),
      ]).then(([freshDetail, recs]) => {
        if (cancelled) return;
        if (freshDetail) {
          const normalizedFresh = normalizeProduct(freshDetail);
          setDetailProduct(normalizedFresh);
          setReviews(normalizedFresh.reviews || []);
          setReviewCount(normalizedFresh.review_count || (normalizedFresh.reviews?.length ?? 0));
          setAvgRating(normalizedFresh.average_rating || 5.0);
        }
        setRecommendations((Array.isArray(recs) ? recs : []).map(normalizeProduct));
      });

      return () => {
        cancelled = true;
      };
    }
    return undefined;
  }, [initialProduct, isOpen, apiClient, defaultFitCode]);

  if (!product) return null;

  const stock = Number(product.stock ?? 0);
  const selectedSizeStock = selectedSize ? product.stockFor(selectedSize) : 0;

  const availableSizes = product.sizes_available || [];
  const price = product.priceFor(selectedSize);
  const gstRate = taxRules.rateFor(price);
  const taxableValue = gstRate > 0 ? price / (1 + gstRate / 100) : price;
  const includedGstAmount = price - taxableValue;

  const returnWindowDays = business?.returns_and_refunds?.return_window_days ?? 7;
  const signatureMin = Number(business?.shipping?.signature_required_above_inr ?? 15000);
  const freeShippingMin = Number(business?.shipping?.free_shipping_threshold_inr ?? 1999);
  const coutureMin = Number(business?.catalog?.couture_tier_min_inr ?? 100000);
  const reserveMin = Number(business?.catalog?.high_value_tier_min_inr ?? 50000);

  const isCouture = price >= coutureMin;
  const isHighValue = price >= reserveMin;
  const requiresSignature = price >= signatureMin;

  const editionTitle = isCouture
    ? "HAUTE ARCHIVE EDITION"
    : isHighValue
    ? "PRIVATE CLIENT RESERVE"
    : "ATELIER EDITION";

  const selectedVariant = (product.variants || []).find((v) => v.size === selectedSize);
  const activeSku = selectedVariant?.sku || product.sku || product.product_id;

  const eligibleMethods = (paymentMethods || []).filter(
    (pm) => price >= (pm.minOrder || 0) && price <= (pm.maxOrder ?? Infinity)
  );

  const img = getProductImage(product);
  const outOfStock = selectedSizeStock <= 0;
  const maxStock = Math.min(Math.max(selectedSizeStock, 1), 10);

  const handleAddToBag = async () => {
    if (outOfStock || isAdding) return false;
    setIsAdding(true);
    try {
      return Boolean(await addToBag(product, selectedSize, quantity));
    } finally {
      setIsAdding(false);
    }
  };

  const handleBuyNow = async () => {
    if (!(await handleAddToBag())) return;
    onClose();
    openDrawer("bag");
  };

  const handleConsultStylist = () => {
    onClose();
    askStylist(
      `Tell me about ${product.product_id} (${product.name})—its natural fiber composition, fit, and styling pairings.`
    );
  };

  const handleReviewSubmit = async (e) => {
    e.preventDefault();
    const { valid, errors } = validateReviewForm({
      rating: reviewRating,
      comment: reviewComment,
      fit_feedback: fitFeedback,
    });
    if (!valid) {
      setFormErrors(errors);
      return;
    }
    setFormErrors({});
    setIsSubmittingReview(true);
    try {
      const updatedRaw = await apiClient.addProductReview(product.product_id, {
        rating: reviewRating,
        fitFeedback,
        comment: reviewComment.trim(),
      });
      const updated = normalizeProduct(updatedRaw);
      setDetailProduct(updated);
      setReviews(updated.reviews || []);
      setReviewCount(updated.review_count || (updated.reviews?.length ?? 0));
      setAvgRating(updated.average_rating || 5.0);
      setReviewComment("");
      setShowReviewForm(false);
      refreshCatalog?.();
      notify({
        type: "success",
        title: "Client impression recorded",
        description: "Thank you for sharing verified fit and fabric feedback.",
      });
    } catch (err) {
      notify({
        type: "error",
        title: "Could not submit review",
        description: err.message || "Please check your details and try again.",
      });
    } finally {
      setIsSubmittingReview(false);
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={product.name} size="lg">
      <div className="product-detail-layout">
        {/* Left Column: Editorial Portrait + Physical Woven Label Specimen */}
        <div className="product-detail-media">
          <div className="detail-main-image-wrap">
            {img.url ? (
              <img src={img.url} alt={img.alt} className="detail-main-image" />
            ) : (
              <div className="product-image-fallback large" data-dept={product.department}>
                <span>{product.name}</span>
              </div>
            )}
            <span className={`card-edition-plaque detail-accent-tag ${isCouture ? "edition-couture" : "edition-reserve"}`}>
              {isHighValue ? editionTitle : product.accent_tag || editionTitle}
            </span>
          </div>

          {/* Physical Garment Label & Authenticity Specimen */}
          <div className="detail-provenance-specimen">
            <GarmentWovenLabel
              origin={product.country_of_origin || "India"}
              composition={product.compositionLabel || product.accent_tag || "Certified Natural Fiber"}
              edition={editionTitle}
            />
            <div className="detail-seal-caption">
              <Icon name="shield" size={14} />
              <span>
                Accompanied by numbered <strong>POL-RET-01</strong> tamper-evident security ribbon &amp; archival garment cover.
              </span>
            </div>
          </div>
        </div>

        {/* Right Column: Couture Garment Dossier */}
        <div className="product-detail-info">
          <div className="detail-header-meta">
            <span className="detail-dept-badge">
              {product.department}
              {product.categoryName ? ` · ${product.categoryName}` : ""}
            </span>
            <span className="detail-sku-badge">SKU: {activeSku}</span>
            {product.country_of_origin && (
              <span className="detail-origin-badge">Origin: {product.country_of_origin}</span>
            )}
          </div>

          <h2 className="detail-product-title">{product.name}</h2>

          {product.description && (
            <p className="detail-editorial-lead">{product.description}</p>
          )}

          {/* Client Rating */}
          <div className="detail-rating-row">
            <StarRating rating={avgRating} count={reviewCount} />
            <a
              href="#reviews-section"
              className="detail-reviews-jump"
              onClick={(e) => {
                e.preventDefault();
                document.getElementById("reviews-section")?.scrollIntoView({ behavior: "smooth" });
              }}
            >
              {reviewCount} verified client {reviewCount === 1 ? "impression" : "impressions"}
            </a>
          </div>

          {/* Transparent Pricing & Statutory GST Ledger */}
          <div className="detail-pricing-box">
            <div className="detail-price-top">
              <div className="detail-price-main" aria-live="polite">{formatInr(price)}</div>
              <div className="detail-gst-explainer">
                <span className="gst-tag">{gstRate}% GST Included</span>
                {product.hsn_code && <span className="hsn-tag">CBIC HSN {product.hsn_code}</span>}
              </div>
            </div>
            <p className="detail-tax-note">
              {product.hasSizePricing
                ? `Size ${selectedSize} tariff (${formatPriceRange(product)} across sizes). `
                : ""}
              Taxable base {formatInr(Math.round(taxableValue))} + statutory GST {formatInr(Math.round(includedGstAmount))}.
              {price >= freeShippingMin ? " Complimentary insured delivery included." : ""}
            </p>
          </div>

          {/* Tailored Size Selector */}
          <div className="detail-size-section">
            <div className="size-label-row">
              <span className="control-label">Select Tailored Size</span>
              {product.fit_guide && <span className="size-fit-tip">{product.fit_guide}</span>}
            </div>
            <div className="size-options-grid" role="radiogroup" aria-label="Select size">
              {availableSizes.map((s) => {
                const szSoldOut = product.stockFor(s) <= 0;
                return (
                  <button
                    key={s}
                    type="button"
                    className={`size-btn-pill ${product.hasSizePricing ? "size-btn-pill--priced" : ""} ${selectedSize === s ? "active" : ""}`}
                    onClick={() => {
                      setSelectedSize(s);
                      setQuantity(1);
                    }}
                    role="radio"
                    aria-checked={selectedSize === s}
                    aria-label={szSoldOut ? `Size ${s}, sold out` : `Size ${s}`}
                    title={szSoldOut ? "Sold out in this size" : undefined}
                    disabled={szSoldOut}
                  >
                    <span>{s}</span>
                    {product.hasSizePricing && (
                      <span className="size-btn-price">{formatInr(product.priceFor(s))}</span>
                    )}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Quantity, Acquisition CTAs & Private Stylist Handoff */}
          <div className="detail-actions-section">
            <div className="qty-row">
              <span className="control-label">Quantity</span>
              <QuantityStepper
                value={quantity}
                onChange={setQuantity}
                min={1}
                max={maxStock}
                disabled={outOfStock}
              />
              <span className="stock-status-label">
                {stock <= 0
                  ? "Currently Archived / Out of Stock"
                  : outOfStock
                  ? `Sold out in size ${selectedSize} · choose another size`
                  : `${selectedSizeStock} ${selectedSizeStock === 1 ? "piece" : "pieces"} in Atelier Vault (Size ${selectedSize})`}
              </span>
            </div>

            <div className="detail-cta-group">
              <Button
                variant="primary"
                onClick={handleAddToBag}
                isLoading={isAdding}
                disabled={outOfStock}
                icon="bag"
                style={{ flex: 1 }}
              >
                {outOfStock ? "Sold Out" : "Add to Shopping Bag"}
              </Button>
              <Button
                variant="outline"
                onClick={handleBuyNow}
                disabled={outOfStock}
                style={{ flex: 1 }}
              >
                Acquire Now
              </Button>
            </div>

            <button
              type="button"
              className="detail-stylist-btn"
              onClick={handleConsultStylist}
            >
              <BrandMonogram size={16} />
              <span>Consult Personal Fashion Consultant on Fit, Provenance &amp; Styling</span>
            </button>
          </div>

          {/* High-Value & Maison Client Confidence Box */}
          <div className={`detail-trust-ledger ${isHighValue ? "is-elevated" : ""}`}>
            <div className="trust-ledger-title">
              <Icon name="award" size={14} />
              <span>{isHighValue ? "Private Reserve & Haute Archive Assurance" : "Maison Client Assurance"}</span>
            </div>
            <ul className="trust-ledger-list">
              <li>
                <strong>Authenticity &amp; Seal:</strong> Individually inspected and sealed with a numbered tamper-evident security ribbon (Policy POL-RET-01).
              </li>
              <li>
                <strong>{requiresSignature ? "Insured White-Glove Courier:" : "Boutique Dispatch:"}</strong>{" "}
                {requiresSignature
                  ? `Complimentary transit-insured delivery with mandatory recipient signature verification (orders ≥ ${formatInr(signatureMin)}).`
                  : `Complimentary boutique delivery on orders from ${formatInr(freeShippingMin)}.`}
              </li>
              {eligibleMethods.length > 0 && (
                <li>
                  <strong>Verified Settlement:</strong>{" "}
                  {eligibleMethods.map((m) => m.label).join(" · ")}.
                </li>
              )}
            </ul>
          </div>

          {/* Database-Driven Craftsmanship & Specification Table */}
          <div className="detail-fabric-specs">
            {product.color && (
              <div className="spec-item">
                <span className="spec-label">Colourway</span>
                <span className="spec-val spec-color-val">
                  {product.colorHex && (
                    <span
                      className="color-swatch-dot"
                      style={{ backgroundColor: product.colorHex }}
                      aria-hidden="true"
                    />
                  )}
                  <span>{product.color}</span>
                </span>
              </div>
            )}
            <div className="spec-item">
              <span className="spec-label">Natural Fiber</span>
              <span className="spec-val">
                {product.compositionLabel || product.accent_tag || product.description}
              </span>
            </div>
            {product.country_of_origin && (
              <div className="spec-item">
                <span className="spec-label">Provenance</span>
                <span className="spec-val">Crafted in {product.country_of_origin}</span>
              </div>
            )}
            {product.fit_guide && (
              <div className="spec-item">
                <span className="spec-label">Silhouette &amp; Fit</span>
                <span className="spec-val">{product.fit_guide}</span>
              </div>
            )}
            {product.fabric_and_care && (
              <div className="spec-item">
                <span className="spec-label">Care Protocol</span>
                <span className="spec-val">{product.fabric_and_care}</span>
              </div>
            )}
            <div className="spec-item">
              <span className="spec-label">Return Charter</span>
              <span className="spec-val">
                {product.final_sale
                  ? "Final Sale archive piece — eligible for return only on verified manufacturing defects."
                  : `Complimentary ${returnWindowDays}-day return window when unworn with original POL-RET-01 security ribbon intact.`}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Complete the Look: Database-Driven Recommendations */}
      {recommendations.length > 0 && (
        <section className="detail-recommendations-section">
          <h3 className="section-subheading">Complete the Ensemble</h3>
          <p className="section-subcaption">
            Curated pairings selected from the Noir Atelier archive.
          </p>
          <div className="recs-grid">
            {recommendations.map((rec) => {
              const recImg = getProductImage(rec);
              return (
                <div key={rec.product_id} className="rec-card">
                  <button
                    type="button"
                    className="rec-thumb-wrap"
                    onClick={() => openProduct?.(rec.product_id)}
                    aria-label={`Inspect ${rec.name}`}
                  >
                    {recImg.url ? (
                      <img src={recImg.url} alt={recImg.alt} className="rec-thumb" />
                    ) : (
                      <div className="rec-thumb placeholder" />
                    )}
                  </button>
                  <div className="rec-info">
                    <h4 className="rec-title">{rec.name}</h4>
                    <span className="rec-price">{formatPriceRange(rec)}</span>
                  </div>
                  <button
                    type="button"
                    className="btn-pill btn-pill-outline btn-xs"
                    onClick={() => addToBag(rec, rec.sizes_available[0], 1)}
                  >
                    + Add ({rec.sizes_available?.[0]})
                  </button>
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* Client Impressions & Fit Reviews */}
      <section id="reviews-section" className="detail-reviews-section">
        <div className="reviews-header-bar">
          <div>
            <h3 className="section-subheading">Verified Client Impressions</h3>
            <span className="reviews-aggregate-caption">
              ★ {Number(avgRating).toFixed(1)} average across {reviewCount} verified {reviewCount === 1 ? "acquisition" : "acquisitions"}
            </span>
          </div>

          {!showReviewForm && (
            <button
              type="button"
              className="btn-pill btn-pill-outline btn-sm"
              onClick={() => setShowReviewForm(true)}
            >
              Record Impression
            </button>
          )}
        </div>

        {showReviewForm && (
          <form className="review-composer-card" onSubmit={handleReviewSubmit}>
            <h4 className="composer-heading">Share Fit &amp; Craftsmanship Feedback</h4>

            <div className="composer-row">
              <div>
                <label className="field-label">Rating</label>
                <div className="star-picker" role="radiogroup" aria-label="Select star rating">
                  {[1, 2, 3, 4, 5].map((num) => (
                    <button
                      key={num}
                      type="button"
                      className={`star-pick-btn ${reviewRating >= num ? "filled" : ""}`}
                      onClick={() => setReviewRating(num)}
                      role="radio"
                      aria-checked={reviewRating === num}
                    >
                      ★
                    </button>
                  ))}
                </div>
              </div>

              {fitOptions.length > 0 && (
                <div>
                  <label className="field-label" htmlFor="fit-feedback-select">
                    Fit Assessment
                  </label>
                  <select
                    id="fit-feedback-select"
                    className="select-control"
                    value={fitFeedback}
                    onChange={(e) => setFitFeedback(e.target.value)}
                  >
                    {fitOptions.map((opt) => (
                      <option key={opt.code} value={opt.code}>
                        {opt.label}
                      </option>
                    ))}
                  </select>
                </div>
              )}
            </div>

            <div className="composer-comment-box">
              <label className="field-label" htmlFor="review-comment-input">
                Impression
              </label>
              <textarea
                id="review-comment-input"
                className={`textarea-control ${formErrors.comment ? "error" : ""}`}
                rows={3}
                placeholder="Note the fabric hand-feel, drape, tailoring, and fit..."
                value={reviewComment}
                onChange={(e) => setReviewComment(e.target.value)}
                aria-invalid={!!formErrors.comment}
              />
              {formErrors.comment && (
                <span className="field-error-msg">{formErrors.comment}</span>
              )}
            </div>

            <div className="composer-actions">
              <Button
                type="submit"
                variant="primary"
                size="sm"
                isLoading={isSubmittingReview}
              >
                Submit Impression
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => setShowReviewForm(false)}
              >
                Cancel
              </Button>
            </div>
          </form>
        )}

        <div className="reviews-list">
          {reviews.length === 0 ? (
            <p className="no-reviews-note">
              No client impressions recorded yet for this archive piece.
            </p>
          ) : (
            reviews.map((rev) => (
              <div key={rev.review_id || rev.id} className="review-item">
                <div className="review-item-header">
                  <div className="reviewer-info">
                    <span className="reviewer-name">
                      {rev.author_name || rev.customer_id || "Verified Client"}
                    </span>
                    <span className="verified-badge">
                      <Icon name="check" size={12} /> Verified Acquisition
                    </span>
                  </div>
                  <span className="review-date">
                    {rev.created_at ? new Date(rev.created_at).toLocaleDateString() : "Recent"}
                  </span>
                </div>
                <div className="review-item-meta">
                  <StarRating rating={rev.rating || 5} />
                  {rev.fit_feedback && (
                    <span className="fit-pill">
                      Fit: {fitLabelByCode[rev.fit_feedback] || rev.fit_feedback.replace(/_/g, " ")}
                    </span>
                  )}
                </div>
                <p className="review-comment-text">{rev.comment}</p>
              </div>
            ))
          )}
        </div>
      </section>
    </Modal>
  );
}
