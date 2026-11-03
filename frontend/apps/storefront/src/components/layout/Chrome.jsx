"use client";

import React, { useEffect, useRef } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import Icon from "@/components/ui/Icon";
import Overlay from "@/components/ui/Overlay";
import { DESIGN_TOKENS } from "@noir/ui/theme.js";
import { ROUTES } from "@/config/ui.config";
import { useStore } from "@/store/StoreProvider";
import { useIsDesktop } from "@/hooks/useMediaQuery";
import { formatInr } from "@noir/utils/formatters.js";

const titleCase = (value = "") => value.charAt(0) + value.slice(1).toLowerCase();

export function AnnouncementBar() {
  const { business, freeShippingMin } = useStore();
  const returnDays = business.returns_and_refunds?.return_window_days;
  const parts = [];
  if (freeShippingMin > 0) parts.push(`Complimentary shipping over ${formatInr(freeShippingMin)}`);
  if (returnDays) parts.push(`${returnDays}-day easy returns`);
  if (!parts.length) return null;
  return (
    <div className="announcement" role="note">
      <div className="container announcement__inner">{parts.join("  ·  ")}</div>
    </div>
  );
}

function useScrollToCollection() {
  const router = useRouter();
  const pathname = usePathname();
  return () => {
    if (pathname !== ROUTES.shop) router.push(`${ROUTES.shop}#collection`);
    else document.getElementById("collection")?.scrollIntoView({ behavior: "smooth", block: "start" });
  };
}

function AccountPanel({ onNavigate }) {
  const { actor, actors, config, isStaff, switchActor, theme, setTheme, fontScale, setFontScale } = useStore();
  return (
    <div className="account-panel">
      <div className="account-panel__who">
        <span className="avatar" aria-hidden="true">{(actor?.label || "G").charAt(0)}</span>
        <div>
          <strong>{actor?.label?.split("(")[0]?.trim() || "Guest"}</strong>
          <span className="muted">{actor?.loyalty_tier ? actor.loyalty_tier.replace(/_/g, " ").toLowerCase() : "Welcome"}</span>
        </div>
      </div>
      <nav className="account-panel__links" aria-label="Account">
        <Link href={ROUTES.orders} onClick={onNavigate}><Icon name="package" size={16} /> My orders & returns</Link>
        <Link href={ROUTES.policies} onClick={onNavigate}><Icon name="shield" size={16} /> Shipping, returns & policies</Link>
        {isStaff && <Link href={ROUTES.admin} onClick={onNavigate}><Icon name="lock" size={16} /> Team console</Link>}
      </nav>

      <div className="account-panel__group">
        <span className="field__label">Appearance</span>
        <div className="segmented" role="group" aria-label="Theme">
          {DESIGN_TOKENS.themes.map((t) => (
            <button key={t.id} type="button" className={theme === t.id ? "is-active" : ""} onClick={() => setTheme(t.id)} aria-pressed={theme === t.id}>
              <Icon name={t.id === "dark" ? "moon" : "sun"} size={14} /> {t.label}
            </button>
          ))}
        </div>
        <div className="segmented" role="group" aria-label="Text size">
          {DESIGN_TOKENS.fontScales.map((f) => (
            <button key={f.id} type="button" className={fontScale === f.id ? "is-active" : ""} onClick={() => setFontScale(f.id)} aria-pressed={fontScale === f.id} title={f.description}>
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {config.demoMode && actors.length > 1 && (
        <div className="account-panel__group">
          <label className="field__label" htmlFor="switch-account">Switch account (demo)</label>
          <select id="switch-account" className="input" value={actor?.token || ""} onChange={(e) => { switchActor(e.target.value); onNavigate?.(); }}>
            {actors.map((a) => (
              <option key={a.token} value={a.token}>{a.label}</option>
            ))}
          </select>
        </div>
      )}
    </div>
  );
}

export function AccountSurface() {
  const { ui, setOverlay } = useStore();
  const isDesktop = useIsDesktop();
  const popoverRef = useRef(null);
  const close = () => setOverlay({ accountOpen: false });

  useEffect(() => {
    if (!ui.accountOpen || !isDesktop) return undefined;
    const onClick = (e) => {
      if (popoverRef.current && !popoverRef.current.contains(e.target) && !e.target.closest("[data-account-trigger]")) close();
    };
    const onKey = (e) => e.key === "Escape" && close();
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [ui.accountOpen, isDesktop]);

  if (!ui.accountOpen) return null;
  if (isDesktop) {
    return (
      <div className="popover" ref={popoverRef} role="dialog" aria-label="Account menu">
        <AccountPanel onNavigate={close} />
      </div>
    );
  }
  return (
    <Overlay open variant="sheet" onClose={close} title="Your account" label="Account menu">
      <AccountPanel onNavigate={close} />
    </Overlay>
  );
}

export function SiteHeader() {
  const { categories, filters, setFilters, resetFilters, cartCount, setOverlay, ui, wishlist, actor } = useStore();
  const pathname = usePathname();
  const goToCollection = useScrollToCollection();

  const selectDepartment = (department) => {
    setFilters({ department });
    goToCollection();
  };

  return (
    <header className="site-header">
      <div className="container site-header__inner">
        <button type="button" className="icon-btn site-header__menu" aria-label="Open menu" onClick={() => setOverlay({ menuOpen: true })}>
          <Icon name="menu" size={20} />
        </button>

        <Link href={ROUTES.shop} className="brand" onClick={() => resetFilters()}>
          Noir Atelier
        </Link>

        <nav className="site-nav" aria-label="Collections">
          <button type="button" className={`site-nav__link ${pathname === ROUTES.shop && filters.department === "ALL" ? "is-active" : ""}`} onClick={() => selectDepartment("ALL")}>
            Shop all
          </button>
          {categories.map((c) => (
            <button key={c.category_id} type="button" className={`site-nav__link ${pathname === ROUTES.shop && filters.department === c.department ? "is-active" : ""}`} onClick={() => selectDepartment(c.department)}>
              {titleCase(c.department)}
            </button>
          ))}
        </nav>

        <form
          className="site-search"
          role="search"
          onSubmit={(e) => {
            e.preventDefault();
            goToCollection();
          }}
        >
          <Icon name="search" size={16} className="site-search__icon" />
          <input type="search" aria-label="Search garments" placeholder="Search linen, silk, merino…" value={filters.q} onChange={(e) => setFilters({ q: e.target.value })} />
        </form>

        <div className="site-actions">
          <div className="site-actions__account">
            <button type="button" className="icon-btn" data-account-trigger aria-label="Account" aria-expanded={ui.accountOpen} onClick={() => setOverlay({ accountOpen: !ui.accountOpen })}>
              <Icon name="user" size={19} />
            </button>
            {pathname !== "/__none" && <AccountSurface />}
          </div>
          <button type="button" className="icon-btn site-actions__wishlist" aria-label={`Wishlist, ${wishlist.length} saved`} onClick={() => setFilters({ q: "" })} hidden>
            <Icon name="heart" size={19} />
          </button>
          <button type="button" className="icon-btn icon-btn--bag" aria-label={`Shopping bag, ${cartCount} item${cartCount === 1 ? "" : "s"}`} onClick={() => setOverlay({ cartOpen: true })}>
            <Icon name="bag" size={19} />
            {cartCount > 0 && <span className="count-badge">{cartCount}</span>}
          </button>
        </div>
      </div>
    </header>
  );
}

export function MobileMenu() {
  const { ui, setOverlay, categories, filters, setFilters } = useStore();
  const goToCollection = useScrollToCollection();
  const close = () => setOverlay({ menuOpen: false });
  const pick = (department) => {
    setFilters({ department });
    close();
    goToCollection();
  };
  return (
    <Overlay open={ui.menuOpen} onClose={close} variant="menu" title="Menu" label="Main menu">
      <nav className="menu-list" aria-label="Collections">
        <button type="button" className={filters.department === "ALL" ? "is-active" : ""} onClick={() => pick("ALL")}>Shop all</button>
        {categories.map((c) => (
          <button key={c.category_id} type="button" className={filters.department === c.department ? "is-active" : ""} onClick={() => pick(c.department)}>
            {titleCase(c.department)} <span className="muted">{c.product_count}</span>
          </button>
        ))}
        <Link href={ROUTES.orders} onClick={close}>My orders & returns</Link>
        <Link href={ROUTES.policies} onClick={close}>Shipping, returns & policies</Link>
      </nav>
    </Overlay>
  );
}

export function MobileTabBar() {
  const pathname = usePathname();
  const { cartCount, setOverlay, ui } = useStore();
  const tabs = [
    { key: "shop", label: "Shop", icon: "home", href: ROUTES.shop },
    { key: "orders", label: "Orders", icon: "package", href: ROUTES.orders },
  ];
  return (
    <nav className="tab-bar" aria-label="Primary">
      {tabs.map((t) => (
        <Link key={t.key} href={t.href} className={`tab-bar__item ${pathname === t.href && !ui.cartOpen && !ui.accountOpen ? "is-active" : ""}`}>
          <Icon name={t.icon} size={20} />
          <span>{t.label}</span>
        </Link>
      ))}
      <button type="button" className={`tab-bar__item ${ui.cartOpen ? "is-active" : ""}`} onClick={() => setOverlay({ cartOpen: true })}>
        <span className="tab-bar__icon">
          <Icon name="bag" size={20} />
          {cartCount > 0 && <span className="count-badge">{cartCount}</span>}
        </span>
        <span>Bag</span>
      </button>
      <button type="button" className={`tab-bar__item ${ui.accountOpen ? "is-active" : ""}`} onClick={() => setOverlay({ accountOpen: true })}>
        <Icon name="user" size={20} />
        <span>Account</span>
      </button>
    </nav>
  );
}

export function SiteFooter() {
  const { business, categories, config, setFilters } = useStore();
  const goToCollection = useScrollToCollection();
  const name = business.store?.name || "Noir Atelier";
  return (
    <footer className="site-footer">
      <div className="container site-footer__grid">
        <div>
          <p className="brand brand--footer">{name}</p>
          <p className="muted">Tailored luxury garments for Men, Women and Kids — made with care in India.</p>
        </div>
        <div>
          <h3 className="footer-heading">Shop</h3>
          <ul>
            {categories.map((c) => (
              <li key={c.category_id}>
                <button type="button" className="link-btn" onClick={() => { setFilters({ department: c.department }); goToCollection(); }}>
                  {titleCase(c.department)}
                </button>
              </li>
            ))}
          </ul>
        </div>
        <div>
          <h3 className="footer-heading">Help</h3>
          <ul>
            <li><Link href={ROUTES.orders}>Track an order</Link></li>
            <li><Link href={ROUTES.policies}>Shipping & returns</Link></li>
            <li><Link href={ROUTES.policies}>Privacy & grievances</Link></li>
          </ul>
        </div>
        <div>
          <h3 className="footer-heading">We accept</h3>
          <ul className="footer-pay">
            {config.paymentMethods.map((p) => (
              <li key={p.method_id}>{p.name}</li>
            ))}
          </ul>
        </div>
      </div>
      <div className="container site-footer__legal">
        <span>© {new Date().getFullYear()} {name}. All prices include GST.</span>
        {business.store?.grievance_officer && <span>Grievance officer: {business.store.grievance_officer}</span>}
      </div>
    </footer>
  );
}
