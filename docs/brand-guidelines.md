# Noir Atelier — Brand Identity & Sartorial System Guidelines

**Positioning:** Established Luxury Fashion House & Curated Digital Maison  
**Catalogue Scale:** ~100 Meticulously Selected Garments (HSN Chapters 61 & 62)  
**Price Architecture:** Everyday Sartorial Essentials (`₹1,899`) to Numbered Haute Archive Pieces (`₹4,65,000+`)

---

## 1. Brand Essence & Positioning

**Noir Atelier** is a private-archive luxury fashion house dedicated exclusively to natural-fiber tailoring, heritage Indian hand-loom couture, and European mill cloths. Unlike high-volume marketplaces, the Maison maintains a strictly curated edit of approximately 100 seasonal and permanent-collection garments across **Men**, **Women**, and **Kids**.

### Core Brand Pillars
1. **Material Integrity:** 100% disclosed fiber composition—European flax linen, extra-fine ZQ Merino, 22–30 momme Mulberry silk, Peruvian Pima cotton, Himalayan Pashmina, and handwoven Kanjeevaram/Zardozi textiles.
2. **Sartorial Restraint:** Architectural proportions, unhurried whitespace, crisp hairline rules, and tactile paper-and-ink contrast—free of artificial gradients, flash-sale banners, or visual noise.
3. **Verifiable Provenance & Trust:** Every garment ships with an individually numbered tamper-evident silk security ribbon (`POL-RET-01`), transparent CBIC HSN 61/62 GST itemisation, and insured white-glove courier delivery.
4. **Personal Client Advisement:** Both human specialists and the Noir Atelier Personal Fashion Consultant AI operate as discreet, knowledgeable wardrobe advisors grounded strictly in live vault inventory and garment specifications.

---

## 2. Logo System & Sartorial Mark Anatomy

All official brand marks live as pure, flat-vector SVGs in `frontend/apps/storefront/public/brand/` and in the React `<BrandLogo />` system (`src/components/ui/BrandLogo.jsx`).

### Anatomy of the `NA` Couture Monogram
- **Octagonal Couture Plaque:** Inspired by bespoke pattern-drafting blocks and woven neck-label corner chamfers (`45°` mitred corners with a fine inner basting-stitch border).
- **Serif-Capped Pillars (`N`):** Two architectural vertical columns anchored by flat sartorial serifs and connected by a clean lapel diagonal.
- **Ascending Needle-Eye Chevron (`A`):** Rises through the `N` in Antique Brushed Bronze (`#8C6D3F` on alabaster / `#C5A572` on obsidian), crowned with a tailor's needle-eye diamond apex.

### Asset Inventory & Real-World Applications
| Asset File | Lockup Type | Primary Use Cases |
| :--- | :--- | :--- |
| `logo-horizontal.svg` | Horizontal Maison Lockup (Light) | Website masthead, tax invoices, lookbook headers, press letterhead |
| `logo-horizontal-reversed.svg` | Horizontal Maison Lockup (Dark) | Dark-mode masthead, evening campaign covers, garment dust-bags |
| `logo-stacked.svg` / `-reversed.svg` | Centered Vertical Crest | Rigid presentation boxes, tissue belly-bands, boutique signage, footer |
| `logo-monogram.svg` / `-reversed.svg` | Standalone `NA` Plaque | Favicon (`src/app/icon.svg`), wax/ribbon seal, horn button engraving, social avatar, AI Consultant medallion |
| `logo-wordmark.svg` | Pure Typographic Wordmark | Compact mobile masthead, collar tape, hem embroidery |
| `label-woven-tag.svg` | Woven Damask Neck Label | Physical 4-point hand-tacked ecru silk-cotton garment neck label & PDP authenticity preview |
| `packaging-seal.svg` | Security Ribbon Seal | Tamper-evident `POL-RET-01` archive tag required for 4-tier luxury returns |

### Clear-Space, Minimum Size & Misuse Rules
- **Clear Space:** Maintain a minimum clear margin of `0.5X` (where `X` is the height of the octagonal monogram plaque) around all four sides of any lockup.
- **Minimum Sizes:**
  - Horizontal Lockup: `140px` digital / `38mm` print (below `140px`, omit the subtitle or switch to Wordmark/Monogram).
  - Monogram Seal: `16px × 16px` digital favicon / `8mm` woven or engraved hardware.
- **Prohibited Treatments:**
  - Never apply drop shadows, outer glows, 3D bevels, metallic raster gradients, or AI-generated textures to the mark.
  - Never stretch, skew, rotate, or re-space the `NOIR ATELIER` wordmark.
  - Never place the mark over high-frequency photography without a solid archival surface container.

---

## 3. Color Architecture & WCAG AA Accessibility

| Semantic Role | Editorial Light (`:root`) | Contrast on Light | Noir Obsidian (`[data-theme="dark"]`) | Contrast on Dark |
| :--- | :--- | :--- | :--- | :--- |
| **Page Canvas (`--bg-page`)** | `#FAF8F4` (Warm Alabaster) | — | `#0E0E0D` (Atelier Carbon) | — |
| **Elevated Surface (`--bg-surface`)** | `#FFFFFF` (Crisp Rag Paper) | — | `#161614` (Smoked Flannel) | — |
| **Subtle Recess (`--bg-subtle`)** | `#F2EFE9` (Ecru Linen) | — | `#201F1C` (Charcoal Serge) | — |
| **Primary Ink (`--text-primary`)** | `#141312` (Obsidian Ink) | **17.4 : 1** (AAA) | `#F5F2EB` (Raw Silk Ivory) | **16.8 : 1** (AAA) |
| **Secondary Copy (`--text-secondary`)** | `#54504A` (Warm Pewter) | **7.5 : 1** (AAA) | `#B8B2A6` (Silvered Linen) | **8.7 : 1** (AAA) |
| **Muted Metadata (`--text-muted`)** | `#6E6961` (Stone Taupe) | **5.1 : 1** (AA) | `#948D80` (Warm Ash) | **5.5 : 1** (AA) |
| **Antique Bronze (`--accent-gold`)** | `#8C6D3F` (Brushed Bronze) | **4.7 : 1** (AA) | `#C5A572` (Champagne Brass) | **8.2 : 1** (AAA) |
| **Architectural Rule (`--border-subtle`)** | `#E6E1D8` | — | `#2A2824` | — |

---

## 4. Typography System

- **Editorial Display & Headings (`--font-serif`):** `Cormorant Garamond` (Weights `400`, `500`, `600`). High-contrast, classical sartorial proportion for garment titles, collection headings, and the Maison wordmark.
- **Interface & Body Copy (`--font-sans`):** `Plus Jakarta Sans` (Weights `400`, `500`, `600`). Clean, neutral legibility for garment specifications, filters, checkout forms, and AI consultant dialogue.
- **Archival Codes & Fiscal Figures (`--font-mono`):** `JetBrains Mono` + `font-variant-numeric: tabular-nums` for style SKUs (`PRD-001-BLK-M`), HSN chapters (`6109` / `6205`), GSTINs, and tabular INR pricing.

---

## 5. Brand Voice & Personal Fashion Consultant Persona

- **Archetype:** The Master Tailor & Private Client Advisor.
- **Tone Attributes:** Composed, articulate, tactile, transparent, never pushy or promotional.
- **Lexicon:**
  - Prefer *piece, garment, silhouette, drape, weave, archive, shopping bag, complimentary insured courier, private client reserve*.
  - Avoid *deal, hurry, cheap, hot item, grab yours, bot, emojis in UI chrome*.
- **Grounding Rule for AI Consultant:** Every price, size variant, stock count, fabric composition percentage, GST rate, and return tier cited by the AI Consultant must come verbatim from `/api/*` backend services. High-value pieces above the `₹50,000` autonomous agent ceiling are gracefully guided toward verified Card / IMPS-NEFT checkout or human Private Client Concierge assistance.
