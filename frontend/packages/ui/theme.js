export const DESIGN_TOKENS = {
  breakpoints: {
    xs: 360,
    sm: 640,
    md: 768,
    lg: 1024,
    xl: 1280,
    "2xl": 1536,
  },
  fontScales: [
    { id: "compact", label: "Compact (A-)" },
    { id: "default", label: "Default (A)" },
    { id: "large", label: "Large (A+)" },
  ],
};

export function applyFontScale(scaleKey = "default") {
  if (typeof document !== "undefined") {
    document.documentElement.setAttribute("data-font-scale", scaleKey);
  }
}

const EDITORIAL_ARTWORK_BY_SKU = {
  "PRD-001": {
    photoUrl: "https://images.unsplash.com/photo-1596755094514-f87e34085b2c?auto=format&fit=crop&w=900&q=80",
    bgGradient: "linear-gradient(165deg, #d8d3c8 0%, #eae6df 100%)",
    accentTag: "100% European Flax Linen",
  },
  "PRD-002": {
    photoUrl: "https://images.unsplash.com/photo-1544022613-e87ca75a784a?auto=format&fit=crop&w=900&q=80",
    bgGradient: "linear-gradient(165deg, #cfd2d6 0%, #e5e6e8 100%)",
    accentTag: "Double-Faced Merino Wool",
  },
  "PRD-003": {
    photoUrl: "https://images.unsplash.com/photo-1539008835657-9e8e9680c956?auto=format&fit=crop&w=900&q=80",
    bgGradient: "linear-gradient(165deg, #d9d0c5 0%, #efeae2 100%)",
    accentTag: "22-Momme Mulberry Silk",
  },
  "PRD-004": {
    photoUrl: "https://images.unsplash.com/photo-1521572267360-ee0c2909d518?auto=format&fit=crop&w=900&q=80",
    bgGradient: "linear-gradient(165deg, #e5e0d5 0%, #f5f2eb 100%)",
    accentTag: "220 GSM Peruvian Pima",
  },
  "PRD-005": {
    photoUrl: "https://images.unsplash.com/photo-1519238263530-99bdd11df2ea?auto=format&fit=crop&w=900&q=80",
    bgGradient: "linear-gradient(165deg, #ced6df 0%, #e8ecf0 100%)",
    accentTag: "Superfine ZQ Merino Knit",
  },
};

export function getProductEditorialVisual(product = {}) {
  const pid = product.product_id || "PRD-001";
  return (
    EDITORIAL_ARTWORK_BY_SKU[pid] || {
      photoUrl: "https://images.unsplash.com/photo-1490481651871-ab68de25d43d?auto=format&fit=crop&w=900&q=80",
      bgGradient: "linear-gradient(165deg, #dcd8cf 0%, #f0ede6 100%)",
      accentTag: product.department || "Atelier Edition",
    }
  );
}
