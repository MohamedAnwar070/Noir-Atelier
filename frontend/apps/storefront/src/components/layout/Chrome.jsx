"use client";

import React, { useState } from "react";
import Link from "next/link";
import { Icon } from "@/components/ui/Icon";
import { BrandLogo, BrandMonogram } from "@/components/ui/BrandLogo";
import { useStore } from "@/store/StoreProvider";
import { formatInr } from "@noir/utils/formatters.js";

export function AnnouncementBar() {
  const { business, freeShippingMin, taxRules } = useStore();
  const returnDays = business?.returns_and_refunds?.return_window_days ?? 7;
  const signatureMin = Number(business?.shipping?.signature_required_above_inr ?? 15000);
  const hsnChapters = (taxRules?.hsnChapters || ["61", "62"]).join("/");

  return (
    <aside className="announcement-bar" role="note" aria-label="Maison client privileges">
      <div className="announcement-bar-inner">
        <span>Complimentary Boutique Delivery over {formatInr(freeShippingMin)}</span>
        <span className="announcement-dot" aria-hidden="true">·</span>
        <span>Insured White-Glove Courier over {formatInr(signatureMin)}</span>
        <span className="announcement-dot" aria-hidden="true">·</span>
        <span>{returnDays}-Day Security-Seal Returns</span>
        <span className="announcement-dot announcement-hide-sm" aria-hidden="true">·</span>
        <span className="announcement-hide-sm">CBIC GST Certified (HSN {hsnChapters})</span>
      </div>
    </aside>
  );
}

export function SiteHeader() {
  const {
    activeDepartment,
    setActiveDepartment,
    catalogMeta,
    searchQuery,
    setSearchQuery,
    cartCount,
    openDrawer,
    askStylist,
    activePage,
    navigateTo,
    currentActor,
    isStaff,
    switchActor,
    actorsList,
    businessConfig,
    theme,
    setTheme,
  } = useStore();

  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const departments = catalogMeta?.departments || [];
  const brandTitle = (businessConfig?.store?.name || "NOIR ATELIER").toUpperCase();

  return (
    <header className="site-header">
      <div className="site-header-inner">
        {/* Brand Identity & Editorial Navigation */}
        <div className="brand-group">
          <Link
            href="/"
            className="brand-logo"
            aria-label={`${brandTitle} — Home`}
            onClick={() => {
              setActiveDepartment("ALL");
              navigateTo("shop");
            }}
          >
            <BrandLogo
              variant="horizontal"
              title={brandTitle}
              subtitle="MAISON DE HAUTE CONFECTION"
            />
          </Link>

          <nav className="primary-nav" aria-label="Garment Collections">
            <button
              type="button"
              className={`nav-link ${activePage === "shop" && activeDepartment === "ALL" ? "active" : ""}`}
              onClick={() => {
                setActiveDepartment("ALL");
                navigateTo("shop");
              }}
            >
              The Archive
            </button>
            {departments.map((dept) => (
              <button
                key={dept.code}
                type="button"
                className={`nav-link ${activePage === "shop" && activeDepartment === dept.code ? "active" : ""}`}
                onClick={() => {
                  setActiveDepartment(dept.code);
                  navigateTo("shop");
                }}
              >
                {dept.name}
              </button>
            ))}
            <button
              type="button"
              className={`nav-link ${activePage === "policies" ? "active" : ""}`}
              onClick={() => navigateTo("policies")}
            >
              Provenance &amp; Policies
            </button>
            {isStaff && (
              <button
                type="button"
                className={`nav-link ${activePage === "admin" ? "active" : ""}`}
                onClick={() => navigateTo("admin")}
              >
                Governance
              </button>
            )}
          </nav>
        </div>

        {/* Natural-Language Archive Search */}
        <div className="header-search">
          <span className="header-search-icon">
            <Icon name="search" size={14} />
          </span>
          <input
            type="search"
            placeholder="Search cashmere coat, silk gown, linen shirt, PRD-041…"
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value);
              if (activePage !== "shop") navigateTo("shop");
            }}
            aria-label="Search curated garments"
          />
          {searchQuery && (
            <button
              type="button"
              className="header-search-clear"
              onClick={() => setSearchQuery("")}
              aria-label="Clear search query"
            >
              <Icon name="close" size={12} />
            </button>
          )}
        </div>

        {/* Client & Maison Controls */}
        <div className="header-actions">
          <div className="header-desktop-controls">
            <select
              className="header-pill-select"
              value={currentActor?.token || ""}
              onChange={(e) => switchActor(e.target.value)}
              aria-label="Switch client or staff profile"
            >
              {(actorsList || []).map((a) => (
                <option key={a.token} value={a.token}>
                  {a.label}
                </option>
              ))}
            </select>

            <button
              type="button"
              className="header-icon-btn"
              onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
              aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} atelier theme`}
              title={theme === "dark" ? "Switch to Alabaster Light" : "Switch to Noir Obsidian"}
            >
              <Icon name={theme === "dark" ? "sun" : "moon"} size={14} />
              <span>{theme === "dark" ? "Alabaster" : "Noir"}</span>
            </button>

            <button
              type="button"
              className="header-icon-btn"
              onClick={() => askStylist()}
              aria-label="Consult Personal Fashion Consultant"
            >
              <BrandMonogram size={15} />
              <span>Stylist</span>
            </button>
          </div>

          <button
            type="button"
            className={`btn-pill btn-pill-outline header-action-btn ${activePage === "orders" ? "active" : ""}`}
            onClick={() => navigateTo("orders")}
            aria-label="Orders and returns"
          >
            <Icon name="package" size={14} />
            <span>Orders</span>
          </button>

          <button
            type="button"
            className="btn-pill header-action-btn"
            onClick={() => openDrawer("bag")}
            aria-label={`Shopping bag with ${cartCount} items`}
          >
            <Icon name="bag" size={14} />
            <span>Bag ({cartCount})</span>
          </button>

          <button
            type="button"
            className="mobile-menu-btn"
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            aria-label="Toggle navigation menu"
            aria-expanded={mobileMenuOpen}
          >
            <Icon name={mobileMenuOpen ? "close" : "menu"} size={18} />
          </button>
        </div>
      </div>

      {/* Mobile Navigation Drawer */}
      <div className={`mobile-nav-drawer ${mobileMenuOpen ? "open" : ""}`} aria-label="Mobile Navigation">
        <div className="mobile-nav-grid">
          <button
            type="button"
            className={`chip-pill ${activePage === "shop" && activeDepartment === "ALL" ? "active" : ""}`}
            onClick={() => {
              setActiveDepartment("ALL");
              navigateTo("shop");
              setMobileMenuOpen(false);
            }}
          >
            The Archive (All)
          </button>
          {departments.map((dept) => (
            <button
              key={dept.code}
              type="button"
              className={`chip-pill ${activePage === "shop" && activeDepartment === dept.code ? "active" : ""}`}
              onClick={() => {
                setActiveDepartment(dept.code);
                navigateTo("shop");
                setMobileMenuOpen(false);
              }}
            >
              {dept.name}
            </button>
          ))}
          <button
            type="button"
            className={`chip-pill ${activePage === "orders" ? "active" : ""}`}
            onClick={() => {
              navigateTo("orders");
              setMobileMenuOpen(false);
            }}
          >
            Orders &amp; Returns
          </button>
          <button
            type="button"
            className={`chip-pill ${activePage === "policies" ? "active" : ""}`}
            onClick={() => {
              navigateTo("policies");
              setMobileMenuOpen(false);
            }}
          >
            Provenance &amp; Policies
          </button>
          <button
            type="button"
            className="chip-pill"
            onClick={() => {
              askStylist();
              setMobileMenuOpen(false);
            }}
          >
            Personal Stylist
          </button>
          {isStaff && (
            <button
              type="button"
              className={`chip-pill ${activePage === "admin" ? "active" : ""}`}
              onClick={() => {
                navigateTo("admin");
                setMobileMenuOpen(false);
              }}
            >
              Governance Portal
            </button>
          )}
        </div>

        <div className="mobile-nav-controls">
          <select
            className="header-pill-select"
            value={currentActor?.token || ""}
            onChange={(e) => {
              switchActor(e.target.value);
              setMobileMenuOpen(false);
            }}
            aria-label="Mobile credential switcher"
          >
            {(actorsList || []).map((a) => (
              <option key={a.token} value={a.token}>
                {a.label}
              </option>
            ))}
          </select>
          <button
            type="button"
            className="chip-pill"
            onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          >
            <Icon name={theme === "dark" ? "sun" : "moon"} size={14} />
            <span>{theme === "dark" ? "Alabaster" : "Noir"}</span>
          </button>
        </div>
      </div>
    </header>
  );
}

export function MobileTabBar() {
  const { activePage, navigateTo, cartCount, openDrawer, askStylist } = useStore();

  return (
    <nav className="mobile-bottom-nav" aria-label="Mobile Navigation">
      <button
        type="button"
        className={`mobile-tab-btn ${activePage === "shop" ? "active" : ""}`}
        onClick={() => navigateTo("shop")}
      >
        <Icon name="home" size={18} />
        <span>Archive</span>
      </button>

      <button
        type="button"
        className="mobile-tab-btn"
        onClick={() => askStylist()}
      >
        <BrandMonogram size={18} />
        <span>Stylist</span>
      </button>

      <button
        type="button"
        className="mobile-tab-btn"
        onClick={() => openDrawer("bag")}
      >
        <Icon name="bag" size={18} />
        <span>Bag ({cartCount})</span>
      </button>

      <button
        type="button"
        className={`mobile-tab-btn ${activePage === "orders" ? "active" : ""}`}
        onClick={() => navigateTo("orders")}
      >
        <Icon name="package" size={18} />
        <span>Orders</span>
      </button>
    </nav>
  );
}

export function SiteFooter() {
  const {
    businessConfig,
    catalogMeta,
    catalogTotal,
    setActiveDepartment,
    navigateTo,
    askStylist,
    freeShippingMin,
    taxRules,
  } = useStore();

  const name = businessConfig?.store?.name || "Noir Atelier";
  const departments = catalogMeta?.departments || [];
  const deptNames = departments.map((d) => d.name).join(", ");
  const curatedTarget = businessConfig?.catalog?.curated_collection_target || catalogTotal || 100;
  const signatureMin = Number(businessConfig?.shipping?.signature_required_above_inr ?? 15000);
  const returnDays = businessConfig?.returns_and_refunds?.return_window_days ?? 7;
  const hsnChapters = (taxRules?.hsnChapters || ["61", "62"]).join("/");

  return (
    <footer className="site-footer">
      <div className="site-footer-grid">
        <div className="footer-brand-col">
          <BrandLogo
            variant="horizontal"
            title={name.toUpperCase()}
            subtitle="MAISON DE HAUTE CONFECTION"
          />
          <p className="footer-manifesto">
            An established fashion house presenting a strictly curated {curatedTarget}-garment archive
            {deptNames ? ` across ${deptNames}` : ""}. Tailored from certified natural fibers—Belgian flax,
            Como mulberry silk, Himalayan cashmere, and heritage Indian handlooms.
          </p>
        </div>

        <div className="footer-nav-col">
          <h3 className="footer-heading">The Archive</h3>
          <ul className="footer-links">
            <li>
              <button
                type="button"
                className="link-subtle"
                onClick={() => {
                  setActiveDepartment("ALL");
                  navigateTo("shop");
                }}
              >
                Complete Collection
              </button>
            </li>
            {departments.map((dept) => (
              <li key={dept.code}>
                <button
                  type="button"
                  className="link-subtle"
                  onClick={() => {
                    setActiveDepartment(dept.code);
                    navigateTo("shop");
                  }}
                >
                  {dept.name}&apos;s Edit
                </button>
              </li>
            ))}
          </ul>
        </div>

        <div className="footer-nav-col">
          <h3 className="footer-heading">Private Client Care</h3>
          <ul className="footer-links">
            <li>
              <button type="button" className="link-subtle" onClick={() => askStylist()}>
                Personal Fashion Consultant
              </button>
            </li>
            <li>
              <button type="button" className="link-subtle" onClick={() => navigateTo("orders")}>
                Orders &amp; Dispatch Tracking
              </button>
            </li>
            <li>
              <button type="button" className="link-subtle" onClick={() => navigateTo("policies")}>
                GST &amp; {returnDays}-Day Return Charter
              </button>
            </li>
          </ul>
        </div>

        <div className="footer-nav-col">
          <h3 className="footer-heading">Atelier Assurance</h3>
          <ul className="footer-assurance-list">
            <li>
              <Icon name="shield" size={13} />
              <span>Numbered Security Ribbon (POL-RET-01)</span>
            </li>
            <li>
              <Icon name="truck" size={13} />
              <span>Complimentary Delivery over {formatInr(freeShippingMin)}</span>
            </li>
            <li>
              <Icon name="award" size={13} />
              <span>Insured Signature Courier over {formatInr(signatureMin)}</span>
            </li>
            <li>
              <Icon name="check" size={13} />
              <span>Statutory GST Invoices (CBIC HSN {hsnChapters})</span>
            </li>
          </ul>
        </div>
      </div>

      <div className="site-footer-bottom">
        <span>© {new Date().getFullYear()} {name}. All prices include statutory Goods &amp; Services Tax (INR).</span>
        <span>4-Point Hand-Tacked Woven Label · Tamper-Evident Provenance</span>
      </div>
    </footer>
  );
}
