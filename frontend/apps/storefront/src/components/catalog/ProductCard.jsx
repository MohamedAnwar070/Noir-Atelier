"use client";

import React, { useState } from "react";
import { useStore } from "@/store/StoreProvider";
import { Icon } from "@/components/ui/Icon";
import { StarRating } from "@/components/ui/Controls";
import { LIMITS } from "@/config/ui.config";
import { formatInr, getProductImage } from "@noir/utils/formatters.js";

export function ProductCard({ product, onSelect }) {
  const { addToBag, toggleWishlist, isWishlisted, taxRules, businessConfig } = useStore();

  const stock = Number(product.stock_quantity ?? product.stock ?? 0);
  const availableSizes = product.sizes_available || [];

  const [selectedSize, setSelectedSize] = useState(availableSizes[0] || "");
  const [sizeChosen, setSizeChosen] = useState(false);
  const [isAdding, setIsAdding] = useState(false);

  const price = product.priceFor(selectedSize);
  const minPrice = product.priceRange?.min ?? price;
  const showFromPrice = product.hasSizePricing && !sizeChosen;

  const coutureMin = Number(businessConfig?.catalog?.couture_tier_min_inr ?? 100000);
  const reserveMin = Number(businessConfig?.catalog?.high_value_tier_min_inr ?? 50000);
  const editionBadge =
    minPrice >= coutureMin
      ? { label: "Haute Archive", className: "edition-couture" }
      : minPrice >= reserveMin
      ? { label: "Private Reserve", className: "edition-reserve" }
      : null;

  const img = getProductImage(product);
  const wishlisted = isWishlisted(product.product_id);
  const outOfStock = stock <= 0;
  const vaultScarce = stock > 0 && stock <= 2;
  const lowStock = stock > 2 && stock <= (LIMITS.lowStockThreshold ?? 5);

  const gstRate = taxRules.rateFor(price);
  const fiberSubtitle = product.materialSummary || product.accent_tag || "";

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
      className={`product-card ${editionBadge ? "is-high-value" : ""}`}
      onClick={() => onSelect?.(product)}
      tabIndex={0}
      role="button"
      aria-label={`View dossier for ${product.name}`}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onSelect?.(product);
        }
      }}
    >
      {/* 3:4 Editorial Portrait Container */}
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

        {/* Top Provenance & Scarcity Plaques */}
        <div className="card-top-badges">
          {editionBadge ? (
            <span className={`card-edition-plaque ${editionBadge.className}`}>
              {editionBadge.label}
            </span>
          ) : (
            product.accent_tag && (
              <span className="card-accent-pill">{product.accent_tag}</span>
            )
          )}

          {vaultScarce && (
            <span className="badge card-stock-pill warning">
              Only {stock} in Vault
            </span>
          )}
          {lowStock && (
            <span className="badge card-stock-pill warning">
              Limited · {stock} left
            </span>
          )}
          {outOfStock && (
            <span className="badge card-stock-pill danger">Archived / Sold Out</span>
          )}
        </div>

        {/* Save to Private Wishlist */}
        <button
          type="button"
          className={`card-wishlist-btn ${wishlisted ? "active" : ""}`}
          onClick={handleWishlistClick}
          aria-label={wishlisted ? "Remove from Wishlist" : "Save to Wishlist"}
        >
          <Icon name={wishlisted ? "heart-filled" : "heart"} size={15} />
        </button>

        {/* Quick Size Selection Bar on Hover / Focus */}
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

      {/* Garment Information */}
      <div className="product-card-body">
        <div className="product-card-meta">
          <span className="product-dept-tag">
            <span>
              {product.department}
              {product.categoryName ? ` · ${product.categoryName}` : ""}
            </span>
            {product.colorHex && (
              <span
                className="color-swatch-dot"
                style={{ backgroundColor: product.colorHex }}
                title={product.color || undefined}
                aria-hidden="true"
              />
            )}
          </span>
          {product.review_count > 0 && (
            <div className="product-card-rating">
              <StarRating
                rating={product.average_rating || 5}
                count={product.review_count || 0}
              />
            </div>
          )}
        </div>

        <h3 className="product-card-title">{product.name}</h3>

        {fiberSubtitle && (
          <p className="product-card-composition">
            {fiberSubtitle}
            {product.country_of_origin ? ` · ${product.country_of_origin}` : ""}
          </p>
        )}

        <div className="product-card-footer">
          <div className="product-price-stack">
            <span className="product-price-main">
              {showFromPrice ? `From ${formatInr(product.priceRange.min)}` : formatInr(price)}
            </span>
            <span className="product-gst-caption">
              {showFromPrice
                ? `Varies by size · incl. ${gstRate}% GST`
                : `${selectedSize ? `Size ${selectedSize} · ` : ""}incl. ${gstRate}% GST`}
            </span>
          </div>

          <button
            type="button"
            className={`btn-pill btn-sm card-add-btn ${isAdding ? "loading" : ""}`}
            onClick={handleQuickAdd}
            disabled={outOfStock || isAdding}
            aria-label={`Add ${product.name}${selectedSize ? ` (Size ${selectedSize})` : ""} to bag`}
          >
            {outOfStock ? (
              "Sold Out"
            ) : isAdding ? (
              <Icon name="check" size={14} />
            ) : (
              <>
                <Icon name="bag" size={13} />
                <span>Add</span>
              </>
            )}
          </button>
        </div>
      </div>
    </article>
  );
}
