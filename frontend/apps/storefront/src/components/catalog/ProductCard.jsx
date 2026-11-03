"use client";

import React, { useState } from "react";
import { useStore } from "@/store/StoreProvider";
import { Icon } from "@/components/ui/Icon";
import { StarRating } from "@/components/ui/Controls";
import { formatInr, getProductImage } from "@noir/utils/formatters.js";

export function ProductCard({ product, onSelect }) {
  const { addToBag, toggleWishlist, isWishlisted, taxRules } = useStore();

  const stock = Number(product.stock_quantity ?? product.stock ?? 0);
  const availableSizes = product.sizes_available;

  const [selectedSize, setSelectedSize] = useState(availableSizes[0] || "M");
  // Until the shopper picks a size, a product with size-based pricing shows "From ₹…".
  const [sizeChosen, setSizeChosen] = useState(false);
  const [isAdding, setIsAdding] = useState(false);

  const price = product.priceFor(selectedSize);
  const showFromPrice = product.hasSizePricing && !sizeChosen;

  const img = getProductImage(product);
  const wishlisted = isWishlisted(product.product_id);
  const outOfStock = stock <= 0;
  const lowStock = stock > 0 && stock <= 3;

  const gstRate = taxRules.rateFor(price); // slab rule from business config

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
            <span className="badge card-stock-pill warning">Only {stock} left</span>
          )}
          {outOfStock && (
            <span className="badge card-stock-pill danger">Sold Out</span>
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
        {!outOfStock && availableSizes.length > 0 && (
          <div
            className="card-quick-sizes"
            onClick={(e) => e.stopPropagation()}
            role="radiogroup"
            aria-label="Available garment sizes"
          >
            {availableSizes.map((s) => (
              <button
                key={s}
                type="button"
                className={`quick-size-chip ${selectedSize === s ? "active" : ""}`}
                onClick={(e) => {
                  e.stopPropagation();
                  setSelectedSize(s);
                  setSizeChosen(true);
                }}
                title={product.hasSizePricing ? formatInr(product.priceFor(s)) : undefined}
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
          <div className="product-card-rating">
            <StarRating
              rating={product.average_rating || 5}
              count={product.review_count || 1}
            />
          </div>
        </div>

        <h3 className="product-card-title">{product.name}</h3>

        <div className="product-card-footer">
          <div className="product-price-stack">
            <span className="product-price-main">
              {showFromPrice ? `From ${formatInr(product.priceRange.min)}` : formatInr(price)}
            </span>
            <span className="product-gst-caption">
              {showFromPrice
                ? "Price varies by size · incl. GST"
                : `Size ${selectedSize} · incl. ${gstRate}% GST`}
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
