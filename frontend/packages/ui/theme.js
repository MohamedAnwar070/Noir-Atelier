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
    { id: "compact", label: "Compact (0.92x)" },
    { id: "default", label: "Editorial Default (1.0x)" },
    { id: "large", label: "Large (1.10x)" },
  ],
};

export function applyFontScale(scaleKey = "default") {
  if (typeof document !== "undefined") {
    document.documentElement.setAttribute("data-font-scale", scaleKey);
  }
}

export function deriveGarmentStyleFromProduct(product = {}) {
  const hsn = String(product.hsn_code || "");
  const name = String(product.name || "").toLowerCase();
  const color = String(product.color || "").toLowerCase();

  let silhouette = "shirt";
  if (name.includes("dress") || hsn === "6204") silhouette = "dress";
  else if (name.includes("overshirt") || hsn === "6201") silhouette = "overshirt";
  else if (name.includes("tee") || hsn === "6109") silhouette = "tee";
  else if (name.includes("crewneck") || hsn === "6110") silhouette = "crewneck";

  let tone = "#1c1c1b";
  let gradient = "linear-gradient(160deg, #4b78a4 0%, #83a5c3 48%, #e6ded2 100%)";
  let cardBg = "linear-gradient(180deg, #dfddd7 0%, #f2f0ea 100%)";

  if (color.includes("ivory")) {
    tone = "#ece6da";
    gradient = "linear-gradient(160deg, #5581ac 0%, #90b0ce 48%, #f2ebe0 100%)";
    cardBg = "linear-gradient(180deg, #e7e3db 0%, #f6f4ef 100%)";
  } else if (color.includes("charcoal")) {
    tone = "#2e2f30";
    gradient = "linear-gradient(160deg, #3c4753 0%, #6b7682 48%, #ded8ce 100%)";
  } else if (color.includes("navy")) {
    tone = "#1d2d44";
    gradient = "linear-gradient(160deg, #345170 0%, #6c8aa7 50%, #e5ded3 100%)";
  } else if (color.includes("obsidian")) {
    tone = "#141413";
    gradient = "linear-gradient(160deg, #2e4b68 0%, #5b7b99 50%, #e5dccf 100%)";
  }

  return { silhouette, tone, gradient, cardBg };
}

export function renderGarmentArtwork(product = {}, size = "card") {
  const { silhouette, tone } = deriveGarmentStyleFromProduct(product);
  const height = size === "hero" ? 245 : 158;
  const stroke = tone === "#ece6da" ? "#8c8578" : "#ffffff";
  const pid = product.product_id || "garment";

  const paths = {
    shirt: `<path d="M45 34 L62 24 L78 24 L95 34 L112 52 L98 66 L88 54 L88 122 L52 122 L52 54 L42 66 L28 52 Z" fill="${tone}" stroke="${stroke}" stroke-width="1.5"/><line x1="70" y1="26" x2="70" y2="122" stroke="${stroke}" stroke-width="1.2" stroke-dasharray="3 3"/>`,
    overshirt: `<path d="M42 30 L60 22 L80 22 L98 30 L116 58 L100 70 L90 52 L90 124 L50 124 L50 52 L40 70 L24 58 Z" fill="${tone}" stroke="${stroke}" stroke-width="1.5"/><rect x="55" y="54" width="11" height="13" rx="2" fill="none" stroke="${stroke}" stroke-width="1.2"/><rect x="74" y="54" width="11" height="13" rx="2" fill="none" stroke="${stroke}" stroke-width="1.2"/>`,
    dress: `<path d="M54 24 L64 36 L76 36 L86 24 L92 56 L106 126 L34 126 L48 56 Z" fill="${tone}" stroke="${stroke}" stroke-width="1.4"/>`,
    tee: `<path d="M44 34 L58 26 C64 32 76 32 82 26 L96 34 L110 52 L96 64 L88 52 L88 120 L52 120 L52 52 L44 64 L30 52 Z" fill="${tone}" stroke="${stroke}" stroke-width="1.5"/>`,
    crewneck: `<path d="M46 36 L60 28 C65 33 75 33 80 28 L94 36 L110 66 L96 74 L86 54 L86 118 L54 118 L54 54 L44 74 L30 66 Z" fill="${tone}" stroke="${stroke}" stroke-width="1.5"/>`,
  };

  return `
    <svg viewBox="0 0 140 145" width="100%" height="${height}" role="img" aria-label="${product.name || pid}" style="display:block; filter: drop-shadow(0 12px 18px rgba(18,17,16,0.16));">
      <defs>
        <radialGradient id="glow-${pid}-${size}" cx="50%" cy="32%" r="60%">
          <stop offset="0%" stop-color="#ffffff" stop-opacity="0.72"/>
          <stop offset="100%" stop-color="#ffffff" stop-opacity="0"/>
        </radialGradient>
      </defs>
      <circle cx="70" cy="70" r="56" fill="url(#glow-${pid}-${size})"/>
      ${paths[silhouette] || paths.shirt}
    </svg>
  `;
}
