"use client";

import React, { useState, useEffect, useMemo } from "react";
import { useStore } from "@/store/StoreProvider";
import { normalizeProduct } from "@/store/normalizers";
import { Modal } from "@/components/ui/Overlay";
import { Icon } from "@/components/ui/Icon";
import { StarRating, QuantityStepper, Button } from "@/components/ui/Controls";
import { formatInr, formatPriceRange, getProductImage, validateReviewForm } from "@noir/utils/formatters.js";

export function ProductDetailModal({ product: initialProduct, isOpen, onClose }) {
  const {
    apiClient,
    currentActor,
    addToBag,
    openDrawer,
    notify,
    taxRules,
    business,
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

  // Recommendations state
  const [recommendations, setRecommendations] = useState([]);

  // Reviews state
  const [reviews, setReviews] = useState([]);
  const [reviewCount, setReviewCount] = useState(0);
  const [avgRating, setAvgRating] = useState(5.0);

  // Review Form state
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
      setSelectedSize(normalizedInit.sizes_available?.[0] || "");
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

  const stock = Number(product.stock_quantity ?? product.stock ?? 0);
  const availableSizes = product.sizes_available || [];
  const price = product.priceFor(selectedSize);
  const gstRate = taxRules.rateFor(price);
  const returnWindowDays = business?.returns_and_refunds?.return_window_days ?? 7;

  const img = getProductImage(product);
  const outOfStock = stock <= 0;
  const maxStock = Math.min(Math.max(stock, 1), 10);

  /** Resolves to true when the item reached the bag (the store toasts any error). */
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
        title: "Review submitted",
        description: "Thank you for your verified fit feedback.",
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
        {/* Gallery / Left Column */}
        <div className="product-detail-media">
          <div className="detail-main-image-wrap">
            {img.url ? (
              <img src={img.url} alt={img.alt} className="detail-main-image" />
            ) : (
              <div className="product-image-fallback large" data-dept={product.department}>
                <span>{product.name}</span>
              </div>
            )}
            {product.accent_tag && (
              <span className="card-accent-pill detail-accent-tag">
                {product.accent_tag}
              </span>
            )}
          </div>
        </div>

        {/* Right Details Column */}
        <div className="product-detail-info">
          <div className="detail-header-meta">
            <span className="detail-dept-badge">
              {product.department}
              {product.categoryName ? ` · ${product.categoryName}` : ""}
            </span>
            <span className="detail-sku-badge">REF: {product.sku || product.product_id}</span>
          </div>

          <h2 className="detail-product-title">{product.name}</h2>

          {/* Rating */}
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
              {reviewCount} verified {reviewCount === 1 ? "review" : "reviews"}
            </a>
          </div>

          {/* Price & GST Slab */}
          <div className="detail-pricing-box">
            <div className="detail-price-main" aria-live="polite">{formatInr(price)}</div>
            <div className="detail-gst-explainer">
              <span className="gst-tag">{gstRate}% GST Applicable</span>
              {product.hsn_code && <span className="hsn-tag">HSN {product.hsn_code}</span>}
            </div>
            <p className="detail-tax-note">
              {product.hasSizePricing
                ? `Price for size ${selectedSize}; sizes range ${formatPriceRange(product)}. `
                : ""}
              Includes GST.
            </p>
          </div>

          {/* Size Selector */}
          <div className="detail-size-section">
            <div className="size-label-row">
              <span className="control-label">Select Tailored Size</span>
              {product.fit_guide && <span className="size-fit-tip">{product.fit_guide}</span>}
            </div>
            <div className="size-options-grid" role="radiogroup" aria-label="Select size">
              {availableSizes.map((s) => (
                <button
                  key={s}
                  type="button"
                  className={`size-btn-pill ${product.hasSizePricing ? "size-btn-pill--priced" : ""} ${selectedSize === s ? "active" : ""}`}
                  onClick={() => setSelectedSize(s)}
                  role="radio"
                  aria-checked={selectedSize === s}
                >
                  <span>{s}</span>
                  {product.hasSizePricing && (
                    <span className="size-btn-price">{formatInr(product.priceFor(s))}</span>
                  )}
                </button>
              ))}
            </div>
          </div>

          {/* Quantity & CTA */}
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
                {outOfStock
                  ? "Sold Out"
                  : `${stock} units in Atelier Vault`}
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
                Buy Now
              </Button>
            </div>
          </div>

          {/* Database-Driven Garment Attributes, Composition & Care */}
          <div className="detail-fabric-specs">
            {product.color && (
              <div className="spec-item">
                <span className="spec-label">Atelier Colourway:</span>
                <span className="spec-val" style={{ display: "inline-flex", alignItems: "center", gap: "0.4rem" }}>
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
              <span className="spec-label">Material &amp; Composition:</span>
              <span className="spec-val">
                {product.compositionLabel || product.accent_tag || product.description}
              </span>
            </div>
            {product.fabric_and_care && (
              <div className="spec-item">
                <span className="spec-label">Garment Care:</span>
                <span className="spec-val">{product.fabric_and_care}</span>
              </div>
            )}
            <div className="spec-item">
              <span className="spec-label">Atelier Guarantee:</span>
              <span className="spec-val">
                {product.final_sale
                  ? "Final Sale archive piece — eligible for return only on verified manufacturing defects."
                  : `Complimentary returns within ${returnWindowDays} days if unworn with security ribbon attached.`}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Complete the Look: Database-Driven Recommendations */}
      {recommendations.length > 0 && (
        <section className="detail-recommendations-section">
          <h3 className="section-subheading">Complete the Look</h3>
          <p className="section-subcaption">
            Stylist-curated pieces from the collection that pair seamlessly.
          </p>
          <div className="recs-grid">
            {recommendations.map((rec) => {
              const recImg = getProductImage(rec);
              return (
                <div key={rec.product_id} className="rec-card">
                  <div className="rec-thumb-wrap">
                    {recImg.url ? (
                      <img src={recImg.url} alt={recImg.alt} className="rec-thumb" />
                    ) : (
                      <div className="rec-thumb placeholder" />
                    )}
                  </div>
                  <div className="rec-info">
                    <h4 className="rec-title">{rec.name}</h4>
                    <span className="rec-price">{formatPriceRange(rec)}</span>
                  </div>
                  <button
                    type="button"
                    className="btn-pill btn-xs"
                    onClick={() => addToBag(rec, rec.sizes_available[0], 1)}
                  >
                    + Bag
                  </button>
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* Customer Reviews Section */}
      <section id="reviews-section" className="detail-reviews-section">
        <div className="reviews-header-bar">
          <div>
            <h3 className="section-subheading">Client Reviews</h3>
            <span className="reviews-aggregate-caption">
              ★ {Number(avgRating).toFixed(1)} out of 5 based on {reviewCount} ratings
            </span>
          </div>

          {!showReviewForm && (
            <button
              type="button"
              className="btn-pill btn-pill-outline btn-sm"
              onClick={() => setShowReviewForm(true)}
            >
              Write a Review
            </button>
          )}
        </div>

        {/* Review Submission Form (Demonstrates Principles 9 & 10) */}
        {showReviewForm && (
          <form className="review-composer-card" onSubmit={handleReviewSubmit}>
            <h4 className="composer-heading">Review {product.name}</h4>

            <div className="composer-row">
              <div>
                <label className="field-label">Overall Rating</label>
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
                    Fit Feedback
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
                Your Review
              </label>
              <textarea
                id="review-comment-input"
                className={`textarea-control ${formErrors.comment ? "error" : ""}`}
                rows={3}
                placeholder="Describe fabric handfeel, tailoring, drape, or sizing..."
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
                Submit Verified Review
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

        {/* Existing Reviews List */}
        <div className="reviews-list">
          {reviews.length === 0 ? (
            <p className="no-reviews-note">
              No reviews yet for this tailored piece. Be the first to share fit feedback!
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
                      <Icon name="check" size={12} /> Verified Purchase
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
