"use client";

import React, { useState } from "react";
import { useStore } from "@/store/StoreProvider";
import { Icon } from "@/components/ui/Icon";
import { StarRating } from "@/components/ui/Controls";
import { formatInr, getProductImage, computeGstSlabFromConfig } from "@noir/utils/formatters.js";

export function ProductCard({ product, onSelect }) {
  const { addToBag, toggleWishlist, isWishlisted, businessConfig } = useStore();
  const [selectedSize, setSelectedSize] = useState(product.sizes?.[0] || "M");
  const [isAdding, setIsAdding] = useState(false);

  const img = getProductImage(product);
  const wishlisted = isWishlisted(product.product_id);
  const outOfStock = Number(product.stock_quantity || 0) <= 0;
  const lowStock = Number(product.stock_quantity || 0) > 0 && Number(product.stock_quantity || 0) <= 3;

  // Determine GST slab
  const gstRate = product.price <= 2500 ? 5 : 12;

  const handleQuickAdd = async (e) => {
    e.stopPropagation();
    if (outOfStock || isAdding) return;
    setIsAdding(true);
    try {
      await addToBag(product, selectedSize, 1);
    } finally {
      setTimeout(() => setIsAdding(false), 450);
    }
  };

  const handleWishlistClick = (e) => {
    e.stopPropagation();
    toggleWishlist(product.product_id);
  };

  return (
    <article
      className="product-card"
      onClick={() => onSelect?.(product)}
      tabIndex={0}
      role="button"
      aria-label={`View details for ${product.name}`}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onSelect?.(product);
        }
      }}
    >
      {/* Media container */}
      <div className="product-media-wrapper">
        {img.url ? (
          <img
            src={img.url}
            alt={img.alt}
            className="product-image"
            loading="lazy"
          />
        ) : (
          <div className="product-image-fallback" data-dept={product.department}>
            <span>{product.name}</span>
          </div>
        )}

        {/* Top Badges */}
        <div className="card-top-badges">
          {product.accent_tag && (
            <span className="card-accent-pill">{product.accent_tag}</span>
          )}
          {lowStock && (
            <span className="card-stock-pill warning">Only {product.stock_quantity} left</span>
          )}
          {outOfStock && (
            <span className="card-stock-pill danger">Sold Out</span>
          )}
        </div>

        {/* Wishlist Button */}
        <button
          type="button"
          className={`card-wishlist-btn ${wishlisted ? "active" : ""}`}
          onClick={handleWishlistClick}
          aria-label={wishlisted ? "Remove from Wishlist" : "Save to Wishlist"}
        >
          <Icon name={wishlisted ? "heart-filled" : "heart"} size={16} />
        </button>

        {/* Quick Size Overlay on hover/focus */}
        {!outOfStock && Array.isArray(product.sizes) && product.sizes.length > 1 && (
          <div
            className="card-quick-sizes"
            onClick={(e) => e.stopPropagation()}
            role="radiogroup"
            aria-label="Available garment sizes"
          >
            {product.sizes.map((s) => (
              <button
                key={s}
                type="button"
                className={`quick-size-chip ${selectedSize === s ? "active" : ""}`}
                onClick={(e) => {
                  e.stopPropagation();
                  setSelectedSize(s);
                }}
                role="radio"
                aria-checked={selectedSize === s}
              >
                {s}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Product Information */}
      <div className="product-card-body">
        <div className="product-card-meta">
          <span className="product-dept-tag">{product.department}</span>
          {product.average_rating ? (
            <div className="product-card-rating">
              <StarRating rating={product.average_rating} count={product.review_count} />
            </div>
          ) : null}
        </div>

        <h3 className="product-card-title">{product.name}</h3>

        <div className="product-card-footer">
          <div className="product-price-stack">
            <span className="product-price-main">{formatInr(product.price)}</span>
            <span className="product-gst-caption">
              incl. {gstRate}% GST ({product.hsn_code || "HSN 6203"})
            </span>
          </div>

          <button
            type="button"
            className={`btn-pill btn-sm card-add-btn ${isAdding ? "loading" : ""}`}
            onClick={handleQuickAdd}
            disabled={outOfStock || isAdding}
            aria-label={`Add ${product.name} (Size ${selectedSize}) to bag`}
          >
            {outOfStock ? (
              "Sold Out"
            ) : isAdding ? (
              <Icon name="check" size={14} />
            ) : (
              <>
                <Icon name="bag" size={14} />
                <span>+ Bag</span>
              </>
            )}
          </button>
        </div>
      </div>
    </article>
  );
}
