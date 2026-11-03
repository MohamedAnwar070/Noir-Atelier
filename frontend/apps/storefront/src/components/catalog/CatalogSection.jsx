"use client";

import React, { useState, useMemo } from "react";
import { useStore } from "@/store/StoreProvider";
import { ProductCard } from "@/components/catalog/ProductCard";
import { ProductGridSkeleton, StatePanel } from "@/components/ui/StatePanel";
import { Icon } from "@/components/ui/Icon";

const PRICE_TIERS = [
  { id: "all", label: "All Prices" },
  { id: "tier_5pct", label: "Under ₹2,500 (5% GST)", max: 2500 },
  { id: "tier_mid", label: "₹2,500 – ₹7,000", min: 2500, max: 7000 },
  { id: "tier_luxury", label: "Above ₹7,000", min: 7000 },
];

const SORT_OPTIONS = [
  { id: "featured", label: "Curated / Featured" },
  { id: "price_asc", label: "Price: Low to High" },
  { id: "price_desc", label: "Price: High to Low" },
  { id: "rating", label: "Top Customer Rated" },
];

export function CatalogSection({ onSelectProduct }) {
  const {
    catalog,
    isLoadingCatalog,
    catalogError,
    activeDepartment,
    setActiveDepartment,
    searchQuery,
    setSearchQuery,
    refreshCatalog,
    storefrontConfig,
  } = useStore();

  const [selectedPriceTier, setSelectedPriceTier] = useState("all");
  const [selectedSort, setSelectedSort] = useState("featured");

  // Filter products locally by price tier & sort
  const filteredProducts = useMemo(() => {
    let list = [...catalog];

    // Price tier filter
    const tier = PRICE_TIERS.find((t) => t.id === selectedPriceTier);
    if (tier) {
      if (tier.min !== undefined) list = list.filter((p) => p.price >= tier.min);
      if (tier.max !== undefined) list = list.filter((p) => p.price <= tier.max);
    }

    // Sort
    if (selectedSort === "price_asc") {
      list.sort((a, b) => a.price - b.price);
    } else if (selectedSort === "price_desc") {
      list.sort((a, b) => b.price - a.price);
    } else if (selectedSort === "rating") {
      list.sort((a, b) => (b.average_rating || 0) - (a.average_rating || 0));
    }

    return list;
  }, [catalog, selectedPriceTier, selectedSort]);

  const handleClearFilters = () => {
    setSearchQuery("");
    setActiveDepartment("ALL");
    setSelectedPriceTier("all");
    setSelectedSort("featured");
  };

  return (
    <section className="catalog-section" aria-label="Garment Collection">
      {/* Editorial Hero Header */}
      <div className="catalog-hero-editorial">
        <div className="hero-content-stack">
          <span className="hero-eyebrow">
            {storefrontConfig.hero_eyebrow || "Noir Atelier Autumn / Winter Collection"}
          </span>
          <h1 className="hero-headline">
            {storefrontConfig.hero_title || "The New Edit"}
          </h1>
          <p className="hero-description">
            {storefrontConfig.hero_subtitle ||
              "Handcrafted tailored linen, mulberry silk dresses, and fine merino garments with real-time GST slab intelligence."}
          </p>

          <div className="hero-guarantees-row">
            <span className="guarantee-pill">
              <Icon name="shield" size={13} />
              <span>HSN 61/62 Tax Certified</span>
            </span>
            <span className="guarantee-pill">
              <Icon name="truck" size={13} />
              <span>Complimentary Delivery &gt; ₹2,500</span>
            </span>
            <span className="guarantee-pill">
              <Icon name="refresh" size={13} />
              <span>7-Day Return Guarantee</span>
            </span>
          </div>
        </div>
      </div>

      {/* Filter and Control Bar */}
      <div className="catalog-toolbar">
        {/* Department Selection */}
        <div className="department-tabs" role="tablist" aria-label="Department selection">
          {["ALL", "MEN", "WOMEN", "KIDS"].map((dept) => (
            <button
              key={dept}
              type="button"
              role="tab"
              aria-selected={activeDepartment === dept}
              className={`dept-tab-btn ${activeDepartment === dept ? "active" : ""}`}
              onClick={() => setActiveDepartment(dept)}
            >
              {dept === "ALL" ? "All Pieces" : dept.charAt(0) + dept.slice(1).toLowerCase()}
            </button>
          ))}
        </div>

        {/* Secondary controls: Price tiers, Sorting, Result count */}
        <div className="catalog-sub-toolbar">
          {/* Price Tier Pills */}
          <div className="price-tier-pills" role="radiogroup" aria-label="Price filters">
            {PRICE_TIERS.map((tier) => (
              <button
                key={tier.id}
                type="button"
                role="radio"
                aria-checked={selectedPriceTier === tier.id}
                className={`chip-pill ${selectedPriceTier === tier.id ? "active" : ""}`}
                onClick={() => setSelectedPriceTier(tier.id)}
              >
                {tier.label}
              </button>
            ))}
          </div>

          <div className="catalog-meta-controls">
            {/* Sort Dropdown */}
            <select
              className="select-control sort-select"
              value={selectedSort}
              onChange={(e) => setSelectedSort(e.target.value)}
              aria-label="Sort garments"
            >
              {SORT_OPTIONS.map((opt) => (
                <option key={opt.id} value={opt.id}>
                  {opt.label}
                </option>
              ))}
            </select>

            <span className="catalog-counter" aria-live="polite">
              {filteredProducts.length} {filteredProducts.length === 1 ? "piece" : "pieces"}
            </span>
          </div>
        </div>
      </div>

      {/* Main Content Area: State-Driven Rendering */}
      <div className="catalog-grid-area">
        {/* Principle 2: Loading State */}
        {isLoadingCatalog && <ProductGridSkeleton count={6} />}

        {/* Principle 3: Error State */}
        {!isLoadingCatalog && catalogError && (
          <StatePanel
            type="error"
            title="Unable to load catalog"
            description={catalogError}
            actionLabel="Try again"
            onAction={refreshCatalog}
          />
        )}

        {/* Principle 6: No Search Results */}
        {!isLoadingCatalog && !catalogError && filteredProducts.length === 0 && (
          <StatePanel
            type="no_results"
            title="No garments found"
            description={
              searchQuery
                ? `No pieces matched "${searchQuery}". Try a different search or clear your active filters.`
                : "No pieces match the selected department and price filters."
            }
            actionLabel="Clear all filters"
            onAction={handleClearFilters}
          />
        )}

        {/* Grid of Products */}
        {!isLoadingCatalog && !catalogError && filteredProducts.length > 0 && (
          <div className="product-grid" role="list">
            {filteredProducts.map((prod) => (
              <ProductCard
                key={prod.product_id}
                product={prod}
                onSelect={onSelectProduct}
              />
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
