"use client";

import React from "react";
import { useStore } from "@/store/StoreProvider";
import { ProductCard } from "@/components/catalog/ProductCard";
import { ProductGridSkeleton, StatePanel } from "@/components/ui/StatePanel";
import { Icon } from "@/components/ui/Icon";
import { formatInr } from "@noir/utils/formatters.js";

export function CatalogSection({ onSelectProduct }) {
  const {
    catalog,
    catalogTotal,
    searchInterpretation,
    isLoadingCatalog,
    catalogError,
    filters,
    setFilters,
    resetFilters,
    hasActiveFilters,
    catalogMeta,
    refreshCatalog,
    storefrontConfig,
    business,
    taxRules,
    freeShippingMin,
  } = useStore();

  const departments = catalogMeta?.departments || [];
  const categories = (catalogMeta?.categories || []).filter((c) => (c.product_count ?? 0) > 0);
  const colorFamilies = catalogMeta?.color_families || [];
  const materialFamilies = catalogMeta?.material_families || [];
  const priceTiers = catalogMeta?.price_tiers || [];
  const sortOptions = catalogMeta?.sort_options || [];
  const returnDays = business?.returns_and_refunds?.return_window_days ?? 7;
  const hsnChapters = (taxRules?.hsnChapters || ["61", "62"]).join("/");

  const recognizedTokens = searchInterpretation?.recognized || [];
  const priceCaption =
    searchInterpretation?.min_price != null && searchInterpretation?.max_price != null
      ? `${formatInr(searchInterpretation.min_price)} – ${formatInr(searchInterpretation.max_price)}`
      : searchInterpretation?.max_price != null
      ? `Up to ${formatInr(searchInterpretation.max_price)}`
      : searchInterpretation?.min_price != null
      ? `From ${formatInr(searchInterpretation.min_price)}`
      : null;

  const showInterpretation =
    Boolean(filters.q) &&
    (recognizedTokens.length > 0 || Boolean(priceCaption) || Boolean(searchInterpretation?.relaxed));

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
              <span>HSN {hsnChapters} Tax Certified</span>
            </span>
            <span className="guarantee-pill">
              <Icon name="truck" size={13} />
              <span>Free delivery from {formatInr(freeShippingMin)}</span>
            </span>
            <span className="guarantee-pill">
              <Icon name="refresh" size={13} />
              <span>{returnDays}-Day Return Guarantee</span>
            </span>
          </div>
        </div>
      </div>

      {/* Database-Driven Filter and Facet Bar */}
      <div className="catalog-toolbar">
        {/* Department Selection (from `departments` table) */}
        <div className="department-tabs" role="tablist" aria-label="Department selection">
          <button
            type="button"
            role="tab"
            aria-selected={filters.department === "ALL"}
            className={`dept-tab-btn ${filters.department === "ALL" ? "active" : ""}`}
            onClick={() => setFilters({ department: "ALL" })}
          >
            All Pieces
          </button>
          {departments.map((dept) => (
            <button
              key={dept.code}
              type="button"
              role="tab"
              aria-selected={filters.department === dept.code}
              className={`dept-tab-btn ${filters.department === dept.code ? "active" : ""}`}
              onClick={() => setFilters({ department: dept.code })}
            >
              {dept.name}
            </button>
          ))}
        </div>

        {/* Structured Attribute Facets (Categories, Colours, Materials) */}
        {(categories.length > 0 || colorFamilies.length > 0 || materialFamilies.length > 0) && (
          <div className="catalog-facets-bar" aria-label="Garment attribute filters">
            {categories.length > 0 && (
              <div className="facet-group" role="group" aria-label="Garment type">
                <span className="facet-label">Type</span>
                <div className="facet-pills">
                  <button
                    type="button"
                    className={`chip-pill ${!filters.category ? "active" : ""}`}
                    onClick={() => setFilters({ category: "" })}
                  >
                    All Types
                  </button>
                  {categories.map((cat) => (
                    <button
                      key={cat.category_id}
                      type="button"
                      className={`chip-pill ${filters.category === cat.slug ? "active" : ""}`}
                      onClick={() =>
                        setFilters({ category: filters.category === cat.slug ? "" : cat.slug })
                      }
                    >
                      {cat.name}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {colorFamilies.length > 0 && (
              <div className="facet-group" role="group" aria-label="Colour family">
                <span className="facet-label">Palette</span>
                <div className="facet-pills">
                  <button
                    type="button"
                    className={`chip-pill ${!filters.color ? "active" : ""}`}
                    onClick={() => setFilters({ color: "" })}
                  >
                    All Colours
                  </button>
                  {colorFamilies.map((cf) => (
                    <button
                      key={cf.family}
                      type="button"
                      className={`chip-pill color-chip-pill ${filters.color === cf.family ? "active" : ""}`}
                      onClick={() =>
                        setFilters({ color: filters.color === cf.family ? "" : cf.family })
                      }
                    >
                      {cf.hex_code && (
                        <span
                          className="color-swatch-dot"
                          style={{ backgroundColor: cf.hex_code }}
                          aria-hidden="true"
                        />
                      )}
                      <span>{cf.label}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {materialFamilies.length > 0 && (
              <div className="facet-group" role="group" aria-label="Natural fiber">
                <span className="facet-label">Fiber</span>
                <div className="facet-pills">
                  <button
                    type="button"
                    className={`chip-pill ${!filters.material ? "active" : ""}`}
                    onClick={() => setFilters({ material: "" })}
                  >
                    All Fibers
                  </button>
                  {materialFamilies.map((mf) => (
                    <button
                      key={mf.family}
                      type="button"
                      className={`chip-pill ${filters.material === mf.family ? "active" : ""}`}
                      onClick={() =>
                        setFilters({ material: filters.material === mf.family ? "" : mf.family })
                      }
                    >
                      {mf.label}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Secondary controls: Price tiers (from DB tax/catalog config), In-stock toggle, Sort, Counter */}
        <div className="catalog-sub-toolbar">
          <div className="price-tier-pills" role="radiogroup" aria-label="Price filters">
            {priceTiers.map((tier) => (
              <button
                key={tier.id}
                type="button"
                role="radio"
                aria-checked={filters.priceTier === tier.id}
                className={`chip-pill ${filters.priceTier === tier.id ? "active" : ""}`}
                onClick={() =>
                  setFilters({
                    priceTier: tier.id,
                    minPrice: tier.min_price ?? null,
                    maxPrice: tier.max_price ?? null,
                  })
                }
              >
                {tier.label}
              </button>
            ))}

            <button
              type="button"
              aria-pressed={filters.inStockOnly}
              className={`chip-pill ${filters.inStockOnly ? "active" : ""}`}
              onClick={() => setFilters({ inStockOnly: !filters.inStockOnly })}
            >
              In Stock Only
            </button>
          </div>

          <div className="catalog-meta-controls">
            {hasActiveFilters && (
              <button
                type="button"
                className="link-subtle"
                onClick={resetFilters}
                style={{ fontSize: "var(--text-xs)" }}
              >
                Reset filters
              </button>
            )}

            {sortOptions.length > 0 && (
              <select
                className="select-control sort-select"
                value={filters.sort}
                onChange={(e) => setFilters({ sort: e.target.value })}
                aria-label="Sort garments"
              >
                {sortOptions.map((opt) => (
                  <option key={opt.id} value={opt.id}>
                    {opt.label}
                  </option>
                ))}
              </select>
            )}

            <span className="catalog-counter" aria-live="polite">
              {catalogTotal || catalog.length} {(catalogTotal || catalog.length) === 1 ? "piece" : "pieces"}
            </span>
          </div>
        </div>

        {/* Natural-Language Search Interpretation Strip */}
        {showInterpretation && (
          <div className="search-interpretation-bar" role="status" aria-live="polite">
            <span className="interpretation-lead">
              <Icon name="sparkles" size={13} />
              <span>Matched facets:</span>
            </span>
            <div className="interpretation-chips">
              {recognizedTokens.map((tok, idx) => (
                <span key={`${tok.dimension}-${tok.value || tok.target}-${idx}`} className="interpretation-chip">
                  <strong>{tok.dimension.replace(/_/g, " ")}:</strong> {tok.label || tok.value || tok.target}
                </span>
              ))}
              {priceCaption && (
                <span className="interpretation-chip">
                  <strong>budget:</strong> {priceCaption}
                </span>
              )}
              {searchInterpretation?.relaxed && (
                <span className="interpretation-relaxed">
                  Showing closest matches using structured filters
                </span>
              )}
            </div>
          </div>
        )}
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
        {!isLoadingCatalog && !catalogError && catalog.length === 0 && (
          <StatePanel
            type="no_results"
            title="No garments found"
            description={
              filters.q
                ? `No pieces matched "${filters.q}". Try broadening your search or clearing active filters.`
                : "No pieces match the selected department, attribute, and price filters."
            }
            actionLabel="Clear all filters"
            onAction={resetFilters}
          />
        )}

        {/* Grid of Products */}
        {!isLoadingCatalog && !catalogError && catalog.length > 0 && (
          <div className="product-grid" role="list">
            {catalog.map((prod) => (
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
