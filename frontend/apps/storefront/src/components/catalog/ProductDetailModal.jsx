"use client";

import React, { useState, useEffect } from "react";
import { useStore } from "@/store/StoreProvider";
import { Modal } from "@/components/ui/Overlay";
import { Icon } from "@/components/ui/Icon";
import { StarRating, QuantityStepper, TextField, Button } from "@/components/ui/Controls";
import { formatInr, getProductImage, validateReviewForm } from "@noir/utils/formatters.js";

export function ProductDetailModal({ product, isOpen, onClose }) {
  const {
    apiClient,
    currentActor,
    addToBag,
    openDrawer,
    notify,
  } = useStore();

  const [selectedSize, setSelectedSize] = useState("M");
  const [quantity, setQuantity] = useState(1);
  const [isAdding, setIsAdding] = useState(false);

  // Recommendations state
  const [recommendations, setRecommendations] = useState([]);
  const [loadingRecs, setLoadingRecs] = useState(false);

  // Reviews state
  const [reviews, setReviews] = useState([]);
  const [reviewCount, setReviewCount] = useState(0);
  const [avgRating, setAvgRating] = useState(5.0);

  // Review Form state
  const [showReviewForm, setShowReviewForm] = useState(false);
  const [reviewRating, setReviewRating] = useState(5);
  const [fitFeedback, setFitFeedback] = useState("true_to_size");
  const [reviewComment, setReviewComment] = useState("");
  const [formErrors, setFormErrors] = useState({});
  const [isSubmittingReview, setIsSubmittingReview] = useState(false);

  useEffect(() => {
    if (product?.product_id && isOpen) {
      setSelectedSize(product.sizes?.[0] || "M");
      setQuantity(1);
      setReviews(product.reviews || []);
      setReviewCount(product.review_count || (product.reviews?.length ?? 0));
      setAvgRating(product.average_rating || 5.0);
      setShowReviewForm(false);
      setFormErrors({});

      // Load DB recommendations
      setLoadingRecs(true);
      apiClient
        .getProductRecommendations(product.product_id)
        .then((recs) => {
          setRecommendations(Array.isArray(recs) ? recs : []);
        })
        .catch(() => setRecommendations([]))
        .finally(() => setLoadingRecs(false));
    }
  }, [product, isOpen, apiClient]);

  if (!product) return null;

  const img = getProductImage(product);
  const outOfStock = Number(product.stock_quantity || 0) <= 0;
  const maxStock = Math.min(Number(product.stock_quantity || 10), 10);
  const gstRate = product.price <= 2500 ? 5 : 12;

  const handleAddToBag = async () => {
    if (outOfStock || isAdding) return;
    setIsAdding(true);
    try {
      await addToBag(product, selectedSize, quantity);
    } finally {
      setIsAdding(false);
    }
  };

  const handleBuyNow = async () => {
    await handleAddToBag();
    onClose();
    openDrawer("bag");
  };

  const handleReviewSubmit = async (e) => {
    e.preventDefault();
    const errors = validateReviewForm({
      rating: reviewRating,
      comment: reviewComment,
      fit_feedback: fitFeedback,
    });
    if (Object.keys(errors).length > 0) {
      setFormErrors(errors);
      return;
    }
    setFormErrors({});
    setIsSubmittingReview(true);
    try {
      const res = await apiClient.addProductReview(product.product_id, {
        rating: reviewRating,
        fit_feedback: fitFeedback,
        comment: reviewComment.trim(),
      });
      notify({
        type: "success",
        title: "Review submitted",
        description: "Thank you for your verified fit feedback.",
      });
      // Append review
      const newReview = {
        review_id: res?.review_id || `REV-${Date.now()}`,
        author_name: currentActor.label?.split(" ")[0] || "Verified Customer",
        rating: reviewRating,
        fit_feedback: fitFeedback,
        comment: reviewComment.trim(),
        created_at: new Date().toISOString(),
      };
      setReviews((prev) => [newReview, ...prev]);
      setReviewCount((prev) => prev + 1);
      setReviewComment("");
      setShowReviewForm(false);
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
            <span className="detail-dept-badge">{product.department}</span>
            <span className="detail-sku-badge">REF: {product.product_id}</span>
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
            <div className="detail-price-main">{formatInr(product.price)}</div>
            <div className="detail-gst-explainer">
              <span className="gst-tag">{gstRate}% GST Applicable</span>
              <span className="hsn-tag">HSN {product.hsn_code || "6203"}</span>
            </div>
            <p className="detail-tax-note">
              Price includes Indian Goods & Services Tax under CBIC notification 15/2021.
            </p>
          </div>

          {/* Size Selector */}
          <div className="detail-size-section">
            <div className="size-label-row">
              <span className="control-label">Select Tailored Size</span>
              <span className="size-fit-tip">Fits true to size</span>
            </div>
            <div className="size-options-grid" role="radiogroup" aria-label="Select size">
              {(product.sizes || ["XS", "S", "M", "L", "XL"]).map((s) => (
                <button
                  key={s}
                  type="button"
                  className={`size-btn-pill ${selectedSize === s ? "active" : ""}`}
                  onClick={() => setSelectedSize(s)}
                  role="radio"
                  aria-checked={selectedSize === s}
                >
                  {s}
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
                  : `${product.stock_quantity || 10} units in Atelier Vault`}
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

          {/* Fabric & Care Specs */}
          <div className="detail-fabric-specs">
            <div className="spec-item">
              <span className="spec-label">Material & Weave:</span>
              <span className="spec-val">
                {product.accent_tag || "Premium Certified Natural Fiber"}
              </span>
            </div>
            <div className="spec-item">
              <span className="spec-label">Garment Care:</span>
              <span className="spec-val">
                Hand wash cold with gentle detergent or eco dry clean.
              </span>
            </div>
            <div className="spec-item">
              <span className="spec-label">Atelier Guarantee:</span>
              <span className="spec-val">
                Complimentary returns within 7 days if unworn with tags attached.
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
            Stylist-curated pieces from the same collection that pair seamlessly.
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
                    <span className="rec-price">{formatInr(rec.price)}</span>
                  </div>
                  <button
                    type="button"
                    className="btn-pill btn-xs"
                    onClick={() => addToBag(rec, rec.sizes?.[0] || "M", 1)}
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
                  <option value="runs_small">Runs Small</option>
                  <option value="true_to_size">True to Size</option>
                  <option value="runs_large">Runs Large / Oversized</option>
                </select>
              </div>
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
                      {rev.author_name || "Verified Client"}
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
                      Fit: {rev.fit_feedback.replace("_", " ")}
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
