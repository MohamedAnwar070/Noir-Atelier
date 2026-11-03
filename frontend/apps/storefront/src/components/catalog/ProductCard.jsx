"use client";

import React, { useState } from "react";
import { useStore } from "@/store/StoreProvider";
import { Icon } from "@/components/ui/Icon";
import { StarRating } from "@/components/ui/Controls";
import { formatInr, getProductImage } from "@noir/utils/formatters.js";

export function ProductCard({ product, onSelect }) {
  const { addToBag, toggleWishlist, isWishlisted } = useStore();

  const price = Number(product.price ?? product.mrp_inr ?? 0);
  const stock = Number(product.stock_quantity ?? product.stock ?? 0);
  const availableSizes =
    Array.isArray(product.sizes) && product.sizes.length
      ? product.sizes
      : Array.isArray(product.sizes_available) && product.sizes_available.length
      ? product.sizes_available
      : ["S", "M", "L", "XL"];

  const [selectedSize, setSelectedSize] = useState(availableSizes[0] || "M");
  const [isAdding, setIsAdding] = useState(false);

  const img = getProductImage(product);
  const wishlisted = isWishlisted(product.product_id);
  const outOfStock = stock <= 0;
  const lowStock = stock > 0 && stock <= 3;

  // Determine GST slab based on actual price
  const gstRate = price <= 2500 ? 5 : 12;

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
            <span className="product-price-main">{formatInr(price)}</span>
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
