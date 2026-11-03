export const DESIGN_TOKENS = {
  breakpoints: { xs: 360, sm: 640, md: 768, lg: 1024, xl: 1280, "2xl": 1536 },
  fontScales: [
    { id: "compact", label: "A-", description: "Smaller text" },
    { id: "default", label: "A", description: "Standard text" },
    { id: "large", label: "A+", description: "Larger text" },
  ],
  themes: [
    { id: "light", label: "Editorial Light" },
    { id: "dark", label: "Noir Dark" },
  ],
};

const STORAGE_KEYS = { theme: "noir_atelier_theme", fontScale: "noir_atelier_font_scale" };

function readStorage(key) {
  try {
    return typeof window !== "undefined" ? window.localStorage.getItem(key) : null;
  } catch {
    return null;
  }
}

function writeStorage(key, value) {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    /* storage unavailable */
  }
}

export function applyTheme(themeKey = "light") {
  if (typeof document === "undefined") return;
  document.documentElement.setAttribute("data-theme", themeKey);
  writeStorage(STORAGE_KEYS.theme, themeKey);
}

export function applyFontScale(scaleKey = "default") {
  if (typeof document === "undefined") return;
  document.documentElement.setAttribute("data-font-scale", scaleKey);
  writeStorage(STORAGE_KEYS.fontScale, scaleKey);
}

export function getInitialTheme() {
  const saved = readStorage(STORAGE_KEYS.theme);
  if (saved === "light" || saved === "dark") return saved;
  if (typeof window !== "undefined" && window.matchMedia?.("(prefers-color-scheme: dark)").matches) return "dark";
  return "light";
}

export function getInitialFontScale() {
  const saved = readStorage(STORAGE_KEYS.fontScale);
  return DESIGN_TOKENS.fontScales.some((f) => f.id === saved) ? saved : "default";
}

function hexToRelativeLuminance(hex) {
  const clean = String(hex || "#000000").replace("#", "");
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(clean.substring(i, i + 2), 16) / 255);
  const [R, G, B] = [r, g, b].map((c) => (c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4)));
  return 0.2126 * R + 0.7152 * G + 0.0722 * B;
}

export function getContrastRatio(hex1, hex2) {
  const l1 = hexToRelativeLuminance(hex1);
  const l2 = hexToRelativeLuminance(hex2);
  const lighter = Math.max(l1, l2);
  const darker = Math.min(l1, l2);
  return Number(((lighter + 0.05) / (darker + 0.05)).toFixed(2));
}

export const ICON_SIZES = {
  xs: 14,
  sm: 16,
  md: 18,
  lg: 22,
  xl: 28,
};

export const SVG_PATHS = {
  search: `<circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" />`,
  bag: `<path d="M6 2 3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4Z"/><path d="M3 6h18"/><path d="M16 10a4 4 0 0 1-8 0"/>`,
  sparkles: `<path d="M12 3l1.9 5.3L19 10l-5.1 1.7L12 17l-1.9-5.3L5 10l5.1-1.7L12 3z"/><path d="M5 3v4"/><path d="M3 5h4"/><path d="M19 17v4"/><path d="M17 19h4"/>`,
  heart: `<path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z"/>`,
  "heart-filled": `<path fill="currentColor" d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z"/>`,
  star: `<polygon fill="currentColor" points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>`,
  sliders: `<line x1="4" x2="4" y1="21" y2="14"/><line x1="4" x2="4" y1="10" y2="3"/><line x1="12" x2="12" y1="21" y2="12"/><line x1="12" x2="12" y1="8" y2="3"/><line x1="20" x2="20" y1="21" y2="16"/><line x1="20" x2="20" y1="12" y2="3"/><line x1="2" x2="6" y1="14" y2="14"/><line x1="10" x2="14" y1="8" y2="8"/><line x1="18" x2="22" y1="16" y2="16"/>`,
  sun: `<circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m6.34 17.66-1.41 1.41"/><path d="m19.07 4.93-1.41 1.41"/>`,
  moon: `<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>`,
  close: `<path d="M18 6 6 18"/><path d="m6 6 12 12"/>`,
  check: `<path d="M20 6 9 17l-5-5"/>`,
  alert: `<circle cx="12" cy="12" r="10"/><line x1="12" x2="12" y1="8" y2="12"/><line x1="12" x2="12.01" y1="16" y2="16"/>`,
  "wifi-off": `<line x1="2" x2="22" y1="2" y2="22"/><path d="M8.5 16.5a5 5 0 0 1 7 0"/><path d="M2 8.82a15 15 0 0 1 4.17-2.65"/><path d="M10.66 5c4.01-.36 8.14.9 11.34 3.76"/><path d="M16.85 11.25a10 10 0 0 1 2.22 1.68"/><path d="M5 12.86a10 10 0 0 1 5.17-2.89"/><line x1="12" x2="12.01" y1="20" y2="20"/>`,
  clock: `<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>`,
  lock: `<rect width="18" height="11" x="3" y="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>`,
  key: `<circle cx="7.5" cy="15.5" r="5.5"/><path d="m21 2-9.6 9.6"/><path d="m15.5 7.5 3 3L22 7l-3-3"/>`,
  shield: `<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m9 12 2 2 4-4"/>`,
  truck: `<path d="M10 17h4V5H2v12h3"/><path d="M20 17h2v-3.34a4 4 0 0 0-1.17-2.83L19 9h-5v8h1"/><circle cx="7.5" cy="17.5" r="2.5"/><circle cx="17.5" cy="17.5" r="2.5"/>`,
  refresh: `<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/>`,
  "arrow-right": `<path d="M5 12h14"/><path d="m12 5 7 7-7 7"/>`,
  menu: `<line x1="4" x2="20" y1="6" y2="6"/><line x1="4" x2="20" y1="12" y2="12"/><line x1="4" x2="20" y1="18" y2="18"/>`,
  home: `<path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/>`,
  package: `<path d="m7.5 4.27 9 5.15"/><path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z"/><path d="m3.3 7 8.7 5 8.7-5"/><path d="M12 22V12"/>`,
  user: `<path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>`,
};

export function renderIcon(name, size = "sm") {
  const px = ICON_SIZES[size] || Number(size) || 16;
  const inner = SVG_PATHS[name] || SVG_PATHS.sparkles;
  return `<span class="ui-icon" aria-hidden="true"><svg width="${px}" height="${px}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.85" stroke-linecap="round" stroke-linejoin="round">${inner}</svg></span>`;
}

const DEPT_GRADIENT_TOKENS = {
  MEN: "linear-gradient(165deg, #d8d3c8 0%, #eae6df 100%)",
  WOMEN: "linear-gradient(165deg, #d9d0c5 0%, #efeae2 100%)",
  KIDS: "linear-gradient(165deg, #ced6df 0%, #e8ecf0 100%)",
};

export function getProductEditorialVisual(product = {}) {
  const dbImgUrl =
    product.image_gallery?.[0]?.url ||
    product.images?.[0] ||
    "";
  const dbAccentTag =
    product.accent_tag ||
    product.image_gallery?.[0]?.alt_text ||
    product.department ||
    "Atelier Edition";
  const bgGradient =
    DEPT_GRADIENT_TOKENS[product.department] ||
    "linear-gradient(165deg, #dcd8cf 0%, #f0ede6 100%)";

  return {
    photoUrl: dbImgUrl,
    bgGradient,
    accentTag: dbAccentTag,
  };
}

export function getProductImage(product = {}) {
  return {
    url: product.image_gallery?.[0]?.url || product.images?.[0] || "",
    alt: product.image_gallery?.[0]?.alt_text || product.name || "Noir Atelier garment",
  };
}
