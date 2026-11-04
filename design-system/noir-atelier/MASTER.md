# Noir Atelier — Design System Master (`@noir/ui`)

## 1. Aesthetic Direction & Calibration
- **Domain:** Curated Luxury Fashion House (~100 Pieces, Everyday Sartorial to Multi-Lakh Haute Archive)
- **Design Dials:**
  - `DESIGN_VARIANCE`: **3 / 10** — Disciplined architectural editorial grid with asymmetric hero storytelling and consistent 3:4 portrait garment framing.
  - `MOTION_INTENSITY`: **3 / 10** — Quiet, composed opacity and border transitions (`180ms–280ms cubic-bezier(0.22, 1, 0.36, 1)`); zero bouncy spring overshoots; full `prefers-reduced-motion: reduce` support.
  - `VISUAL_DENSITY`: **2 / 10** — Generous gallery whitespace, collapsible sartorial filter drawer (no crowded chip walls), and unhurried vertical rhythm.

## 2. Spatial & Geometric Tokens
- **Container Max Width:** `1380px` (`--container-max`) with fluid horizontal gutters `clamp(1.15rem, 3.2vw, 3rem)`.
- **Sartorial Corner Radii (Architectural Tailoring over SaaS Pills):**
  - `--radius-xs`: `2px` (size selectors, archival tags, inputs)
  - `--radius-sm`: `3px` (buttons, summary panels, filter chips)
  - `--radius-md`: `4px` (3:4 portrait garment frames, product cards)
  - `--radius-card`: `4px` (`--card-radius`)
  - `--radius-sheet`: `6px` (modals, side drawers; `16px 16px 0 0` on mobile bottom sheets)
- **Hairline Borders & Shadows:**
  - Primary structure relies on `1px solid var(--border-subtle)` rather than heavy drop shadows.
  - Elevation shadows (`--shadow-soft`, `--shadow-elevated`) are reserved strictly for floating overlays, modals, drawers, and subtle card focus states.

## 3. High-Value Piece UX Standards (`₹50,000` – `₹4,85,000+`)
1. **Edition Distinction:** Pieces meeting `business_config.catalog.couture_tier_min_inr` (`₹1,00,000+`) or `high_value_tier_min_inr` (`₹50,000+`) display understated *Haute Archive* or *Private Reserve* provenance indicators—never garish badges.
2. **Authenticity & Woven Label Specimen:** Product Detail Dossiers surface the garment's exact fiber percentages, country/atelier of origin, woven damask label specification, and `POL-RET-01` numbered security ribbon verification.
3. **Payment Limit Transparency:** Checkout dynamically validates each payment method's `min_order_inr` and `max_order_inr` from PostgreSQL (automatically guiding carts above `₹1,00,000` NPCI UPI limits toward **Credit/Debit Card** or **IMPS / NEFT Bank Wire** up to `₹5,00,000`).
4. **White-Glove Delivery & Concierge:** Displays mandatory recipient signature assurance (`signature_required_above_inr`) and one-click *Consult Personal Stylist* contextual handoff.

## 4. Accessibility & Responsive Invariants
- **Contrast:** All body, secondary, muted, and bronze accent text tokens meet WCAG 2.1 AA (`>= 4.5:1`) in both Editorial Light and Noir Obsidian themes.
- **Touch & Keyboard:** Minimum `44px × 44px` interactive targets on touch/mobile viewports; `:focus-visible` `2px` antique bronze focus ring; trapped focus and `Escape` dismissal on stacked modals/drawers.
- **Container Queries:** Maintained on `@container hero`, `@container catalog`, `@container card`, and `@container kpis` alongside viewport breakpoints (`375px`, `640px`, `768px`, `1024px`, `1440px`).
