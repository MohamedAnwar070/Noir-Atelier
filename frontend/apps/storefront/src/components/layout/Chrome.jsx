"use client";

import React, { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Icon } from "@/components/ui/Icon";
import { useStore } from "@/store/StoreProvider";
import { formatInr } from "@noir/utils/formatters.js";

export function AnnouncementBar() {
  const { business, freeShippingMin } = useStore();
  const returnDays = business?.returns_and_refunds?.return_window_days || 7;
  const freeThreshold = freeShippingMin; // from business config

  return (
    <aside className="announcement-bar" role="note" aria-label="Store privileges">
      <div className="announcement-bar-inner">
        <span>Complimentary Boutique Delivery over {formatInr(freeThreshold)}</span>
        <span className="announcement-dot">·</span>
        <span>{returnDays}-Day Atelier Returns</span>
        <span className="announcement-dot">·</span>
        <span>CBIC GST Certified (HSN 61/62)</span>
      </div>
    </aside>
  );
}

export function SiteHeader() {
  const {
    activeDepartment,
    setActiveDepartment,
    categories,
    searchQuery,
    setSearchQuery,
    cartCount,
    openDrawer,
    activePage,
    navigateTo,
    currentActor,
    switchActor,
    actorsList,
    theme,
    setTheme,
  } = useStore();

  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  return (
    <header className="site-header">
      <div className="site-header-inner">
        {/* Brand & Desktop Navigation */}
        <div className="brand-group">
          <Link
            href="/"
            className="brand-logo"
            onClick={() => {
              setActiveDepartment("ALL");
              navigateTo("shop");
            }}
          >
            NOIR ATELIER
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
              The Edit
            </button>
            {["MEN", "WOMEN", "KIDS"].map((dept) => (
              <button
                key={dept}
                type="button"
                className={`nav-link ${activePage === "shop" && activeDepartment === dept ? "active" : ""}`}
                onClick={() => {
                  setActiveDepartment(dept);
                  navigateTo("shop");
                }}
              >
                {dept.charAt(0) + dept.slice(1).toLowerCase()}
              </button>
            ))}
            <button
              type="button"
              className={`nav-link ${activePage === "policies" ? "active" : ""}`}
              onClick={() => navigateTo("policies")}
            >
              Policies
            </button>
            {["manager", "finance_admin", "admin"].includes(currentActor?.role) && (
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

        {/* Global Search Bar */}
        <div className="header-search">
          <span className="header-search-icon">
            <Icon name="search" size={15} />
          </span>
          <input
            type="search"
            placeholder="Search linen, silk, merino…"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            aria-label="Search garments"
          />
        </div>

        {/* Actions Group */}
        <div className="header-actions">
          <div className="header-desktop-controls">
            {/* Demo credential profile switcher */}
            <select
              className="header-pill-select"
              value={currentActor?.token || ""}
              onChange={(e) => switchActor(e.target.value)}
              aria-label="Switch client or staff credentials"
            >
              {(actorsList || []).map((a) => (
                <option key={a.token} value={a.token}>
                  {a.label}
                </option>
              ))}
            </select>

            {/* Theme switcher */}
            <button
              type="button"
              className="chip-pill"
              onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
              aria-label="Toggle color theme"
              title="Switch light or dark atelier theme"
            >
              <Icon name={theme === "dark" ? "sun" : "moon"} size={14} />
              <span>{theme === "dark" ? "Light" : "Noir"}</span>
            </button>
          </div>

          {/* Orders Link */}
          <button
            type="button"
            className={`btn-pill btn-pill-outline ${activePage === "orders" ? "active" : ""}`}
            onClick={() => navigateTo("orders")}
            style={{ padding: "0.45rem 0.95rem", fontSize: "var(--text-xs)" }}
            aria-label="Orders and returns"
          >
            <Icon name="package" size={14} />
            <span>Orders</span>
          </button>

          {/* Shopping Bag Button */}
          <button
            type="button"
            className="btn-pill"
            style={{ padding: "0.45rem 1.05rem", fontSize: "var(--text-xs)" }}
            onClick={() => openDrawer("bag")}
            aria-label={`Shopping bag with ${cartCount} items`}
          >
            <Icon name="bag" size={14} />
            <span>Bag ({cartCount})</span>
          </button>

          {/* Mobile Hamburger Button */}
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
            The Edit (All)
          </button>
          {["MEN", "WOMEN", "KIDS"].map((dept) => (
            <button
              key={dept}
              type="button"
              className={`chip-pill ${activePage === "shop" && activeDepartment === dept ? "active" : ""}`}
              onClick={() => {
                setActiveDepartment(dept);
                navigateTo("shop");
                setMobileMenuOpen(false);
              }}
            >
              {dept.charAt(0) + dept.slice(1).toLowerCase()}
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
            Atelier Policies
          </button>
          {["manager", "finance_admin", "admin"].includes(currentActor?.role) && (
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

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.5rem" }}>
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
            <span>{theme === "dark" ? "Light" : "Noir"}</span>
          </button>
        </div>
      </div>
    </header>
  );
}

export function MobileTabBar() {
  const { activePage, navigateTo, cartCount, openDrawer } = useStore();

  return (
    <nav className="mobile-bottom-nav" aria-label="Mobile Navigation">
      <button
        type="button"
        className={`mobile-tab-btn ${activePage === "shop" ? "active" : ""}`}
        onClick={() => navigateTo("shop")}
      >
        <Icon name="home" size={18} />
        <span>The Edit</span>
      </button>

      <button
        type="button"
        className={`mobile-tab-btn ${activePage === "orders" ? "active" : ""}`}
        onClick={() => navigateTo("orders")}
      >
        <Icon name="package" size={18} />
        <span>Orders</span>
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
        className={`mobile-tab-btn ${activePage === "policies" ? "active" : ""}`}
        onClick={() => navigateTo("policies")}
      >
        <Icon name="shield" size={18} />
        <span>Policies</span>
      </button>
    </nav>
  );
}

export function SiteFooter() {
  const { businessConfig, categories, setActiveDepartment, navigateTo } = useStore();
  const name = businessConfig?.store?.name || "Noir Atelier";

  return (
    <footer className="site-footer">
      <div className="site-footer-inner">
        <div>
          <p className="brand-logo" style={{ fontSize: "var(--text-lg)" }}>
            {name}
          </p>
          <p style={{ margin: "0.25rem 0 0", color: "var(--text-muted)", fontSize: "11px" }}>
            Tailored luxury garments for Men, Women and Kids — crafted with pure natural fibers in India.
          </p>
        </div>

        <div style={{ display: "flex", gap: "1.5rem", flexWrap: "wrap", alignItems: "center" }}>
          <button
            type="button"
            className="link-subtle"
            onClick={() => {
              setActiveDepartment("ALL");
              navigateTo("shop");
            }}
          >
            The Collection
          </button>
          <button
            type="button"
            className="link-subtle"
            onClick={() => navigateTo("orders")}
          >
            Order Tracking
          </button>
          <button
            type="button"
            className="link-subtle"
            onClick={() => navigateTo("policies")}
          >
            GST &amp; Returns
          </button>
        </div>

        <div style={{ fontSize: "11px", color: "var(--text-muted)" }}>
          © {new Date().getFullYear()} {name}. All prices include statutory Goods &amp; Services Tax (CBIC HSN 61/62).
        </div>
      </div>
    </footer>
  );
}
