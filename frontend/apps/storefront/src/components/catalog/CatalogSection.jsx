"use client";

import React, { useState } from "react";
import { useStore } from "@/store/StoreProvider";
import { ProductCard } from "@/components/catalog/ProductCard";
import { ProductGridSkeleton, StatePanel } from "@/components/ui/StatePanel";
import { BrandMonogram } from "@/components/ui/BrandLogo";
import { Icon } from "@/components/ui/Icon";
import { formatInr } from "@noir/utils/formatters.js";

export function CatalogSection({ onSelectProduct }) {
  const {
    catalog,
    catalogTotal,
    hasMoreProducts,
    isLoadingMore,
    loadMoreProducts,
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
    askStylist,
  } = useStore();

  const [facetsOpen, setFacetsOpen] = useState(false);

  const departments = catalogMeta?.departments || [];
  const categories = (catalogMeta?.categories || []).filter((c) => (c.product_count ?? 0) > 0);
  const colorFamilies = catalogMeta?.color_families || [];
  const materialFamilies = catalogMeta?.material_families || [];
  const priceTiers = catalogMeta?.price_tiers || [];
  const sortOptions = catalogMeta?.sort_options || [];
  const returnDays = business?.returns_and_refunds?.return_window_days ?? 7;
  const signatureMin = Number(business?.shipping?.signature_required_above_inr ?? 15000);
  const hsnChapters = (taxRules?.hsnChapters || ["61", "62"]).join("/");
  const heroImageUrl = storefrontConfig?.hero_image_url || "";
  const heroImageAlt = storefrontConfig?.hero_image_alt || "Noir Atelier Curated Archive";

  // Highest price tier from DB config for the hero's direct "Explore Haute Archive" action
  const flagshipTier =
    priceTiers.length > 1 ? priceTiers[priceTiers.length - 1] : null;

  const activeFacetCount = [
    filters.category,
    filters.color,
    filters.material,
    filters.priceTier && filters.priceTier !== "ALL" ? filters.priceTier : "",
    filters.inStockOnly ? "stock" : "",
  ].filter(Boolean).length;

  const activeCategoryObj = categories.find((c) => c.slug === filters.category);
  const activeColorObj = colorFamilies.find((cf) => cf.family === filters.color);
  const activeMaterialObj = materialFamilies.find((mf) => mf.family === filters.material);
  const activeTierObj = priceTiers.find((t) => t.id === filters.priceTier && t.id !== "ALL");

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

  const totalCount = catalogTotal || catalog.length;

  return (
    <section className="catalog-section" aria-label="Garment Collection">
      {/* Asymmetric Editorial Maison Hero */}
      <div className={`catalog-hero-editorial ${heroImageUrl ? "has-media" : ""}`}>
        <div className="hero-content-stack">
          <div className="hero-eyebrow-row">
            <BrandMonogram size={22} />
            <span className="hero-eyebrow">
              {storefrontConfig.hero_eyebrow || "Maison de Haute Confection · Curated Archive"}
            </span>
          </div>

          <h1 className="hero-headline">
            {storefrontConfig.hero_title || "The New Edit"}
          </h1>

          <p className="hero-description">
            {storefrontConfig.hero_subtitle ||
              "Handcrafted tailored linen, mulberry silk dresses, and fine merino garments with real-time GST slab intelligence."}
          </p>

          <div className="hero-cta-row">
            {flagshipTier && (
              <button
                type="button"
                className="btn-pill"
                onClick={() =>
                  setFilters({
                    priceTier: flagshipTier.id,
                    minPrice: flagshipTier.min_price ?? null,
                    maxPrice: flagshipTier.max_price ?? null,
                  })
                }
              >
                <Icon name="award" size={14} />
                <span>Explore {flagshipTier.label.split("·")[0].trim()}</span>
              </button>
            )}
            <button
              type="button"
              className="btn-pill btn-pill-outline"
              onClick={() =>
                askStylist("Recommend standout pieces from the collection based on natural fiber craftsmanship.")
              }
            >
              <BrandMonogram size={14} />
              <span>Consult Personal Stylist</span>
            </button>
          </div>

          <div className="hero-guarantees-row" aria-label="Maison guarantees">
            <span className="guarantee-pill">
              <Icon name="shield" size={13} />
              <span>POL-RET-01 Security Seal</span>
            </span>
            <span className="guarantee-pill">
              <Icon name="truck" size={13} />
              <span>Insured Courier over {formatInr(signatureMin)}</span>
            </span>
            <span className="guarantee-pill">
              <Icon name="refresh" size={13} />
              <span>{returnDays}-Day Return Charter</span>
            </span>
            <span className="guarantee-pill">
              <Icon name="check" size={13} />
              <span>CBIC HSN {hsnChapters} Certified · Free Shipping {formatInr(freeShippingMin)}+</span>
            </span>
          </div>
        </div>

        {heroImageUrl && (
          <figure className="hero-portrait-frame">
            <img
              src={heroImageUrl}
              alt={heroImageAlt}
              className="hero-portrait-img"
            />
            <figcaption className="hero-portrait-caption">
              <span>Noir Atelier Archive</span>
              <span>Certified Natural Fibers</span>
            </figcaption>
          </figure>
        )}
      </div>

      {/* Sartorial Collection Bar */}
      <div className="catalog-toolbar">
        <div className="catalog-primary-bar">
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

          {/* Right-side Tailor, Sort & Piece Counter */}
          <div className="catalog-meta-controls">
            <button
              type="button"
              className={`filter-toggle-btn ${facetsOpen || activeFacetCount > 0 ? "active" : ""}`}
              onClick={() => setFacetsOpen((prev) => !prev)}
              aria-expanded={facetsOpen}
              aria-controls="atelier-facets-panel"
            >
              <Icon name="sliders" size={14} />
              <span>Filter &amp; Tailor</span>
              {activeFacetCount > 0 && (
                <span className="filter-count-badge">{activeFacetCount}</span>
              )}
            </button>

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
              {totalCount} {totalCount === 1 ? "piece" : "pieces"}
            </span>
          </div>
        </div>

        {/* Edition / Price Tier Strip (Always accessible, quiet horizontal bar) */}
        {priceTiers.length > 0 && (
          <div className="catalog-sub-toolbar">
            <div className="price-tier-pills" role="radiogroup" aria-label="Edition and price tiers">
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
                In Vault Now
              </button>
            </div>
          </div>
        )}

        {/* Collapsible Structured Attribute Atelier Panel */}
        {facetsOpen && (categories.length > 0 || colorFamilies.length > 0 || materialFamilies.length > 0) && (
          <div
            id="atelier-facets-panel"
            className="catalog-facets-bar"
            aria-label="Garment attribute filters"
          >
            {categories.length > 0 && (
              <div className="facet-group" role="group" aria-label="Garment silhouette">
                <span className="facet-label">Silhouette</span>
                <div className="facet-pills">
                  <button
                    type="button"
                    className={`chip-pill ${!filters.category ? "active" : ""}`}
                    onClick={() => setFilters({ category: "" })}
                  >
                    All Silhouettes
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
                <span className="facet-label">Natural Fiber</span>
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

        {/* Active Filter Summary Chips */}
        {hasActiveFilters && (
          <div className="active-filters-strip" aria-label="Active collection filters">
            <span className="active-filters-label">Tailored by:</span>
            {filters.q && (
              <button
                type="button"
                className="active-filter-chip"
                onClick={() => setFilters({ q: "" })}
              >
                <span>&ldquo;{filters.q}&rdquo;</span>
                <Icon name="close" size={11} />
              </button>
            )}
            {activeCategoryObj && (
              <button
                type="button"
                className="active-filter-chip"
                onClick={() => setFilters({ category: "" })}
              >
                <span>{activeCategoryObj.name}</span>
                <Icon name="close" size={11} />
              </button>
            )}
            {activeColorObj && (
              <button
                type="button"
                className="active-filter-chip"
                onClick={() => setFilters({ color: "" })}
              >
                <span>{activeColorObj.label}</span>
                <Icon name="close" size={11} />
              </button>
            )}
            {activeMaterialObj && (
              <button
                type="button"
                className="active-filter-chip"
                onClick={() => setFilters({ material: "" })}
              >
                <span>{activeMaterialObj.label}</span>
                <Icon name="close" size={11} />
              </button>
            )}
            {activeTierObj && (
              <button
                type="button"
                className="active-filter-chip"
                onClick={() => setFilters({ priceTier: "ALL", minPrice: null, maxPrice: null })}
              >
                <span>{activeTierObj.label}</span>
                <Icon name="close" size={11} />
              </button>
            )}
            {filters.inStockOnly && (
              <button
                type="button"
                className="active-filter-chip"
                onClick={() => setFilters({ inStockOnly: false })}
              >
                <span>In Vault Now</span>
                <Icon name="close" size={11} />
              </button>
            )}
            <button type="button" className="link-subtle" onClick={resetFilters}>
              Reset archive view
            </button>
          </div>
        )}

        {/* Natural-Language Search Interpretation Strip */}
        {showInterpretation && (
          <div className="search-interpretation-bar" role="status" aria-live="polite">
            <span className="interpretation-lead">
              <Icon name="sparkles" size={13} />
              <span>Interpreted attributes:</span>
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
                  Showing closest matches from the curated archive
                </span>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Main Content Area: State-Driven Rendering */}
      <div className="catalog-grid-area">
        {isLoadingCatalog && <ProductGridSkeleton count={8} />}

        {!isLoadingCatalog && catalogError && (
          <StatePanel
            type="error"
            title="Unable to load archive"
            description={catalogError}
            actionLabel="Try again"
            onAction={refreshCatalog}
          />
        )}

        {!isLoadingCatalog && !catalogError && catalog.length === 0 && (
          <StatePanel
            type="no_results"
            title="No garments match this selection"
            description={
              filters.q
                ? `No archive pieces matched "${filters.q}". Try broadening your phrasing or resetting active facets.`
                : "No pieces match the selected department, fiber, and edition filters."
            }
            actionLabel="Reset archive filters"
            onAction={resetFilters}
          />
        )}

        {!isLoadingCatalog && !catalogError && catalog.length > 0 && (
          <>
            <div className="product-grid" role="list">
              {catalog.map((prod) => (
                <ProductCard
                  key={prod.product_id}
                  product={prod}
                  onSelect={onSelectProduct}
                />
              ))}
            </div>

            {/* Curated Archive Pagination Footer */}
            <div className="catalog-pagination-footer">
              <p className="catalog-pagination-summary">
                Showing <strong>{catalog.length}</strong> of <strong>{totalCount}</strong> curated pieces
              </p>
              <div className="catalog-pagination-track" aria-hidden="true">
                <div
                  className="catalog-pagination-fill"
                  style={{ width: `${Math.min(100, Math.round((catalog.length / Math.max(1, totalCount)) * 100))}%` }}
                />
              </div>
              {hasMoreProducts && (
                <button
                  type="button"
                  className="btn-pill btn-pill-outline catalog-load-more-btn"
                  onClick={loadMoreProducts}
                  disabled={isLoadingMore}
                >
                  {isLoadingMore ? "Unveiling Archive Pieces…" : "Explore More Pieces"}
                </button>
              )}
            </div>
          </>
        )}
      </div>
    </section>
  );
}
